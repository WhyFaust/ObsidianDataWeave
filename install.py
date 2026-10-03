#!/usr/bin/env python3
"""Install into a project venv on Windows, macOS or Linux (stdlib bootstrap)."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def create_config(vault_path, remote):
    config_path = ROOT / "config.toml"
    if config_path.exists():
        print("config.toml already exists; existing values preserved.")
        return
    text = (ROOT / "config.example.toml").read_text(encoding="utf-8")
    if vault_path:
        text = text.replace('"/path/to/your/obsidian/vault"',
                            json.dumps(Path(vault_path).expanduser().resolve().as_posix(), ensure_ascii=False))
    text = text.replace('remote = "gdrive:"',
                        "remote = " + json.dumps(remote if remote.endswith(":") else remote + ":"))
    staging = (Path(tempfile.gettempdir()) / "obsidian-dataweave" / "staging").as_posix()
    text = text.replace('staging_dir = ""', "staging_dir = " + json.dumps(staging, ensure_ascii=False))
    try:
        with config_path.open("x", encoding="utf-8") as stream:
            stream.write(text)
    except FileExistsError:
        print("config.toml was created concurrently; preserved.")
    else:
        print("Created config.toml; configure vault_path before use." if not vault_path
              else "Created config.toml with the supplied vault path.")


def register_claude(python):
    skill_dir = Path.home() / ".claude" / "skills" / "obsidian-dataweave"
    files = {
        "SKILL.md": "SKILL.md",
        "rules/atomization.md": "references/atomization-rules.md",
        "rules/taxonomy.md": "references/taxonomy-rules.md",
        "rules/personal_notes.md": "references/personal-notes-rules.md",
        "rules/contacts.md": "references/contacts-rules.md",
        "tags.yaml": "references/tags.yaml",
    }
    # Copies need neither Windows Developer Mode nor symlink privileges.
    # Rerun the installer after git pull to refresh these managed files.
    for source, relative in files.items():
        target = skill_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            target.unlink()
        shutil.copy2(ROOT / source, target)

    claude_md = Path.home() / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True, exist_ok=True)
    content = claude_md.read_text(encoding="utf-8") if claude_md.exists() else ""
    content = re.sub(r"\n*## ObsidianDataWeave[^\n]*\n.*?(?=\n## |\Z)", "", content, flags=re.DOTALL)
    block = (
        "\n\n## ObsidianDataWeave\n\n"
        "Obsidian note processing: enrich/atomize + .docx and NotebookLM import.\n\n"
        f"- **Skill:** `{skill_dir / 'SKILL.md'}`\n"
        f"- **Repo:** `{ROOT}`\n"
        f"- **Python:** `{python}` (use this project interpreter for scripts)\n\n"
        "### Trigger phrases\n"
        '- "process note X" / "обработай заметку X"\n'
        '- "enrich note X" / "atomize note X"\n'
        '- "import document X.docx" / "обработай документ X.docx"\n'
        '- "zettelkasten rules" / "правила заметок"\n'
    )
    claude_md.write_text(content + block, encoding="utf-8")
    print(f"Registered Claude skill at {skill_dir}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("local", "claude", "codex"), default="claude")
    parser.add_argument("--vault-path", help="path to an existing Obsidian vault")
    parser.add_argument("--rclone-remote", default="gdrive:")
    parser.add_argument("--skip-index", action="store_true", help="skip memory migration/index creation")
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error("Python 3.10+ is required")
    if args.vault_path and not Path(args.vault_path).expanduser().is_dir():
        parser.error("--vault-path must point to an existing directory")
    if not args.rclone_remote.strip():
        parser.error("--rclone-remote must not be empty")

    required = ("requirements.txt", "config.example.toml", "AGENTS.md", "SKILL.md",
                "SKILL_PERSONAL.md", "rules/atomization.md", "rules/taxonomy.md",
                "rules/personal_notes.md", "rules/contacts.md", "tags.yaml")
    for relative in required:
        if not (ROOT / relative).is_file():
            raise RuntimeError(f"Missing repository file: {relative}")

    venv = ROOT / ".venv"
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if venv.exists() and not python.is_file():
        raise RuntimeError("Existing .venv is incomplete or belongs to another OS. "
                           "Move it aside and rerun; virtual environments are not portable.")
    if not python.is_file():
        run(sys.executable, "-m", "venv", venv)
    # Always use this interpreter's pip, including all requirements on upgrades.
    run(python, "-m", "pip", "install", "-r", ROOT / "requirements.txt")
    create_config(args.vault_path, args.rclone_remote)
    if not args.skip_index:
        run(python, ROOT / "scripts" / "migrate.py")
    if args.mode == "claude":
        register_claude(python)
    elif args.mode == "codex":
        print("Codex uses repo-local AGENTS.md; no global registration needed.")
    print(f"Installed. Run project scripts with: {python}")
    print("Claude/Codex CLI, rclone and browser login are separate, optional workflow prerequisites.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
