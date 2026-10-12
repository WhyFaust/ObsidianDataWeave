"""Tests for migrate.py — idempotent upgrade steps."""

import sqlite3
from pathlib import Path

from scripts.memory_index import db_path_for_vault, search, status
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


def test_ensure_index_skips_gracefully(tmp_path: Path) -> None:
    # memory disabled
    out = ensure_index({"vault": {"vault_path": str(tmp_path)},
                        "memory": {"enabled": False}})
    assert out.startswith("skipped")
    # vault_path placeholder / missing
    out = ensure_index({"vault": {"vault_path": "/path/to/your/obsidian/vault"},
                        "memory": {"enabled": True, "db_dir": str(tmp_path)}})
    assert "vault_path not configured" in out


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
