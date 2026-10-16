"""migrate.py — idempotent upgrade step for existing ObsidianDataWeave installs.

Run after every `git pull` (install.sh calls it automatically):

    python3 scripts/migrate.py

Ensure-style, no version bookkeeping: each step checks reality and only does
what is missing. Safe to run any number of times.

Current steps:
1. config.toml gets the [memory] section (FTS5 memory defaults) if absent.
2. The FTS5 vault index is built (or incrementally refreshed) when
   vault_path is configured and [memory].enabled is true.

Nothing in the vault is ever touched; the legacy Smart Connections cache
(.smart-env/) is left as-is for users who still want the plugin.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from scripts.config import PROJECT_ROOT, load_config
    from scripts.memory_index import (
        db_path_for_vault,
        fts5_available,
        memory_config,
        update_index,
        vault_path_from,
    )
except ModuleNotFoundError:
    from config import PROJECT_ROOT, load_config
    from memory_index import (
        db_path_for_vault,
        fts5_available,
        memory_config,
        update_index,
        vault_path_from,
    )

MEMORY_SECTION = """
[memory]
# FTS5 full-text memory over the whole vault (replaces the legacy
# Smart Connections embedding layer). Zero dependencies: stdlib sqlite3.
enabled = true

# Where the SQLite index lives. Empty → ~/.cache/obsidian-dataweave/
# (one db per vault, named <vault-slug>-<hash>.db). The index is always
# OUTSIDE the vault so vault sync (gdrive/iCloud/...) never touches it.
db_dir = ""

# "unicode61" (default — compact, word-level, Cyrillic-safe) or
# "trigram" (substring matching like pg_trgm; needs SQLite >= 3.34,
# index is noticeably larger).
tokenizer = "unicode61"

# Refresh the index automatically after each vault_writer write.
# First build is always explicit: scripts/memory_index.py build (or migrate.py).
auto_update = true
"""


def ensure_memory_section(config_path: Path) -> str:
    """Append the [memory] block to config.toml if it is missing.

    Returns one of: "added", "present", "no-config".
    """
    if not config_path.exists():
        return "no-config"
    text = config_path.read_text(encoding="utf-8")
    if "[memory]" in text:
        return "present"
    if text and not text.endswith("\n"):
        text += "\n"
    config_path.write_text(text + MEMORY_SECTION, encoding="utf-8")
    return "added"


def ensure_index(config: dict) -> str:
    """Build or refresh the FTS5 index. Returns a human status string."""
    mem = memory_config(config)
    if not mem["enabled"]:
        return "skipped (memory disabled)"
    if not fts5_available():
        return "skipped (sqlite3 lacks FTS5)"
    try:
        vault_path = vault_path_from(config)
    except ValueError:
        return "skipped (vault_path not configured yet)"
    if not vault_path.is_dir():
        raise RuntimeError(
            f"vault_path is unavailable or not a directory: {vault_path}. "
            "Restore access or correct vault_path in config.toml, then rerun migration."
        )

    db_path = db_path_for_vault(vault_path, mem["db_dir"])
    full = not db_path.exists()
    stats = update_index(config, full=full, quiet=True)
    verb = "built" if full else "refreshed"
    return f"{verb}: {stats['total']} notes ({stats['db']})"


def main() -> int:
    config_path = PROJECT_ROOT / "config.toml"

    print("== Migrate: config ==")
    state = ensure_memory_section(config_path)
    if state == "added":
        print("config.toml: [memory] section added")
    elif state == "present":
        print("config.toml: [memory] section already present")
    else:
        print("config.toml: not found — skipping (install.sh creates it)")

    print("== Migrate: FTS5 memory index ==")
    if state == "no-config":
        print("index: skipped (no config)")
        return 0
    config = load_config(strict=False)
    try:
        print(f"index: {ensure_index(config)}")
    except Exception as exc:  # noqa: BLE001 — migration must report, not crash
        print(f"index: FAILED ({exc})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
