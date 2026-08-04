"""Deterministic version-consistency checker for release engineering.

Enforces that the version identity of a release is internally consistent. Today
the enforced relationship is:

    Git tag  ->  pyproject.toml [project].version

Because the public GET /version endpoint derives from the same pyproject.toml
value (via app/api/build_info.py), enforcing tag <-> pyproject transitively
guarantees tag <-> /version without importing any runtime module.

The module is structured as a registry of independent consistency checks so
future checks (e.g. CHANGELOG has a section for the version) can be added
without redesign. Pure and stdlib-only: no network, no runtime imports.

Usage:
    python scripts/check_version.py v1.2.4          # or refs/tags/v1.2.4
    python scripts/check_version.py                  # infer from GITHUB_REF

Exit code 0 when consistent, 1 otherwise.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# scripts/check_version.py -> scripts -> repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# Release tags are strict vMAJOR.MINOR.PATCH. Prerelease/build metadata is
# intentionally out of scope until the release process needs it.
_TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")


@dataclass(frozen=True)
class CheckOutcome:
    label: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class VersionContext:
    """Shared, pre-resolved inputs handed to every consistency check."""

    tag: str | None
    tag_version: str | None
    pyproject_version: str | None
    parse_error: str


def normalize_ref(ref: str | None) -> str | None:
    """Accept 'refs/tags/v1.2.4', 'v1.2.4', or None -> bare tag or None."""
    if not ref:
        return None
    ref = ref.strip()
    prefix = "refs/tags/"
    if ref.startswith(prefix):
        ref = ref[len(prefix) :]
    return ref or None


def parse_tag_version(tag: str | None) -> tuple[str | None, str]:
    """Return (version, error). version is None when the tag is missing/malformed."""
    if tag is None:
        return None, "no tag provided (pass a tag or set GITHUB_REF)"
    m = _TAG_RE.match(tag)
    if not m:
        return None, f"tag '{tag}' is not a valid release tag (expected vMAJOR.MINOR.PATCH)"
    return m.group("version"), ""


def read_pyproject_version() -> str | None:
    try:
        import tomllib

        data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
        return str(data["project"]["version"])
    except (OSError, KeyError, ValueError):
        return None


def build_context(ref: str | None) -> VersionContext:
    tag = normalize_ref(ref)
    tag_version, parse_error = parse_tag_version(tag)
    return VersionContext(
        tag=tag,
        tag_version=tag_version,
        pyproject_version=read_pyproject_version(),
        parse_error=parse_error,
    )


# --- consistency checks (registry-driven; add new ones without redesign) ----


def check_tag_is_valid(ctx: VersionContext) -> CheckOutcome:
    if ctx.tag_version is None:
        return CheckOutcome("Release tag format", False, ctx.parse_error)
    return CheckOutcome("Release tag format", True, ctx.tag)


def check_pyproject_readable(ctx: VersionContext) -> CheckOutcome:
    if ctx.pyproject_version is None:
        return CheckOutcome("pyproject version", False, "could not read [project].version")
    return CheckOutcome("pyproject version", True, ctx.pyproject_version)


def check_tag_matches_pyproject(ctx: VersionContext) -> CheckOutcome:
    if ctx.tag_version is None or ctx.pyproject_version is None:
        return CheckOutcome("Tag <-> pyproject", False, "prerequisite check failed")
    if ctx.tag_version != ctx.pyproject_version:
        return CheckOutcome(
            "Tag <-> pyproject",
            False,
            f"tag {ctx.tag_version} != pyproject {ctx.pyproject_version}",
        )
    return CheckOutcome("Tag <-> pyproject", True, f"both {ctx.tag_version}")


CHECKS: tuple[Callable[[VersionContext], CheckOutcome], ...] = (
    check_tag_is_valid,
    check_pyproject_readable,
    check_tag_matches_pyproject,
)


def run_checks(ref: str | None) -> list[CheckOutcome]:
    ctx = build_context(ref)
    return [check(ctx) for check in CHECKS]


def is_consistent(outcomes: list[CheckOutcome]) -> bool:
    return all(o.ok for o in outcomes)


def render(outcomes: list[CheckOutcome]) -> str:
    lines = ["Version Consistency Check", ""]
    for o in outcomes:
        mark = "\u2713" if o.ok else "\u2717"  # ✓ / ✗
        lines.append(f"{(o.label + ' ').ljust(24, '.')} {mark} {o.detail}")
    lines.append("")
    lines.append(("Result ").ljust(24, ".") + (" CONSISTENT" if is_consistent(outcomes) else " INCONSISTENT"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ref = argv[0] if argv else os.environ.get("GITHUB_REF")
    outcomes = run_checks(ref)
    print(render(outcomes))
    return 0 if is_consistent(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
