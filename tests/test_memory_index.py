"""Tests for memory_index.py — FTS5 vault memory (build/update/search)."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path, PureWindowsPath
from unittest.mock import Mock

import pytest

from scripts.memory_index import (
    auto_update_after_write,
    build_match_expr,
    db_path_for_vault,
    fts5_available,
    open_db,
    search,
    status,
    update_index,
)

pytestmark = pytest.mark.skipif(
    not fts5_available(), reason="sqlite3 built without FTS5"
)


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / "Notes").mkdir(parents=True)
    (root / "Guides").mkdir()
    (root / ".smart-env").mkdir()

    (root / "Notes" / "ai-agents.md").write_text(
        "---\ntags:\n  - ai\n  - agents\n---\n"
        "# Агенты и память\n\nАвтономные агенты используют контекст.\n"
        "## Memory layers\n\nLexical search beats embeddings here.\n",
        encoding="utf-8",
    )
    (root / "Notes" / "cooking.md").write_text(
        "---\ntags: [food]\n---\n# Борщ\n\nРецепт борща со свёклой.\n",
        encoding="utf-8",
    )
    (root / "Guides" / "overview.md").write_text(
        "# Overview\n\nThe vault holds compiled knowledge.\n", encoding="utf-8"
    )
    (root / "root-note.md").write_text("Plain root note about zettelkasten.\n",
                                       encoding="utf-8")
    (root / ".smart-env" / "cache.md").write_text("legacy embeddings cache\n",
                                                  encoding="utf-8")
    return root


@pytest.fixture
def cfg(vault: Path, tmp_path: Path) -> dict:
    return {
        "vault": {"vault_path": str(vault)},
        "memory": {"enabled": True, "db_dir": str(tmp_path / "cache"),
                   "tokenizer": "unicode61", "auto_update": True},
    }


# ── build / scan ──────────────────────────────────────────────────────────────


def test_build_indexes_all_and_skips_hidden(cfg: dict) -> None:
    stats = update_index(cfg, full=True, quiet=True)
    assert stats["total"] == 4  # .smart-env/cache.md is skipped
    info = status(cfg)
    assert info["exists"] and info["notes"] == 4


def test_search_russian_and_english(cfg: dict) -> None:
    update_index(cfg, full=True, quiet=True)
    ru = search(cfg, "агенты")
    assert ru and ru[0]["path"] == "Notes/ai-agents.md"
    en = search(cfg, "vault")
    assert en and en[0]["path"] == "Guides/overview.md"


def test_prefix_search(cfg: dict) -> None:
    update_index(cfg, full=True, quiet=True)
    assert search(cfg, "агент") == []  # exact token does not exist
    hits = search(cfg, "агент", prefix=True)
    assert hits and hits[0]["path"] == "Notes/ai-agents.md"


def test_title_ranked_above_body(cfg: dict, vault: Path) -> None:
    (vault / "Notes" / "memory.md").write_text("# memory\n\nshort\n", encoding="utf-8")
    update_index(cfg, full=True, quiet=True)
    hits = search(cfg, "memory")
    assert hits[0]["path"] == "Notes/memory.md"  # title hit outranks body hits


# ── incremental update ────────────────────────────────────────────────────────


def test_update_modified_and_removed(cfg: dict, vault: Path) -> None:
    update_index(cfg, full=True, quiet=True)
    note = vault / "Notes" / "cooking.md"
    note.write_text(note.read_text(encoding="utf-8") + "\nДобавлен пастернак.\n",
                    encoding="utf-8")
    (vault / "root-note.md").unlink()

    stats = update_index(cfg, quiet=True)
    assert stats["indexed"] == 1 and stats["removed"] == 1 and stats["total"] == 3
    assert search(cfg, "пастернак")[0]["path"] == "Notes/cooking.md"
    assert search(cfg, "zettelkasten") == []


# ── filters ───────────────────────────────────────────────────────────────────


def test_tag_filter(cfg: dict) -> None:
    update_index(cfg, full=True, quiet=True)
    hits = search(cfg, "рецепт", tag="food")
    assert [h["path"] for h in hits] == ["Notes/cooking.md"]
    assert search(cfg, "рецепт", tag="ai") == []


def test_folder_filter(cfg: dict) -> None:
    update_index(cfg, full=True, quiet=True)
    hits = search(cfg, "knowledge", folder="Notes")
    assert hits == []
    hits = search(cfg, "knowledge", folder="Guides")
    assert hits and hits[0]["path"] == "Guides/overview.md"


# ── auto-update hook ──────────────────────────────────────────────────────────


def test_auto_update_noop_without_db(cfg: dict, tmp_path: Path, capsys) -> None:
    auto_update_after_write(cfg)
    assert not (tmp_path / "cache").exists()  # hook never creates the first build
    err = capsys.readouterr().err  # but it must signal the missing index
    assert "not built" in err and "memory_index.py build" in err


def test_auto_update_refreshes_existing_db(cfg: dict, vault: Path, capsys) -> None:
    update_index(cfg, full=True, quiet=True)
    (vault / "Notes" / "fresh.md").write_text("# fresh\n\nсвежайшая заметка\n",
                                              encoding="utf-8")
    capsys.readouterr()  # drop anything from the build above
    auto_update_after_write(cfg)
    assert search(cfg, "свежайшая")[0]["path"] == "Notes/fresh.md"
    assert "not built" not in capsys.readouterr().err  # silent once the db exists


def test_auto_update_respects_flags(cfg: dict, vault: Path) -> None:
    update_index(cfg, full=True, quiet=True)
    cfg["memory"]["auto_update"] = False
    (vault / "Notes" / "ghost.md").write_text("призрачная заметка\n", encoding="utf-8")
    auto_update_after_write(cfg)
    assert search(cfg, "призрачная") == []


# ── plumbing ──────────────────────────────────────────────────────────────────


def test_db_path_distinct_per_vault(tmp_path: Path) -> None:
    a = db_path_for_vault(tmp_path / "VaultA", str(tmp_path))
    b = db_path_for_vault(tmp_path / "VaultB", str(tmp_path))
    assert a != b and a.parent == b.parent == tmp_path


def test_match_expr_is_injection_safe(cfg: dict) -> None:
    update_index(cfg, full=True, quiet=True)
    # quotes and FTS5 operators inside the query must not break the MATCH
    assert search(cfg, 'рецепт" OR x:y AND (') == []
    expr = build_match_expr('a"b OR c', tag='fo"od')
    assert '""' in expr and expr.startswith("(")


def test_search_without_index_raises(cfg: dict, tmp_path: Path) -> None:
    cfg["memory"]["db_dir"] = str(tmp_path / "nowhere")
    with pytest.raises(RuntimeError, match="index not built"):
        search(cfg, "anything")


def test_read_only_connection_rejects_writes(cfg: dict) -> None:
    update_index(cfg, full=True, quiet=True)
    db_path = db_path_for_vault(Path(cfg["vault"]["vault_path"]), cfg["memory"]["db_dir"])
    conn = open_db(db_path, readonly=True)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM files")
    finally:
        conn.close()


@pytest.mark.skipif(os.name == "nt", reason="POSIX local path emulates UNC without a network share")
def test_read_only_unc_uri_preserves_path_and_rejects_writes(cfg: dict) -> None:
    update_index(cfg, full=True, quiet=True)
    db_path = db_path_for_vault(Path(cfg["vault"]["vault_path"]), cfg["memory"]["db_dir"])
    unc_path = PureWindowsPath("//" + db_path.as_posix().lstrip("/"))
    path = Mock(spec=Path)
    path.resolve.return_value = unc_path
    before = db_path.read_bytes()
    conn = open_db(path, readonly=True)
    try:
        assert conn.execute("SELECT count(*) FROM files").fetchone()[0] == 4
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM files")
    finally:
        conn.close()
    assert db_path.read_bytes() == before


def test_read_only_open_does_not_create_missing_index(tmp_path: Path) -> None:
    db_path = tmp_path / "missing" / "index.db"
    with pytest.raises(sqlite3.OperationalError):
        open_db(db_path, readonly=True)
    assert not db_path.parent.exists()


def test_read_helpers_work_without_write_permissions(cfg: dict, tmp_path: Path) -> None:
    cfg["memory"]["db_dir"] = str(tmp_path / "cache with # and ?")
    update_index(cfg, full=True, quiet=True)
    db_path = db_path_for_vault(Path(cfg["vault"]["vault_path"]), cfg["memory"]["db_dir"])
    before = db_path.read_bytes()
    db_path.chmod(0o444)
    db_path.parent.chmod(0o555)
    try:
        assert search(cfg, "агенты")[0]["path"] == "Notes/ai-agents.md"
        assert status(cfg)["notes"] == 4
        assert db_path.read_bytes() == before
        assert list(db_path.parent.iterdir()) == [db_path]
    finally:
        db_path.parent.chmod(0o755)
        db_path.chmod(0o644)


def test_writer_converts_existing_wal_index(cfg: dict) -> None:
    update_index(cfg, full=True, quiet=True)
    db_path = db_path_for_vault(Path(cfg["vault"]["vault_path"]), cfg["memory"]["db_dir"])
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    finally:
        conn.close()
    update_index(cfg, quiet=True)
    conn = open_db(db_path, readonly=True)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert conn.execute("SELECT count(*) FROM files").fetchone()[0] == 4
    finally:
        conn.close()


def test_hot_journal_requires_explicit_recovery(cfg: dict) -> None:
    update_index(cfg, full=True, quiet=True)
    db_path = db_path_for_vault(Path(cfg["vault"]["vault_path"]), cfg["memory"]["db_dir"])
    crashed = subprocess.run(
        [sys.executable, "-c", """
import os
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
conn.execute("PRAGMA cache_size=1")
conn.execute("BEGIN IMMEDIATE")
conn.execute("DELETE FROM files")
conn.execute("UPDATE notes_fts SET body = ?", ("uncommitted " * 20000,))
os._exit(99)
""", str(db_path)],
        capture_output=True, timeout=10,
    )
    assert crashed.returncode == 99, crashed.stderr.decode()
    journal = Path(str(db_path) + "-journal")
    assert journal.exists()
    before = (db_path.read_bytes(), journal.read_bytes())
    for reader in [lambda: status(cfg), lambda: search(cfg, "агенты")]:
        with pytest.raises(RuntimeError, match="INDEX_RECOVERY_REQUIRED.*memory_index.py update"):
            reader()
        assert (db_path.read_bytes(), journal.read_bytes()) == before

    assert update_index(cfg, quiet=True)["indexed"] == 0
    assert not journal.exists()
    assert status(cfg)["notes"] == 4
    assert search(cfg, "агенты")[0]["path"] == "Notes/ai-agents.md"
