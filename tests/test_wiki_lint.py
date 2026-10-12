"""Tests for scripts/wiki_lint.py — read-only structural checks."""

from pathlib import Path

import pytest

from scripts.wiki_lint import discover_spaces, lint_space
from scripts.wiki_compile import materialize_to_staging, snapshot_wiki_space, validate_changeset
from scripts.wiki_models import ChangeSet, WikiPage


# ── Fixture helpers ──────────────────────────────────────────────────────────


def _write(path: Path, frontmatter: dict, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    path.write_text("\n".join(lines), encoding="utf-8")


def _good_fm(slug: str, page_type: str, source_stem: str) -> dict:
    return {
        "note_type": "wiki",
        "wiki_project": slug,
        "wiki_page_type": page_type,
        "wiki_status": "draft",
        "date": "2026-05-15",
        "source_doc": f"wiki:{slug}:{page_type}:{source_stem}",
    }


@pytest.fixture
def project_space(tmp_path: Path) -> Path:
    """A minimally valid project-mode wiki-space with all core pages."""
    slug = "demo"
    root = tmp_path / slug
    _write(root / "SCHEMA.md", {"note_type": "wiki", "wiki_project": slug,
                                  "wiki_page_type": "meta", "wiki_status": "stable",
                                  "date": "2026-05-15", "wiki_mode": "project",
                                  "source_doc": f"wiki:{slug}:meta:SCHEMA"})
    _write(root / "index.md", {"note_type": "wiki", "wiki_project": slug,
                                 "wiki_page_type": "meta", "wiki_status": "stable",
                                 "date": "2026-05-15",
                                 "source_doc": f"wiki:{slug}:meta:index"},
           body="# Index\n")
    _write(root / "log.md", {"note_type": "wiki", "wiki_project": slug,
                               "wiki_page_type": "meta", "wiki_status": "stable",
                               "date": "2026-05-15",
                               "source_doc": f"wiki:{slug}:meta:log"})
    for core in (
        "overview",
        "architecture",
        "components",
        "workflows",
        "goals-and-roadmap",
        "glossary",
        "open-questions",
    ):
        _write(root / "pages" / f"{core}.md", _good_fm(slug, "core", core), body=f"# {core}\n")
    return root


# ── Happy path ────────────────────────────────────────────────────────────────


def test_minimal_valid_project_space_passes(project_space: Path) -> None:
    issues = lint_space(project_space)
    # index.md INDEX_STALE is expected because we did not list the core pages.
    # Filter to just confirm there are no structural failures other than that.
    non_index = [i for i in issues if i.code != "INDEX_STALE"]
    assert non_index == [], non_index


# ── Missing meta / core pages ────────────────────────────────────────────────


def test_missing_meta_pages_reported(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    root.mkdir()
    issues = lint_space(root)
    codes = [i.code for i in issues]
    assert "META_MISSING" in codes


def test_project_mode_missing_core_pages(project_space: Path) -> None:
    (project_space / "pages" / "architecture.md").unlink()
    issues = lint_space(project_space)
    msgs = [i.message for i in issues if i.code == "CORE_PAGE_MISSING"]
    assert any("architecture" in m for m in msgs)


def test_corpus_mode_does_not_require_core_pages(tmp_path: Path) -> None:
    slug = "demo"
    root = tmp_path / slug
    _write(root / "SCHEMA.md", {"note_type": "wiki", "wiki_project": slug,
                                  "wiki_page_type": "meta", "wiki_status": "stable",
                                  "date": "2026-05-15", "wiki_mode": "corpus",
                                  "source_doc": f"wiki:{slug}:meta:SCHEMA"})
    _write(root / "index.md", {"note_type": "wiki", "wiki_project": slug,
                                 "wiki_page_type": "meta", "wiki_status": "stable",
                                 "date": "2026-05-15",
                                 "source_doc": f"wiki:{slug}:meta:index"})
    _write(root / "log.md", {"note_type": "wiki", "wiki_project": slug,
                               "wiki_page_type": "meta", "wiki_status": "stable",
                               "date": "2026-05-15",
                               "source_doc": f"wiki:{slug}:meta:log"})
    issues = lint_space(root)
    assert not [i for i in issues if i.code == "CORE_PAGE_MISSING"]


# ── Frontmatter checks ───────────────────────────────────────────────────────


def test_wrong_note_type_reported(project_space: Path) -> None:
    bad = project_space / "entities" / "wrong.md"
    fm = _good_fm("demo", "entity", "wrong")
    fm["note_type"] = "atomic"
    _write(bad, fm, body="# Wrong\n")
    issues = lint_space(project_space)
    assert any(i.code == "WRONG_NOTE_TYPE" for i in issues)


def test_invalid_page_type_reported(project_space: Path) -> None:
    bad = project_space / "entities" / "bad.md"
    fm = _good_fm("demo", "entity", "bad")
    fm["wiki_page_type"] = "bogus"
    _write(bad, fm, body="# Bad\n")
    issues = lint_space(project_space)
    assert any(i.code == "INVALID_PAGE_TYPE" for i in issues)


def test_wrong_project_slug_reported(project_space: Path) -> None:
    bad = project_space / "entities" / "stray.md"
    fm = _good_fm("other-project", "entity", "stray")
    _write(bad, fm, body="# Stray\n")
    issues = lint_space(project_space)
    assert any(i.code == "WRONG_PROJECT_SLUG" for i in issues)


def test_invalid_source_doc_reported(project_space: Path) -> None:
    bad = project_space / "entities" / "weird.md"
    fm = _good_fm("demo", "entity", "weird")
    fm["source_doc"] = "Some.docx"
    _write(bad, fm, body="# Weird\n")
    issues = lint_space(project_space)
    assert any(i.code == "INVALID_SOURCE_DOC" for i in issues)


def test_invalid_confidence_reported(project_space: Path) -> None:
    bad = project_space / "entities" / "shaky.md"
    fm = _good_fm("demo", "entity", "shaky")
    fm["confidence"] = "uncertain"
    _write(bad, fm, body="# Shaky\n")
    issues = lint_space(project_space)
    assert any(i.code == "INVALID_CONFIDENCE" for i in issues)


# ── Wikilinks ────────────────────────────────────────────────────────────────


def test_unresolved_wikilink_reported(project_space: Path) -> None:
    bad = project_space / "entities" / "linker.md"
    _write(bad, _good_fm("demo", "entity", "linker"),
           body="# Linker\n\nSee [[missing-target]] for context.")
    issues = lint_space(project_space)
    assert any(i.code == "UNRESOLVED_WIKILINK" for i in issues)


def test_open_question_marker_is_allowed(project_space: Path) -> None:
    page = project_space / "entities" / "questioner.md"
    _write(page, _good_fm("demo", "entity", "questioner"),
           body="# Questioner\n\nNeed [[?future-page]] later.")
    issues = lint_space(project_space)
    assert not [i for i in issues if i.code == "UNRESOLVED_WIKILINK"]


def test_wikilink_to_existing_stem_resolves(project_space: Path) -> None:
    page = project_space / "entities" / "linker.md"
    _write(page, _good_fm("demo", "entity", "linker"),
           body="# Linker\n\n[[overview]] is a core page.")
    issues = lint_space(project_space)
    assert not [i for i in issues if i.code == "UNRESOLVED_WIKILINK"]


@pytest.mark.parametrize("target", [
    "entities/postgres", "entities/postgres.md",
    "{prefix}/entities/postgres", "{prefix}/entities/postgres.md#Details|Postgres",
    "postgres.md", "postgres.md#Details", "postgres.md|Postgres",
    "postgres.md#Details|Postgres",
])
def test_compiler_and_linter_agree_on_path_links(project_space: Path, target: str) -> None:
    _write(project_space / "entities/postgres.md", _good_fm("demo", "entity", "postgres"),
           body="# Postgres\n")
    target = target.format(prefix=f"{project_space.parent.name}/demo")
    cs = ChangeSet(project="demo", compile_id="x", creates=[WikiPage(
        rel_path="entities/linker.md", frontmatter=_good_fm("demo", "entity", "linker"),
        body=f"# Linker\n\n[[{target}]]",
    )])
    validate_changeset(cs, snapshot_wiki_space(project_space))
    materialize_to_staging(cs, project_space)
    assert not [i for i in lint_space(project_space) if i.code == "UNRESOLVED_WIKILINK"]


@pytest.mark.parametrize("target", [
    "entities/missing", "{folder}/other/entities/postgres",
    "{folder}/demo/../other/entities/postgres", "../entities/postgres",
    "missing.md", "{folder}/other/postgres.md", "{folder}/other/entities/postgres.md",
])
def test_linter_rejects_missing_and_foreign_path_links(project_space: Path, target: str) -> None:
    _write(project_space / "entities/postgres.md", _good_fm("demo", "entity", "postgres"),
           body="# Postgres\n")
    target = target.format(folder=project_space.parent.name)
    _write(project_space / "entities/linker.md", _good_fm("demo", "entity", "linker"),
           body=f"# Linker\n\n[[{target}]]")
    assert [i for i in lint_space(project_space) if i.code == "UNRESOLVED_WIKILINK"]


# ── Duplicate entities ───────────────────────────────────────────────────────


def test_duplicate_entity_reported(project_space: Path) -> None:
    _write(project_space / "entities" / "postgres.md",
           _good_fm("demo", "entity", "postgres"), body="# Postgres\n")
    _write(project_space / "entities" / "postgres-2.md",
           _good_fm("demo", "entity", "postgres-2"), body="# postgres\n")
    issues = lint_space(project_space)
    assert any(i.code == "DUPLICATE_ENTITY" for i in issues)


# ── Raw layout ───────────────────────────────────────────────────────────────


def test_invalid_raw_kind_reported(project_space: Path) -> None:
    bad = project_space / "raw" / "bogus" / "x.md"
    _write(bad, _good_fm("demo", "raw", "x"), body="# X\n")
    issues = lint_space(project_space)
    assert any(i.code == "INVALID_RAW_KIND" for i in issues)


def test_raw_kind_mismatch_reported(project_space: Path) -> None:
    page = project_space / "raw" / "docs" / "mismatch.md"
    fm = _good_fm("demo", "raw", "mismatch")
    fm["raw_kind"] = "articles"  # but it lives under raw/docs/
    _write(page, fm, body="# Mismatch\n")
    issues = lint_space(project_space)
    assert any(i.code == "RAW_KIND_MISMATCH" for i in issues)


def test_raw_underscore_files_are_exempt(project_space: Path) -> None:
    """raw/_README.md is documentation, not a raw note."""
    readme = project_space / "raw" / "_README.md"
    _write(readme, {"note_type": "wiki", "wiki_project": "demo",
                     "wiki_page_type": "meta", "wiki_status": "stable",
                     "date": "2026-05-15", "source_doc": "wiki:demo:meta:raw-readme"},
           body="# Raw layer README\n")
    issues = lint_space(project_space)
    assert not [i for i in issues if i.code == "RAW_KIND_MISSING"]


def test_wikilinks_inside_code_are_ignored(project_space: Path) -> None:
    """Documentation prose like `[[wikilink]]` must not become a real link."""
    page = project_space / "entities" / "doc-page.md"
    body = (
        "# Doc page\n\n"
        "Talking about `[[wikilinks]]` as a concept.\n\n"
        "```markdown\n"
        "[[fenced-example]]\n"
        "```\n"
    )
    _write(page, _good_fm("demo", "entity", "doc-page"), body=body)
    issues = lint_space(project_space)
    assert not [i for i in issues if i.code == "UNRESOLVED_WIKILINK"], (
        "wikilinks inside backticks/fences should be invisible to the linter"
    )


# ── discover_spaces ──────────────────────────────────────────────────────────


def test_discover_spaces_filters_invalid_slugs(tmp_path: Path) -> None:
    (tmp_path / "valid-slug").mkdir()
    (tmp_path / "Another").mkdir()  # uppercase — invalid slug
    (tmp_path / "spaced name").mkdir()
    found = [p.name for p in discover_spaces(tmp_path)]
    assert "valid-slug" in found
    assert "Another" not in found
    assert "spaced name" not in found


def test_discover_spaces_missing_root_returns_empty(tmp_path: Path) -> None:
    assert discover_spaces(tmp_path / "does-not-exist") == []
