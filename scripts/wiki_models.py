"""wiki_models.py — Dataclasses and constants for the LLM Wiki contour.

Pure module: no I/O, no LLM calls. Holds the ChangeSet protocol that
wiki_compile.py emits/consumes and the constants that wiki_lint.py and
vault_writer.py both reference.

The ChangeSet is the contract between the LLM and the rest of the pipeline.
Anything LLM produces that does not parse to a valid ChangeSet is rejected
before it ever touches the vault.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ── Note-type contour ─────────────────────────────────────────────────────────

WIKI_NOTE_TYPE = "wiki"

WIKI_PAGE_TYPES: tuple[str, ...] = (
    "core",
    "entity",
    "concept",
    "comparison",
    "query",
    "readout",
    "raw",
    "meta",
)

WIKI_STATUSES: tuple[str, ...] = (
    "stub",
    "draft",
    "stable",
    "stale",
    "contradicted",
    "ingested",
)

WIKI_CONFIDENCES: tuple[str, ...] = ("high", "medium", "low")

WIKI_MODES: tuple[str, ...] = ("project", "corpus")

WIKI_RAW_KINDS: tuple[str, ...] = ("articles", "docs", "transcripts", "assets")

# Core pages that project mode requires (created as stubs at init).
CORE_PAGES: tuple[str, ...] = (
    "overview",
    "architecture",
    "components",
    "workflows",
    "goals-and-roadmap",
    "glossary",
    "open-questions",
)

# Meta-pages that live at the root of the wiki-space.
META_PAGES: tuple[str, ...] = ("SCHEMA", "index", "log")

REQUIRED_FRONTMATTER: tuple[str, ...] = (
    "note_type",
    "wiki_project",
    "wiki_page_type",
    "wiki_status",
    "date",
)

# Slug pattern for project names and page stems: kebab-case ASCII.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


# ── Helpers ────────────────────────────────────────────────────────────────────


def is_valid_slug(value: str) -> bool:
    return bool(SLUG_RE.match(value or ""))


def synth_source_doc(slug: str, page_type: str, stem: str) -> str:
    """Synthetic source_doc for a wiki page.

    Format: ``wiki:<slug>:<page_type>:<stem>``. Guarantees that the existing
    processed.json registry can dedup wiki pages without colliding with
    real imported documents.
    """
    return f"wiki:{slug}:{page_type}:{stem}"


SOURCE_DOC_RE = re.compile(r"^wiki:[a-z0-9-]+:[a-z]+:[^/]+$")


def is_valid_wiki_source_doc(value: str) -> bool:
    return bool(SOURCE_DOC_RE.match(value or ""))


def resolves_wikilink(target: str, known_names: set[str], known_paths: set[str],
                      wiki_prefix: str = "") -> bool:
    """Resolve names and paths inside one wiki-space."""
    return (target in known_names
            or target.removesuffix(".md") in known_names
            or target.removeprefix(wiki_prefix).removesuffix(".md") in known_paths)


# ── ChangeSet primitives ───────────────────────────────────────────────────────


@dataclass(slots=True)
class WikiPage:
    """A page being created in this compile run."""

    rel_path: str
    frontmatter: dict[str, Any]
    body: str
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rel_path": self.rel_path,
            "frontmatter": self.frontmatter,
            "body": self.body,
            "sources": list(self.sources),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WikiPage":
        return cls(
            rel_path=str(data["rel_path"]),
            frontmatter=dict(data.get("frontmatter") or {}),
            body=str(data.get("body") or ""),
            sources=list(data.get("sources") or []),
        )


@dataclass(slots=True)
class WikiPageUpdate:
    """A merge into an existing page.

    `expected_existing_links` carries the wikilinks the snapshot saw on disk
    before the LLM was prompted. The validator hard-fails if any of them are
    missing from `body` after the update — same guard as
    process_contacts.validate_contacts_result(), generalized to N pages.
    """

    rel_path: str
    expected_existing_links: list[str]
    frontmatter: dict[str, Any]
    body: str
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rel_path": self.rel_path,
            "expected_existing_links": list(self.expected_existing_links),
            "frontmatter": self.frontmatter,
            "body": self.body,
            "sources": list(self.sources),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WikiPageUpdate":
        return cls(
            rel_path=str(data["rel_path"]),
            expected_existing_links=list(data.get("expected_existing_links") or []),
            frontmatter=dict(data.get("frontmatter") or {}),
            body=str(data.get("body") or ""),
            sources=list(data.get("sources") or []),
        )


@dataclass(slots=True)
class OpenQuestion:
    text: str
    raised_in: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "raised_in": self.raised_in}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OpenQuestion":
        return cls(text=str(data["text"]), raised_in=str(data.get("raised_in") or ""))


@dataclass(slots=True)
class Contradiction:
    page_a: str
    page_b: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {"page_a": self.page_a, "page_b": self.page_b, "summary": self.summary}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Contradiction":
        return cls(
            page_a=str(data["page_a"]),
            page_b=str(data["page_b"]),
            summary=str(data.get("summary") or ""),
        )


@dataclass(slots=True)
class LogEntry:
    summary: str
    raws_consumed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "raws_consumed": list(self.raws_consumed)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LogEntry":
        return cls(
            summary=str(data.get("summary") or ""),
            raws_consumed=list(data.get("raws_consumed") or []),
        )


@dataclass(slots=True)
class ChangeSet:
    """Root object that wiki_compile.py validates and applies.

    The LLM emits this as JSON. `parse_changeset()` checks shape only; full
    semantic validation against the existing snapshot lives in
    wiki_compile.validate_changeset() so this module stays pure.
    """

    project: str
    compile_id: str
    creates: list[WikiPage] = field(default_factory=list)
    updates: list[WikiPageUpdate] = field(default_factory=list)
    renames: list[dict[str, str]] = field(default_factory=list)
    open_questions: list[OpenQuestion] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    log_entry: LogEntry = field(default_factory=lambda: LogEntry(summary=""))

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "compile_id": self.compile_id,
            "creates": [c.to_dict() for c in self.creates],
            "updates": [u.to_dict() for u in self.updates],
            "renames": list(self.renames),
            "open_questions": [q.to_dict() for q in self.open_questions],
            "contradictions": [c.to_dict() for c in self.contradictions],
            "log_entry": self.log_entry.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChangeSet":
        return cls(
            project=str(data["project"]),
            compile_id=str(data["compile_id"]),
            creates=[WikiPage.from_dict(d) for d in data.get("creates") or []],
            updates=[WikiPageUpdate.from_dict(d) for d in data.get("updates") or []],
            renames=[dict(r) for r in data.get("renames") or []],
            open_questions=[OpenQuestion.from_dict(d) for d in data.get("open_questions") or []],
            contradictions=[Contradiction.from_dict(d) for d in data.get("contradictions") or []],
            log_entry=LogEntry.from_dict(data.get("log_entry") or {}),
        )


# ── Shape-level validation (semantic checks live in wiki_compile) ──────────────


class ChangeSetShapeError(ValueError):
    """Raised when a dict cannot be parsed into a ChangeSet."""


def parse_changeset(data: Any) -> ChangeSet:
    """Strict parse: structure errors raise ChangeSetShapeError with a path."""
    if not isinstance(data, dict):
        raise ChangeSetShapeError("ChangeSet root must be a JSON object")

    for key in ("project", "compile_id"):
        if key not in data or not isinstance(data[key], str) or not data[key]:
            raise ChangeSetShapeError(f"ChangeSet missing required string field '{key}'")

    for list_key in ("creates", "updates", "renames", "open_questions", "contradictions"):
        if list_key in data and not isinstance(data[list_key], list):
            raise ChangeSetShapeError(f"ChangeSet field '{list_key}' must be a list")

    for i, entry in enumerate(data.get("creates") or []):
        _require_page_fields(entry, f"creates[{i}]", required=("rel_path", "frontmatter", "body"))
    for i, entry in enumerate(data.get("updates") or []):
        _require_page_fields(
            entry,
            f"updates[{i}]",
            required=("rel_path", "expected_existing_links", "frontmatter", "body"),
        )
        if not isinstance(entry["expected_existing_links"], list):
            raise ChangeSetShapeError(
                f"updates[{i}].expected_existing_links must be a list"
            )

    return ChangeSet.from_dict(data)


def _require_page_fields(entry: Any, where: str, required: tuple[str, ...]) -> None:
    if not isinstance(entry, dict):
        raise ChangeSetShapeError(f"{where} must be an object")
    missing = [k for k in required if k not in entry]
    if missing:
        raise ChangeSetShapeError(f"{where} missing fields: {missing}")
    if not isinstance(entry["frontmatter"], dict):
        raise ChangeSetShapeError(f"{where}.frontmatter must be an object")
    if not isinstance(entry.get("body", ""), str):
        raise ChangeSetShapeError(f"{where}.body must be a string")
