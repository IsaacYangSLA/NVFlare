# NVFlare audit logging — engineering presentation

Audience: the NVFlare core development team, already familiar with the runtime
and its execution paths. The deck focuses on the audit log: producer capture
boundaries, record contents and correlation, persistence failures, process/file
ownership, authorized retrieval and compatible implementation changes.

There are 20 main slides and 8 appendix slides, 28 slides total. Healthcare and
finance references support the audit design discussion in appendix slides 21–27;
slide 28 closes the appendix with estimated implementation size by group.

1. **Logging categories, slide 2:** audit, diagnostic, training/experiment logging
   and operational telemetry; their purposes, components and typical outputs.
2. **Existing implementation, slides 3–8:** audit call paths, writer, text format,
   field presence, coverage gaps and receipt versus acceptance.
3. **Common record meanings, slide 9:** actor, action, resource, timestamp and outcome.
4. **Proposed design, slides 10–15:** OWASP logging guidance, pipeline, explicit
   records, field availability, write policy, file ownership and retrieval.
5. **Implementation discussion, slides 16–20:** component changes and four
   bottom-up stage groups, with delivery and compatibility boundaries for review.
6. **Appendix, slides 21–27:** healthcare standards, U.S. certification and EHR
   implementations; financial recordkeeping/reporting standards, vendor
   implementations and model-training examples.
7. **Appendix, slide 28:** LOC estimates for the four implementation groups,
   separating production changes from tests and documentation.

## Deliverables and editable sources

- [Editable PowerPoint](output/nvflare-audit-logging.pptx)
- [PDF](output/nvflare-audit-logging.pdf)
- [Speaker manuscript](speaker-notes.md), also embedded in PowerPoint notes
- [Source package](output/presentation-source.zip)

Active content is in `current.json`, `industry.json`, `healthcare-standards.json`,
`finance-standards.json`, `finance-vendors.json`, `proposed.json` and
`implementation.json`. `appendix-evidence.json` contains the implementation-size
estimate slide. Visual design is in `build.py` and `illustrations.py`.

## Implementation discussion

Slides 16–20 extend the proposed design beyond `AuditService` and `Auditor`.
The component map covers the shared event contract, direct-call compatibility,
runtime event producers and helpers, startup policy, process/file ownership,
authorized retrieval and application/storage integration. The audit writer records
supplied artifact metadata; model persistors and storage systems retain the files.

The bottom-up sequence uses four conceptual groups: A, core infrastructure
(B1–B3); B, runtime integration (B4–B7); C, event coverage (B8–B10); and D,
deployment capabilities (B11–B15). Baseline refresh and event-catalog confirmation
are prework before B1. The groups describe dependencies, not parallel
implementation workstreams.

Core infrastructure introduces record types, validation, redaction and serializers
without changing active output initially (B1); improves `Auditor` file operations,
locking, closure, failure health and optional synchronization (B2); then adds the
structured `AuditService` API and legacy adapters, with validation shared by direct
calls (B3).

Runtime integration covers startup configuration (B4), file ownership and
retrieval (B5), optional JSONL (B6), and context propagation (B7). Event coverage
then adds authentication/admin outcomes (B8), task/workflow decisions (B9), and
job/artifact events (B10). Deployment capabilities cover rotation (B11), optional
collection (B12), archive/retention integration (B13), optional strict admission
(B14), and a deployment profile (B15).

Each increment must remain usable without a later stage. Only one implementation
PR is active at a time; future stages stay as notes. After its predecessor merges,
refresh main, read the final implementation and review decisions, then revise the
next stage's assumptions and scope before branching. Optional collection,
retention integration and strict admission remain separate deployment choices.

Slide 28 gives planning ranges of 2,500–4,600 changed LOC for A,
3,300–5,800 for B, 4,100–8,100 for C and 6,400–12,500 for D:
16,300–31,000 total, including tests and documentation. Changed LOC means
additions plus deletions accumulated across implementation PRs; replacing a line
counts twice and later revisions count again. The ranges assume core paths and
generic owner hooks, reuse of existing facilities, one collector integration and
one archive backend. They exclude custom-application instrumentation and generated
presentation artifacts. Re-evaluate the next stage's estimate after each merge.

## Industry references

The appendix provides concrete references for record contents, trail correlation,
capture boundaries, retrieval and preservation. The healthcare table covers
ISO 27789, ASTM E2147, DICOM audit messages, IHE ATNA
and FHIR AuditEvent. It distinguishes individual event records, audit trails and
the generation/exchange/repository mechanisms supporting them. U.S. certified
health IT requirements are a separate comparison. Epic, Oracle Health and MEDITECH illustrate documented capture,
storage/extraction and forwarding mechanisms, with public-information limits.

The finance table separates SEC/FINRA record preservation, CAT reporting and FIX
trading-message semantics. Bloomberg Vault, Broadridge and FIS are documented
implementation examples, not a market-share ranking or interchangeable products.
Event producers capture the actions, reporting interfaces handle delivery, and
archives preserve the records.

## Regenerate

From the repository root:

```bash
source .venv/bin/activate
python -m pip install python-pptx==1.0.2
python docs/presentations/audit-logging/build.py
libreoffice --headless --convert-to pdf \
  --outdir docs/presentations/audit-logging/output \
  docs/presentations/audit-logging/output/nvflare-audit-logging.pptx
pdftoppm -scale-to 1100 -png \
  docs/presentations/audit-logging/output/nvflare-audit-logging.pdf \
  docs/presentations/audit-logging/output/previews/slide
```

Rendering needs LibreOffice Impress and Lato, Carlito and Cousine fonts.
The NotebookLM-inspired design uses ivory pages, charcoal type, restrained
accents, native editable line illustrations, document/code panels and light
PowerPoint tables. The PDF embeds font subsets.

## Record and evidence boundaries

The current-implementation walkthrough is pinned to canonical commit
`f787dd919`; the design reference is fork commit `9111adf82`. Slide 1 identifies
that baseline. The logger inventory on slide 2 uses the separately pinned main
source identified in its notes. Full source links and
individual review dates are in the notes; source footnotes are omitted from slide faces.

The JSON on slide 11 is illustrative. Rejection S3 references receipt S2, compares
local J42 with reported J41 and leaves the unestablished attempt null. Slides
12–13 explain which proposed fields already exist at runtime and which require
new capture or bookkeeping. The full table is also in
[the design document](../../audit-improvement-program.md#proposed-record-fields-and-existing-data).

Identity provenance means how an actor identity was obtained and validated; slide
12 defines it where used. Applications supply verified model identity. The audit
writer records metadata without reading or hashing models. A digest alone does
not prove execution. Complete workflow evidence depends on the responsible
producers and external preservation systems.

See [narrative-review.md](narrative-review.md) for the concept review and
[validation.md](validation.md) for checks and artifact hashes.
