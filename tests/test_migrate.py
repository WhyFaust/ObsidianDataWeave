"""Tests for migrate.py — idempotent upgrade steps."""

import json
import sqlite3
from pathlib import Path

import pytest

from scripts import config, migrate
from scripts.memory_index import db_path_for_vault, fts5_available, search, status
from scripts.migrate import ensure_index, ensure_memory_section


def test_ensure_memory_section_added_once(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('[vault]\nvault_path = "/tmp/v"\n', encoding="utf-8")

    assert ensure_memory_section(cfg) == "added"
    text = cfg.read_text(encoding="utf-8")
    assert "[memory]" in text and text.startswith("[vault]")  # original kept

    assert ensure_memory_section(cfg) == "present"  # idempotent
    assert text == cfg.read_text(encoding="utf-8")


def test_ensure_memory_section_no_config(tmp_path: Path) -> None:
    assert ensure_memory_section(tmp_path / "config.toml") == "no-config"


@pytest.mark.parametrize(
    ("vault_path", "enabled", "expected"),
    [
        ("unavailable", False, "memory disabled"),
        ("", True, "vault_path not configured"),
        ("/path/to/your/obsidian/vault", True, "vault_path not configured"),
    ],
    ids=["disabled", "empty", "placeholder"],
)
def test_ensure_index_skips_gracefully(
    tmp_path: Path, vault_path: str, enabled: bool, expected: str,
) -> None:
    if vault_path == "unavailable":
        vault_path = str(tmp_path / "unavailable")
    out = ensure_index({"vault": {"vault_path": vault_path},
                        "memory": {"enabled": enabled, "db_dir": str(tmp_path / "cache")}})
    assert out.startswith("skipped")
    assert expected in out
    assert not (tmp_path / "cache").exists()


def test_ensure_index_builds_then_refreshes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("# hello\n\nworld\n", encoding="utf-8")
    cfg = {"vault": {"vault_path": str(vault)},
           "memory": {"enabled": True, "db_dir": str(tmp_path / "cache"),
                      "tokenizer": "unicode61", "auto_update": True}}

    first = ensure_index(cfg)
    assert first.startswith("built: 1 notes")
    second = ensure_index(cfg)
    assert second.startswith("refreshed: 1 notes")


def test_upgrade_legacy_wal_before_read_only_queries(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("# hello\n\nworld\n", encoding="utf-8")
    cache = tmp_path / "cache"
    cfg = {"vault": {"vault_path": str(vault)},
           "memory": {"enabled": True, "db_dir": str(cache), "tokenizer": "unicode61"}}
    ensure_index(cfg)
    db_path = db_path_for_vault(vault, str(cache))
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    finally:
        conn.close()
    assert list(cache.iterdir()) == [db_path]

    assert ensure_index(cfg).startswith("refreshed: 1 notes")
    before = db_path.read_bytes()
    db_path.chmod(0o444)
    cache.chmod(0o555)
    try:
        conn = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
        try:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        finally:
            conn.close()
        assert status(cfg)["notes"] == 1
        assert search(cfg, "world")[0]["path"] == "note.md"
        assert db_path.read_bytes() == before
        assert list(cache.iterdir()) == [db_path]
    finally:
        cache.chmod(0o755)
        db_path.chmod(0o644)


@pytest.mark.skipif(
    not fts5_available() or config.tomllib is None, reason="FTS5 and a TOML parser are required"
)
@pytest.mark.parametrize("vault_is_file", [False, True], ids=["missing", "not-directory"])
def test_main_fails_for_unavailable_vault_without_changing_wal_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    vault_is_file: bool,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("# Retained\n\nLegacy WAL content.\n", encoding="utf-8")
    cache = tmp_path / "cache"
    cfg = {"vault": {"vault_path": str(vault)},
           "memory": {"enabled": True, "db_dir": str(cache)}}
    ensure_index(cfg)
    db_path = db_path_for_vault(vault, str(cache))
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        conn.execute("UPDATE notes_fts SET body = ?", ("committed wal content",))
        conn.commit()
    finally:
        conn.close()
    before = {path.name: path.read_bytes() for path in cache.iterdir()}
    vault.rename(tmp_path / "offline-vault")
    if vault_is_file:
        vault.write_text("not a directory", encoding="utf-8")
    (tmp_path / "config.toml").write_text(
        f"[vault]\nvault_path = {json.dumps(str(vault))}\n"
        f"[memory]\nenabled = true\ndb_dir = {json.dumps(str(cache))}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(migrate, "PROJECT_ROOT", tmp_path)

    result = migrate.main()

    output = capsys.readouterr()
    assert {path.name: path.read_bytes() for path in cache.iterdir()} == before
    assert result == 1, output.out + output.err
    assert "FAILED" in output.err
    assert str(vault) in output.err
    assert "vault_path" in output.err
    assert "config.toml" in output.err
    assert "skipped" not in output.out
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("SELECT path, body FROM notes_fts").fetchall() == [
            ("note.md", "committed wal content")
        ]
    finally:
        conn.close()
