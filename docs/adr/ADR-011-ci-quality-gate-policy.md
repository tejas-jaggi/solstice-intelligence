# ADR-011: CI & Quality-Gate Policy

- **Status:** Accepted
- **Date:** Milestone 3, Phase A
- **Context area:** Automated quality enforcement

## Problem

The repository had 101 tests but nothing ran them automatically; a commit that
broke a test would not be caught until someone manually ran pytest. Code style,
type safety, coverage, and dependency vulnerabilities were likewise unenforced
and invisible. We need automated enforcement that is credible without being
counterproductive.

## Decision

A GitHub Actions workflow runs on every push and pull request. Checks are divided
into **blocking gates** and **advisory / informational reports**:

- **Blocking (fail the build):**
  - **pytest** — the full deterministic test suite.
  - **Ruff** — lint and format check. Findings are mechanical and auto-fixable, so blocking has no downside.
  - **mypy** — static type checking. Originally introduced as an advisory gate
    during incremental type adoption, then promoted to a blocking gate after
    Phase A verification established a sustained zero-finding baseline across
    the repository.
- **Informational only (never a gate):**
  - **Coverage** — measured and reported. No threshold gate: a coverage target
    incentivizes low-value tests written to hit a number.
  - **pip-audit** — dependency vulnerability scan. Never gates, because the
    vulnerability database changes over time; gating would make the same commit
    pass or fail depending on *when* CI ran (non-deterministic builds).

**Core principle:** blocking gates must always be **deterministic and
actionable**; informational or time-varying checks report findings without
destabilizing the build. A red build therefore always means a real, fixable
problem.

**No secrets, zero API cost.** CI requires no OpenAI key and spends no API
credit, because the entire suite is deterministic via `FakeLLMClient` and mocks.
This is a direct payoff of a discipline held since Milestone 1.

## Phase A Promotion Record

The original ADR intentionally introduced mypy as an advisory quality gate to
allow incremental adoption without encouraging blanket suppressions or rushed
type annotations.

During the Phase A verification initiative, the repository reached a verified
quality baseline:

- Ruff lint: clean
- Ruff formatting: compliant
- mypy: 0 findings across 55 source files
- pytest: 101/101 tests passing
- pip-audit: no known dependency vulnerabilities

With the repository maintaining a verified zero-finding baseline, the promotion
criterion defined in this ADR was satisfied. GitHub Actions was therefore updated
to make mypy a blocking quality gate for all future pull requests and commits.

This promotion reflects an earned engineering milestone rather than a policy
change made on a schedule.

## CI performance philosophy

CI must remain fast enough that developers run it willingly. A slow pipeline is
one people skip or work around, at which point the gate stops protecting the
codebase. As the repository grows, workflow runtime is treated as an engineering
consideration to review, not an unbounded default: fast checks run first,
dependencies are cached, and the job stays single and lean rather than sprawling.

## Alternatives considered

- **Gate on everything immediately (mypy, a coverage threshold, dependency
  scan).** Rejected: blocking mypy on a partly-typed codebase forces suppression
  or a large up-front cleanup; a coverage threshold incentivizes low-value tests;
  gating on a changing CVE database makes builds non-deterministic.
- **No CI, keep manual verification.** Rejected: leaves the test guarantee
  dependent on human memory and provides no visible credibility.
- **External CI (CircleCI, Travis).** Rejected: adds an integration for no
  benefit when the repository is hosted on GitHub. GitHub Actions is native,
  free for public repositories, and the industry standard here.
- **Ruff `target-version = py314`.** Rejected: ruff 0.16.0's py314 formatter
  strips the required parentheses from multi-type `except (A, B):` clauses,
  producing invalid syntax. Pinned to `py312`, which the codebase is fully
  compatible with, since it uses no 3.14-only syntax.

## Tooling

GitHub Actions (native CI), Ruff (lint + format, replacing flake8/black/isort
with one fast tool), mypy (reference type checker), coverage.py via pytest-cov
(measurement), pip-audit (PyPA dependency scanner). Dependabot is an optional
future enhancement, not a Phase A deliverable — pip-audit is sufficient.

## Consequences

Every change is automatically verified; broken tests, style violations, and
type-checking failures now block merges, while coverage and dependency
vulnerabilities remain visible without introducing non-deterministic build
failures.

The advisory→blocking transition for mypy demonstrates that type safety was
adopted incrementally and promoted only after reaching a verified zero-finding
baseline. This preserves both engineering discipline and long-term
maintainability while avoiding unnecessary suppressions during adoption.

The milestone is purely additive: no runtime behavior changed as part of the
promotion. The work consisted of quality improvements, type refinements,
tooling enhancements, and CI policy updates validated by a fully passing
regression suite.
