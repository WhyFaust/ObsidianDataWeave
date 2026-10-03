# Agent Usage

This document shows how Claude Code and Codex should operate on this repository.

For every command below, replace `python3` with `.venv/bin/python` on Linux/macOS
or `.venv\Scripts\python.exe` on Windows, and run from the repository directory.

## Canonical Flow
1. Read `AGENTS.md`.
2. Run `python3 scripts/doctor.py` if setup is uncertain.
3. Choose the matching local command.
4. Use `--dry-run` when available before making high-impact changes.
5. Use explicit non-interactive policies when the command may otherwise prompt.

## Intent To Command
- Import a `.docx` into the vault:
  `python3 scripts/process.py "Document.docx"`
- Import a `.docx` into the vault without prompts:
  `python3 scripts/process.py "Document.docx" --non-interactive --on-conflict skip`
- Rework a personal note:
  `python3 scripts/process_note.py "Note Title"`
- Rework a personal note in atomize mode without prompts:
  `python3 scripts/process_note.py "Note Title" --mode atomize --non-interactive --on-conflict skip`
- Only generate markdown from a prepared plan:
  `python3 scripts/generate_notes.py /path/to/atom-plan.json`
- Only write staged markdown to the vault:
  `python3 scripts/vault_writer.py --staging /path/to/staging --atom-plan /path/to/atom-plan.json`
- Only write staged markdown to the vault without prompts:
  `python3 scripts/vault_writer.py --staging /path/to/staging --atom-plan /path/to/atom-plan.json --non-interactive --on-conflict skip`
- Inspect duplicate candidates without changing files:
  `python3 scripts/dedup_vault.py --dry-run --skip-claude`
- Run dedup without prompts:
  `python3 scripts/dedup_vault.py --non-interactive --decision skip`

## Environment Expectations
- `config.toml` exists and points to a real Obsidian vault.
- The configured `claude` or `codex` CLI is available in `PATH` for semantic rewrites.
- `rclone` is available for `.docx` fetching.

## Local Wiki On Windows

Create a repo-local `config.toml` using `config.example.toml`. Set `vault_path`
to the parent Obsidian vault, for example `'C:/Users/<user>/Documents/Obsidian Vault'`,
and `[wiki].wiki_folder = 'LLM Wiki'`. Leave `[rclone].staging_dir = ''` for the
OS temp directory, or choose a directory outside the vault. Leave `[memory].db_dir = ''` to store the
FTS5 database in `~/.cache/obsidian-dataweave/`, outside the vault and repository.
Keep `enabled = true` and `auto_update = true`. `config.toml` is ignored by Git;
keep machine-specific paths and credentials out of the shared example.

From PowerShell:

```powershell
Set-Location 'C:\path\to\ObsidianDataWeave'
# Initial creation of the search database; this is not an application build.
.\.venv\Scripts\python.exe scripts/memory_index.py build
# Use update, rather than build, when an index already exists.
.\.venv\Scripts\python.exe scripts/memory_index.py update
```

Inspect the index and search a generic example space:

```powershell
.\.venv\Scripts\python.exe scripts/memory_index.py status
.\.venv\Scripts\python.exe scripts/memory_index.py search 'Wiki' --folder 'LLM Wiki/demo/pages'
```

The folder is relative to `vault_path`; use forward slashes in examples.
Windows backslashes and a trailing slash are accepted too. The folder filter
includes its subfolders. Choose a query word present in the target pages.

`vault_writer.py` and successful `wiki_ingest.py` runs refresh an existing index
when `auto_update` is enabled, including ingest with `--no-compile`. A missing
index produces a hint and is not built implicitly. A refresh failure warns
without failing the completed note write. Raw inputs are immutable: ingest
uses a new numeric suffix on collision, while the writer skips an existing raw
even with `--on-conflict overwrite`. Custom `--label` values must be ASCII
kebab-case slugs.

FTS5 indexing/search is local and needs no rclone, browser or LLM backend.
Wiki compilation needs a supported backend (`codex` or `claude`).

## Notes For Claude Code
- `SKILL.md` is a thin adapter over the repo-local contract.
- Optional registration in `~/.claude/CLAUDE.md` is handled by `install.py --mode claude`.
- The shared `install.py` bootstrap creates a project venv on Windows/macOS/Linux;
  use its printed interpreter for subsequent commands. Bash `install.sh` delegates
  to it. Copied global skill files are refreshed by rerunning the installer.

## Notes For Codex
- `AGENTS.md` is the primary integration surface.
- No global install is required to understand repository workflows.
- Prefer explicit no-prompt flags in tool runs so the agent never blocks on stdin.
