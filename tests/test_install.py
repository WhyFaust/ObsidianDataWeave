import json
import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import config
from scripts.memory_index import db_path_for_vault, fts5_available, update_index


@pytest.mark.parametrize("migration_exit", [0, 23], ids=["success", "failure"])
def test_migration_gates_registration_and_completion(tmp_path: Path, migration_exit: int) -> None:
    source = Path(__file__).resolve().parents[1]
    project = tmp_path / "project"
    project.mkdir()
    for relative in (
        "install.sh", "AGENTS.md", "SKILL.md", "SKILL_PERSONAL.md", "tags.yaml",
        "rules/atomization.md", "rules/taxonomy.md", "rules/personal_notes.md", "rules/contacts.md",
    ):
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)
    (project / "config.toml").write_text("[memory]\nenabled = false\n", encoding="utf-8")
    (project / "scripts").mkdir()
    (project / "scripts" / "migrate.py").write_text(
        f"print('migration exit {migration_exit}')\nraise SystemExit({migration_exit})\n",
        encoding="utf-8",
    )
    dependencies = tmp_path / "dependencies"
    dependencies.mkdir()
    for module in ("docx", "yaml", "tomli"):
        (dependencies / f"{module}.py").touch()
    home = tmp_path / "home"
    home.mkdir()
    env = {
        **os.environ,
        "HOME": str(home),
        "PYTHONPATH": str(dependencies),
        "PATH": os.pathsep.join((str(Path(sys.executable).parent), os.environ["PATH"])),
    }

    result = subprocess.run(
        ["bash", str(project / "install.sh"), "--mode", "claude"],
        cwd=project, env=env, capture_output=True, text=True, timeout=10,
    )

    assert f"migration exit {migration_exit}" in result.stdout
    assert result.returncode == migration_exit, result.stdout + result.stderr
    registered_skill = home / ".claude" / "skills" / "obsidian-dataweave" / "SKILL.md"
    if migration_exit:
        assert "== Done ==" not in result.stdout
        assert "== Global skill registration ==" not in result.stdout
        assert not (home / ".claude").exists()
    else:
        assert "== Done ==" in result.stdout
        assert registered_skill.is_symlink()
        assert (home / ".claude" / "CLAUDE.md").is_file()


@pytest.mark.skipif(
    not fts5_available() or config.tomllib is None, reason="FTS5 and a TOML parser are required"
)
def test_unavailable_vault_stops_install_before_registration(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1]
    project = tmp_path / "project"
    project.mkdir()
    for relative in (
        "install.sh", "AGENTS.md", "SKILL.md", "SKILL_PERSONAL.md", "tags.yaml",
        "rules/atomization.md", "rules/taxonomy.md", "rules/personal_notes.md", "rules/contacts.md",
        "scripts/migrate.py", "scripts/config.py", "scripts/memory_index.py", "scripts/scan_vault.py",
    ):
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("# Retained\n\nLegacy WAL content.\n", encoding="utf-8")
    cache = tmp_path / "cache"
    cfg = {"vault": {"vault_path": str(vault)},
           "memory": {"enabled": True, "db_dir": str(cache)}}
    update_index(cfg, full=True, quiet=True)
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
    (project / "config.toml").write_text(
        f"[vault]\nvault_path = {json.dumps(str(vault))}\n"
        f"[memory]\nenabled = true\ndb_dir = {json.dumps(str(cache))}\n",
        encoding="utf-8",
    )
    commands = tmp_path / "bin"
    commands.mkdir()
    probe = "import docx, yaml, sys; sys.version_info >= (3, 11) or __import__('tomli')"
    python = commands / "python3"
    python.write_text(
        '#!/bin/bash\n'
        f'if [[ "${{1:-}}" == "-c" && "${{2:-}}" == {shlex.quote(probe)} ]]; then\n'
        '    exit 0\n'
        'fi\n'
        f'exec {shlex.quote(sys.executable)} "$@"\n',
        encoding="utf-8",
    )
    python.chmod(0o755)
    pip = commands / "pip3"
    pip.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    pip.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = {
        **os.environ,
        "HOME": str(home),
        "PYTHONPATH": str(project),
        "PATH": os.pathsep.join((str(commands), os.defpath)),
    }

    result = subprocess.run(
        ["bash", str(project / "install.sh"), "--mode", "claude"],
        cwd=project, env=env, capture_output=True, text=True, timeout=10,
    )

    assert {path.name: path.read_bytes() for path in cache.iterdir()} == before
    assert result.returncode == 1, result.stdout + result.stderr
    assert "index: FAILED" in result.stderr
    assert str(vault) in result.stderr
    assert "== Global skill registration ==" not in result.stdout
    assert "== Done ==" not in result.stdout
    assert not (home / ".claude").exists()
