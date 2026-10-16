import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from scripts import config, doctor
from scripts.memory_index import db_path_for_vault, fts5_available, update_index

pytestmark = pytest.mark.skipif(
    not fts5_available() or config.tomllib is None, reason="FTS5 and a TOML parser are required"
)


@pytest.mark.parametrize("recovery_required", [False, True], ids=["healthy", "recovery"])
def test_memory_diagnostics_allow_later_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    recovery_required: bool,
) -> None:
    source = Path(__file__).resolve().parents[1]
    project = tmp_path / "project"
    project.mkdir()
    for name in (
        "config.example.toml", "AGENTS.md", "SKILL.md", "SKILL_PERSONAL.md",
        "SKILL_CONTACTS.md", "tags.yaml", "wiki_tags.yaml",
    ):
        shutil.copy2(source / name, project / name)
    for name in ("rules", "templates"):
        shutil.copytree(source / name, project / name)
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("# Memory\n\nA diagnostic note.\n", encoding="utf-8")
    cache = tmp_path / "cache"
    cfg = {
        "vault": {"vault_path": str(vault)},
        "memory": {"enabled": True, "db_dir": str(cache)},
    }
    (project / "config.toml").write_text(
        f"[vault]\nvault_path = {json.dumps(str(vault))}\n"
        f"[memory]\nenabled = true\ndb_dir = {json.dumps(str(cache))}\n",
        encoding="utf-8",
    )
    update_index(cfg, full=True, quiet=True)
    db_path = db_path_for_vault(vault, str(cache))
    journal = Path(str(db_path) + "-journal")
    if recovery_required:
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
            capture_output=True, text=True, timeout=10,
        )
        assert crashed.returncode == 99, crashed.stderr
        before = (db_path.read_bytes(), journal.read_bytes())
    monkeypatch.setattr(config, "PROJECT_ROOT", project)
    monkeypatch.setattr(doctor, "PROJECT_ROOT", project)
    monkeypatch.setattr(doctor, "REGISTRY_PATH", project / "processed.json")
    monkeypatch.setattr(shutil, "which", lambda name: sys.executable)
    monkeypatch.setitem(sys.modules, "notebooklm", ModuleType("notebooklm"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    if recovery_required:
        with pytest.raises(SystemExit) as exc:
            doctor.main()
        assert exc.value.code == 1
    else:
        assert doctor.main() is None

    output = capsys.readouterr()
    assert "command `python3`" in output.out
    assert "command `claude`" in output.out
    assert "command `codex`" in output.out
    assert "command `rclone`" in output.out
    assert "python module `notebooklm`" in output.out
    assert "notebooklm auth:" in output.out
    assert "Traceback" not in output.err
    if recovery_required:
        assert "ERROR    memory index:" in output.out
        assert "INDEX_RECOVERY_REQUIRED" in output.out
        assert "python3 scripts/memory_index.py update" in output.out
        assert "write access" in output.out
        assert "do not delete the journal" in output.out
        assert (db_path.read_bytes(), journal.read_bytes()) == before
    else:
        assert "OK       memory index: 1 notes" in output.out
