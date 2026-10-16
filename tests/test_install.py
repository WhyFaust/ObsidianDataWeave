import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


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
