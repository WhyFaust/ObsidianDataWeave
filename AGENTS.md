# ObsidianDataWeave Agent Contract

## Purpose
This repository converts source `.docx` documents and existing Obsidian notes into Zettelkasten-style notes with MOC structure.

Agents should treat this file as the canonical integration contract for both Claude Code and Codex.

## Supported Workflows
1. Process a source document into atomic notes and MOC:
   `python3 scripts/process.py "Document.docx"`
   Safe automation form:
   `python3 scripts/process.py "Document.docx" --non-interactive --on-conflict skip`
2. Process a curated NotebookLM notebook into atomic notes and MOC:
   `python3 scripts/process_notebook.py "<notebook_id>"`
   Safe automation form:
   `python3 scripts/process_notebook.py "<notebook_id>" --non-interactive --on-conflict skip`
   Optional inputs: `--include-sources`, `--include-mindmap`, `--profile <name>`.
3. Process an existing personal note in the vault:
   `python3 scripts/process_note.py "Note Title"`
   Safe automation form:
   `python3 scripts/process_note.py "Note Title" --mode atomize --non-interactive --on-conflict skip`
4. Process a contacts/networking note into individual contact cards:
   `python3 scripts/process_contacts.py "Contacts Note"`
   Safe automation form:
   `python3 scripts/process_contacts.py "Contacts Note" --non-interactive --on-conflict skip`
5. Generate markdown files from an existing atom plan JSON:
   `python3 scripts/generate_notes.py /path/to/atom-plan.json`
6. Copy staged markdown files into the vault:
   `python3 scripts/vault_writer.py --staging /path/to/staging --atom-plan /path/to/atom-plan.json`
7. Find duplicate note candidates or run semantic dedup:
   `python3 scripts/dedup_vault.py --dry-run`
8. Run environment checks before operating on the vault:
   `python3 scripts/doctor.py`
9. Run deep research directly into a NotebookLM notebook (bypasses the upstream
   CLI retry duplication bug, see "Why research_notebook.py exists" below):
   `python3 scripts/research_notebook.py run "<notebook_id>" "<query>"`
   Safe automation form:
   `python3 scripts/research_notebook.py run "<notebook_id>" "<query>" --non-interactive`
   Dry-run preview of what would be imported:
   `python3 scripts/research_notebook.py run "<notebook_id>" "<query>" --dry-run`
10. Clean up duplicate/error sources in an existing NotebookLM notebook:
    `python3 scripts/research_notebook.py dedupe "<notebook_id>" --dry-run`
    Safe automation form:
    `python3 scripts/research_notebook.py dedupe "<notebook_id>" --include-error --non-interactive`
11. Initialize a new LLM Wiki space:
    `python3 scripts/wiki_init.py <slug> --mode project --title "Project"`
    Modes: `project` (fixed core pages) or `corpus` (entities-only).
    Add `--lang ru` (or `--lang en`) to pick template language; defaults to
    `[wiki].default_lang` in `config.toml` (`en` if unset).
12. Ingest raw inputs into a wiki-space:
    `python3 scripts/wiki_ingest.py <slug> <file-or-dir> --kind {articles|docs|transcripts|assets}`
13. Compile a wiki-space (LLM merges raw into pages):
    `python3 scripts/wiki_compile.py <slug> --since-last-compile`
    Safe automation form:
    `python3 scripts/wiki_compile.py <slug> --since-last-compile --on-conflict overwrite`
14. Update one page from a single new raw input (incremental merge):
    `python3 scripts/wiki_update.py <slug> raw/docs/<file>.md`
15. Lint wiki-space integrity:
    `python3 scripts/wiki_lint.py [<slug>] [--strict]`
16. Search the FTS5 vault memory (lexical full-text over every note):
    `python3 scripts/memory_index.py search "<query>" --json`
    Useful flags: `--limit N`, `--prefix` (last term as prefix), `--folder X`,
    `--tag Y`, `--raw` (raw FTS5 syntax). The index updates automatically
    after each vault_writer write ([memory].auto_update).
17. Build or refresh the memory index / run the upgrade migration:
    `python3 scripts/memory_index.py build` | `update` | `status`
    `python3 scripts/migrate.py`  (idempotent: adds [memory] config, builds index)

## Memory protocol (MUST)

The FTS5 vault memory (`scripts/memory_index.py`) is the agent's recall layer.
It is **not** automatic end-to-end: the first build is explicit, and search
only helps if you actually run it. Follow this protocol — do not treat memory
as optional.

1. **Ensure the index exists.** On a new setup, after `git pull`, or whenever
   unsure, run `python3 scripts/memory_index.py status`. If it reports
   `exists: false`, build it once: `python3 scripts/memory_index.py build`
   (or `python3 scripts/migrate.py`, which builds it idempotently). The index
   does **not** self-create on the first vault write — `vault_writer` only
   refreshes an index that already exists and prints a `NOTE:` hint to stderr
   when it is missing.
2. **Search before you answer or write.** Before answering any question about
   vault / wiki content, and before `wiki_compile.py` / `wiki_update.py` (to
   avoid duplicating existing knowledge), first run
   `python3 scripts/memory_index.py search "<query>" --json`. Prefer recall
   over guessing from memory.
3. **Self-heal on miss.** If a search raises `index not built yet`, run
   `python3 scripts/memory_index.py build`, then retry the search.

After a build, `[memory].auto_update` keeps the index fresh on every
`vault_writer` write — no manual refresh is needed during normal operation.

## Workflow Mapping
Common user intent -> command:

- "process/import this .docx" -> `python3 scripts/process.py "<file>.docx"`
- "process/import this .docx without prompts" -> `python3 scripts/process.py "<file>.docx" --non-interactive --on-conflict skip`
- "process notebook" / "обработай ноутбук" / "pull from NotebookLM" -> `python3 scripts/process_notebook.py "<notebook_id>"`
- "process notebook with sources" -> `python3 scripts/process_notebook.py "<notebook_id>" --include-sources`
- "process notebook without prompts" -> `python3 scripts/process_notebook.py "<notebook_id>" --non-interactive --on-conflict skip`
- "fetch notebook notes only" (no atomization) -> `python3 scripts/fetch_notebook.py "<notebook_id>"`
- "process/enrich/atomize this note" -> `python3 scripts/process_note.py "<note title or path>"`
- "process contacts" / "обработай контакты" -> `python3 scripts/process_contacts.py "<note title or path>"`
- "atomize this note without prompts" -> `python3 scripts/process_note.py "<note title or path>" --mode atomize --non-interactive --on-conflict skip`
- "show duplicate candidates" -> `python3 scripts/dedup_vault.py --dry-run --skip-claude`
- "run full dedup review" -> `python3 scripts/dedup_vault.py`
- "write staged notes without prompts" -> `python3 scripts/vault_writer.py --staging "<dir>" --atom-plan "<plan.json>" --non-interactive --on-conflict skip`
- "run dedup without prompts" -> `python3 scripts/dedup_vault.py --non-interactive --decision skip`
- "render markdown from atom plan" -> `python3 scripts/generate_notes.py "<plan.json>"`
- "check setup/prereqs" -> `python3 scripts/doctor.py`
- "run deep research in notebook" / "запусти ресерч в ноутбук" / "deep research into notebook" -> `python3 scripts/research_notebook.py run "<notebook_id>" "<query>"`
- "dry-run research import" -> `python3 scripts/research_notebook.py run "<notebook_id>" "<query>" --dry-run`
- "dedupe notebook sources" / "почисти дубли источников в ноутбуке" -> `python3 scripts/research_notebook.py dedupe "<notebook_id>" --dry-run`
- "clean up broken research import" -> `python3 scripts/research_notebook.py dedupe "<notebook_id>" --include-error --non-interactive`
- "init wiki" / "создай вики <slug>" -> `python3 scripts/wiki_init.py <slug> --mode project --title "<title>"` (+ `--lang ru|en` if user specifies language; otherwise `[wiki].default_lang` from `config.toml`)
- "ingest <path> в вики <slug>" / "залей в вики" -> `python3 scripts/wiki_ingest.py <slug> <path> --kind <kind>`
- "compile wiki" / "собери вики <slug>" -> `python3 scripts/wiki_compile.py <slug> --since-last-compile`
- "update wiki page" / "обнови вики <slug> <raw-path>" -> `python3 scripts/wiki_update.py <slug> raw/docs/<file>.md`
- "lint wiki" / "проверь вики" -> `python3 scripts/wiki_lint.py [<slug>] --strict`
- "search notes/vault" / "найди в заметках" / "what do we know about X" / "что мы знаем про X" / "вспомни" / "recall" -> `python3 scripts/memory_index.py search "<query>" --json`
- "rebuild/refresh memory" / "перестрой индекс памяти" / "memory status" -> `python3 scripts/memory_index.py build | update | status`

## Important Constraints
- `scripts/vault_writer.py` is the only script allowed to write generated note files into `vault_path`. This includes wiki pages — `wiki_compile.py` always invokes `vault_writer.py` as a subprocess.
- The LLM Wiki contour (`<vault>/<wiki_folder>/<slug>/`) is strictly isolated from atomic notes / MOCs / contacts. `wiki_compile.py` does **not** read atomic notes, and atomic processors do **not** read wiki pages. Crossing the boundary triggers `WIKI_WRITE_FORBIDDEN` from `vault_writer.py`.
- `wiki_compile.py` rejects any ChangeSet where an existing page lost a `[[wikilink]]` between snapshot and merge. Exit code 5, marker `WIKI_LINKS_LOST`. Never bypass with `--force` or by stripping `expected_existing_links` — fix the root cause in the prompt or the LLM output.
- `scripts/process.py`, `scripts/process_note.py`, and `scripts/process_notebook.py` rely on the local `claude` CLI (or `codex`) for the semantic rewrite step.
- `scripts/fetch_notebook.py` and `scripts/process_notebook.py` require `notebooklm-py` to be installed and an authenticated NotebookLM session (`notebooklm login`).
- Agents must prefer repo-local files over global home-directory files.
- `config.toml` is local, machine-specific state. Never overwrite it unless explicitly asked.
- `processed.json`, `dedup_reviewed.json`, staging artifacts, and vault contents are runtime state. Do not delete them unless explicitly asked.

## LLM Wiki

A separate, isolated knowledge contour. Lives at
`<vault>/<wiki_folder>/<slug>/` (default `wiki_folder = "LLM Wiki"`).
Each `<slug>/` is a self-contained wiki-space.

Three layers per wiki-space:

- **raw/** — immutable inputs (`articles/`, `docs/`, `transcripts/`,
  `assets/`). Added by `wiki_ingest.py`. Never modified by any script.
- **pages/ + entities/ + concepts/ + comparisons/ + queries/** —
  the compiled knowledge layer. `wiki_compile.py` reads raw + the
  existing snapshot, calls the LLM, and merges back via
  `vault_writer.py`. Existing `[[wikilinks]]` are preserved across
  passes (load-bearing safety property — `WIKI_LINKS_LOST` exit 5
  if violated).
- **SCHEMA.md / index.md / log.md** — meta layer. SCHEMA is frozen
  after init; index is regenerated each compile; log body is append-only.
  Its `compiled_raws` frontmatter records consumed raw fingerprints through
  the writer pass. Legacy inputs without a fingerprint remain pending;
  `--raw-only` permits intentional reprocessing.

Two modes (set at init via `--mode`):

- **project** — fixed core pages (overview, architecture, components,
  workflows, goals-and-roadmap, glossary, open-questions). Use for
  documenting a single coherent system.
- **corpus** — only entities/concepts grow as raw is added. Use for
  reading-list-style or rule-set knowledge bases without a fixed
  centre.

Template language: `wiki_init.py` ships templates in `en` and `ru`.
Pick per-invocation with `--lang ru|en`, or set `[wiki].default_lang`
in `config.toml` (falls back to `en`). Choice only affects on-disk
prose of meta files and core-page stubs — structure, frontmatter
contract, and pipeline behavior are language-agnostic.

Typical workflow:

```
wiki_init.py <slug> --mode {project|corpus} --title "<title>"
wiki_ingest.py <slug> path/to/raw --kind {articles|docs|transcripts|assets} --no-compile
wiki_compile.py <slug> --since-last-compile
wiki_lint.py <slug> --strict
```

The LLM-side contract for compile is in `rules/wiki_compile.md`. The
on-disk page contract (frontmatter, page_types, statuses) is in
`rules/wiki_schema.md`. Incremental-merge semantics for
`wiki_update.py` are in `rules/wiki_update.md`. Read these before any
work that touches a wiki-space — they are authoritative over this
overview.

## Required Local Files
- `config.toml`: local runtime configuration (now includes `[wiki]` section)
- `tags.yaml`: canonical taxonomy for atomic notes
- `wiki_tags.yaml`: separate tag whitelist for the LLM Wiki contour
- `rules/atomization.md`: note-splitting rules
- `rules/taxonomy.md`: tags, MOC, wikilink rules
- `rules/personal_notes.md`: personal note rules
- `rules/contacts.md`: contact note rules
- `rules/wiki_schema.md`: on-disk contract for every wiki page
- `rules/wiki_compile.md`: ChangeSet shape and compile-time LLM contract
- `rules/wiki_update.md`: incremental-merge guidance for `wiki_update.py`
- `templates/wiki/`: SCHEMA / index / log / raw README / 7 core page stubs
- `SKILL.md`: Claude-facing adapter over this contract
- `SKILL_PERSONAL.md`: prompt header for personal note processing
- `SKILL_CONTACTS.md`: prompt header for contact note processing

## CLI Contracts
- `scripts/process.py`
  - Input: `.docx` filename or atom plan JSON with `--from-plan`
  - Safe automation flags for final vault writes: `--non-interactive --on-conflict skip|overwrite`
  - Output: summary to stdout, diagnostics to stderr
- `scripts/process_note.py`
  - Input: note title, filename, or absolute path
  - Safe automation flags for atomize writes: `--non-interactive --on-conflict skip|overwrite`
  - Output: writes updated/generated notes into the vault
- `scripts/process_contacts.py`
  - Input: note title, filename, or absolute path (containing contacts)
  - Safe automation flags: `--non-interactive --on-conflict skip|overwrite`
  - Output: writes individual contact notes + MOC to vault
- `scripts/generate_notes.py`
  - Input: atom plan JSON
  - Output: staging directory path to stdout
- `scripts/vault_writer.py`
  - Input: `--staging`, optional `--atom-plan`
  - Safe automation flags: `--non-interactive --on-conflict skip|overwrite`
  - Output: summary to stdout and stderr
- `scripts/dedup_vault.py`
  - Input: vault notes from configured vault path
  - Safe automation flags: `--non-interactive --decision merge|keep|skip`
  - Output: diagnostics to stderr, updates vault on confirmed merges
- `scripts/research_notebook.py`
  - Input: `run <notebook_id> "<query>"` or `dedupe <notebook_id>`
  - `run` flags: `--mode fast|deep` (default deep), `--source web|drive`, `--max-sources N`, `--poll-interval N`, `--poll-timeout N`, `--profile NAME`, `--dry-run`, `--non-interactive`
  - `dedupe` flags: `--key auto|url|title`, `--include-error`, `--dry-run`, `--non-interactive`, `--profile NAME`
  - Behavior: drives `notebooklm-py` Python API directly, so IMPORT_RESEARCH is a one-shot call with no retry-on-timeout duplication. Dedupe subcommand groups existing sources by URL (or title) and deletes everything except the first occurrence per group, optionally also removing sources in error state.
  - Output: progress + summary on stderr; dry-run plan or empty-plan JSON on stdout
- `scripts/wiki_init.py`
  - Input: `<slug>` plus `--mode {project|corpus} --title --description --force --non-interactive`
  - Exit codes: 0 (created), 1 (bad args), 2 (`WIKI_ALREADY_EXISTS`)
  - Output: confirmation line on stdout; no LLM is called
- `scripts/wiki_ingest.py`
  - Input: `<slug> <file-or-dir-or-url>` plus `--kind {articles|docs|transcripts|assets}`, `--label`, `--no-compile`, `--backend`
  - Exit codes: 0, 1, 2 (`WIKI_PROJECT_NOT_FOUND`), 3 (`WIKI_INGEST_EMPTY`), 4
  - Behavior: writes one .md per input under `raw/<kind>/<date>-<slug>.md`; chains `wiki_compile.py --since-last-compile` unless `--no-compile`
- `scripts/wiki_compile.py`
  - Input: `<slug>` plus `--since-last-compile`, `--raw-only <glob>`, `--update-only`, `--dry-run`, `--on-conflict {skip|overwrite|rename|ask}`, `--backend {auto|claude|codex}`, `--timeout-seconds N`
  - Exit codes: 0, 1, 2 (`WIKI_PROJECT_NOT_FOUND`), 3 (`WIKI_VALIDATION_FAILED`), 4 (`WIKI_RAW_LIMIT_EXCEEDED`), 5 (`WIKI_LINKS_LOST`)
  - Behavior: snapshots existing wiki, calls LLM via `rewrite_backend`, validates ChangeSet, materializes pages into staging, subprocesses `vault_writer.py`. The wikilink-preservation guard (exit 5) is the load-bearing safety property — never bypass it.
- `scripts/wiki_update.py`
  - Input: `<slug> <path-in-raw>` plus any flags forwarded to `wiki_compile.py`
  - Behavior: convenience wrapper for `wiki_compile.py <slug> --raw-only <path> --update-only`
- `scripts/wiki_lint.py`
  - Input: optional `<slug>` plus `--json --strict`
  - Exit codes: 0 (clean), 1 (`WIKI_LINT_FAILED`)
  - Read-only structural checks: meta/core pages present, frontmatter complete, wikilinks resolve, entities not duplicated, raw layout valid

## Recommended Agent Behavior
- Start with `python3 scripts/doctor.py` if setup is uncertain.
- Use `--dry-run` modes before destructive or high-impact operations.
- Prefer `--non-interactive` plus an explicit conflict/decision policy when running from an agent.
- Quote filenames with spaces or Cyrillic characters.
- When a task is unclear, inspect the relevant script help first.

## NotebookLM Auth Handling
- NotebookLM "login state" is a file on disk (`~/.notebooklm/storage_state.json` + `~/.notebooklm/browser_profile/`). Every run re-reads it; there is no in-memory session the agent needs to refresh. Once the user has logged in on this machine, subsequent runs go through without any browser prompt.
- `fetch_notebook.py` and `process_notebook.py` perform a pre-flight auth check (`check_auth_or_exit()`) before opening any network clients.
- Both scripts exit with code `2` and emit `NOTEBOOKLM_AUTH_REQUIRED` on stderr when the user is not authenticated OR when `notebooklm-py` is missing entirely.
- The canonical flow uses a **project venv** (`.venv/`) — system pip is blocked by PEP 668 on Arch/Manjaro/Debian. `scripts/notebooklm_setup.py` auto-detects venv and skips `--user` when inside one.
- Agent contract when `NOTEBOOKLM_AUTH_REQUIRED` is observed:
  1. Tell the user that dependencies will be installed automatically, but the actual browser login has to happen in a separate terminal window (because `notebooklm login` needs a real TTY to read the `ENTER` keypress; running it from Claude Code's shell aborts with `Aborted!`).
  2. Ensure a venv exists (create with `python3 -m venv .venv` if missing) and run:
     `.venv/bin/python scripts/notebooklm_setup.py --skip-login`
     This installs `notebooklm-py[browser]` and Playwright Chromium into the venv. Safe to run repeatedly and safe to run from a non-TTY shell (login is skipped).
  3. Ask the user to open a separate terminal window in the repo directory and run:
     `.venv/bin/notebooklm login`
     Sign in to Google in the Chromium window, wait for the NotebookLM homepage, return to that terminal and press ENTER. The session persists at `~/.notebooklm/storage_state.json`.
  4. When the user confirms, retry the original `process_notebook.py <notebook_id>` command. The preflight should now pass silently.
  5. Do not manually chain `pip install`, `playwright install`, and `notebooklm login` — always go through the setup script for steps 1–2.
  6. If the setup script exits non-zero, relay its stderr to the user and stop — do not attempt ad-hoc recovery. Exit code `3` specifically means "stdin is not a TTY and login was requested" — always invoke with `--skip-login` from the agent's shell.

- `scripts/notebooklm_setup.py`
  - Input: none (flags: `--skip-login`, `--reinstall`)
  - Behavior: auto-detects venv vs system Python; uses `pip --user` only outside a venv; refuses to launch `notebooklm login` on a non-TTY stdin
  - Output: diagnostics to stderr; exit 0 on success, 1 on install/login failure, 2 on missing auth file after login, 3 on missing TTY when login is requested
  - Use this as the canonical entrypoint whenever `NOTEBOOKLM_AUTH_REQUIRED` is observed

- `scripts/fetch_notebook.py`
  - Input: NotebookLM `notebook_id`
  - Optional flags: `--include-sources`, `--include-mindmap`, `--profile <name>`, `-o <path>`
  - Output: parsed-JSON path to stdout (compatible with `atomize.py`); diagnostics to stderr
  - Prereq: `notebooklm-py` installed + `notebooklm login` completed

- `scripts/process_notebook.py`
  - Input: NotebookLM `notebook_id`
  - Optional flags: `--include-sources`, `--include-mindmap`, `--profile <name>`
  - Safe automation flags: `--non-interactive --on-conflict skip|overwrite`
  - Output: summary to stdout; runs the full fetch -> atomize -> generate -> write pipeline
  - Prereq: same as `fetch_notebook.py`, plus `claude`/`codex` CLI for the rewrite step

## Why research_notebook.py exists

The upstream `notebooklm-py` CLI command
`notebooklm source add-research "<query>" --mode deep --import-all`
wraps `client.research.import_sources()` in an exponential-backoff retry loop that kicks in on `RPCTimeoutError`. Each retry re-imports the full source list without deduping against what's already in the notebook, so a single IMPORT_RESEARCH RPC that times out N times leaves N× duplicates. We hit this concretely: 78 research sources, 4 retries, 392 imported sources instead of ~78. Tracked upstream as `teng-lin/notebooklm-py` issue #241 (open).

Upstream explicitly documents the escape hatch in `src/notebooklm/cli/helpers.py::import_with_retry`:

> This is intentionally CLI-only policy. Library consumers calling `client.research.import_sources()` directly still get one-shot behavior.

`scripts/research_notebook.py` takes that escape hatch. It drives the research flow through the `notebooklm-py` Python API, so IMPORT_RESEARCH is a single call with no silent retry — duplication literally cannot happen through this code path. The `dedupe` subcommand is the cleanup for notebooks already poisoned by the CLI bug.

**Agents must prefer `research_notebook.py run` over `notebooklm source add-research --import-all`** until the upstream bug is fixed.

## Validation Commands
- `pytest -q`
- `python3 scripts/process.py --help`
- `python3 scripts/process_note.py --help`
- `python3 scripts/process_notebook.py --help`
- `python3 scripts/fetch_notebook.py --help`
- `python3 scripts/dedup_vault.py --help`
- `python3 scripts/doctor.py`
