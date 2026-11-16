# Presentation verification — 2026-11-16

Scope: 28 slides/pages: 20 main slides and eight appendix slides. The presentation
and design document now explicitly target NVFlare core developers. Main-slide
explanations focus on audit capture, API/file contracts, record semantics,
persistence failures, ownership/retrieval and compatible integration. Basic
framework, process, UUID and timestamp tutorials were trimmed. The title remains
first, the logger table second, and the industry references in the appendix.

## Content and plan checks

- Slide 28 adds the discussed LOC estimates as the final appendix slide, with
  production, tests/documentation and total ranges for each group. Every row
  and aggregate sum passed arithmetic checks. The visible callout defines
  additions plus deletions across PRs and the core-path/single-collector/
  single-archive integration assumptions. Notes explain replacements, repeated
  edits, exclusions and re-estimation after predecessor merges.
- Slides 1–27 and the design document match the pre-edit source package exactly.
  The source manifest, PowerPoint content and notes agree. The README and
  narrative now identify the 20-main/8-appendix order and slide 28.
- The core-team audience and audit-log scope are explicit in the design document,
  README and narrative review. Technical design precedes the document's stage
  ledger and delivery process. This is an editorial change, not a runtime change.
- Slide 2's logging-category table, slide 3's approved automatic-startup and
  explicit-instrumentation statements, field-availability tables and the selected
  B1–B15 tables remain intact. Historical source pins and review dates remain
  historical; this revision does not claim a new main-branch source review.
- Slide 16 includes the requested application-developer responsibility statement
  verbatim, with dataset-version selection as the example. A taller two-line
  callout and adjusted table height keep it visible without overlap.

- Group A covers B1–B3 core infrastructure; B covers B4–B7 runtime integration;
  C covers B8–B10 event coverage; D covers B11–B15 deployment capabilities.
  Every B stage appears once. Baseline/contract/catalog prework precedes B1.
- The design program, README and narrative use the same selected sequence.
  The original field-availability table was preserved byte-for-byte.
- Direct and service calls share validation. Legacy signatures, text defaults
  and string event IDs remain compatibility boundaries.
- B4 rejects unshipped capabilities and preserves trusted startup/security
  ordering and local-policy privacy. B5 ships ownership and retrieval together.
  B6 includes readers, downloads and workspace archives immediately; B13 covers
  external audit-record archive integration separately.
- B10 isolates all post-commit audit-emission failures outside storage cleanup.
  B14 needs B2/B3/B4/B8 and does not require collection or archive deployment.
  Every earlier stage includes its own checks/docs; B15 validates the profile.
- Independent source review found no blocking audience/scope or preserved-content
  issues. The prior bottom-up plan review remains recorded separately; this
  revision does not change the selected stage deliverables.
- Source footnotes and previous disclaimer removals remain preserved. Full
  source references and detailed implementation boundaries remain in notes.

## Artifact verification

PowerPoint and PDF each contain 28 slides/pages. All source content, embedded
notes, PowerPoint shape bounds, stage order and estimate arithmetic passed
checks using `/tmp/check-audit-loc-slide.py`. PDF title, takeaway, callout and
table text checks and all PDF word bounds passed across all 28 pages. Earlier
JSON correlation/content assertions remain covered by the unchanged sources
and their November 12 verification. All previews and contact sheets were
refreshed. The new slide received independent source/arithmetic and visual
review with no findings. Scoped Black, isort and serial flake8 checks passed
for both unchanged renderer files. `git diff --check` passed.

The source ZIP contains current presentation sources and the design document.
No runtime implementation or production tests changed; no PR was submitted.
Runtime unit tests were not rerun for this documentation/artifact update.

## Artifact hashes (SHA-256)

```text
955f0987bb1de28485d43b6ba6f1c619840d393468dce74bb956cce0841bce9d  nvflare-audit-logging.pptx
d0a21ce15b1ac0847697150a03981fd53578909ab7d51337089b514ac0209b5e  nvflare-audit-logging.pdf
```
