# Presentation review — 2026-11-16

Audience: the NVFlare core development team, with existing knowledge of the
runtime. Scope: 20 main slides and 8 appendix slides, 28 slides total. The main
narrative examines current audit capture and writer behavior, record semantics,
proposed audit mechanisms and compatible implementation boundaries. The appendix
supplies industry references and examples supporting those technical decisions,
then closes with implementation-size estimates for the four groups.

## Concept progression

| Slides | Concepts and connection |
| --- | --- |
| 1 | Establish the audit-log design scope and identify the reviewed code baseline. |
| 2 | Distinguish audit, diagnostic, training/experiment logging and operational telemetry by purpose, components and output. |
| 3 | Trace producer/helper/service/writer audit calls. Explain automatic startup and explicitly instrumented event coverage. |
| 4–7 | Explain synchronous writing, thread/process coordination, flush versus synchronization, field presence versus validity and diagnostic versus audit records. |
| 8 | Follow related task handoffs and an invalid reply. Receipt does not establish acceptance; references need not identify adjacent events. |
| 9 | Map current headers to actor, action, resource, timestamp and outcome. Industry field names and requirements vary. |
| 10–11 | Define OWASP and connect its Logging Cheat Sheet to the proposed event pipeline; show explicit rejection S3 linked to receipt S2. |
| 12–13 | Map proposed fields to existing runtime context, required helper changes, new bookkeeping and producer-owned evidence. |
| 14–15 | Distinguish operation outcome from persistence state; explain file ownership, restarts, file parts and authorized retrieval. |
| 16 | Map the components to improve: shared contract and adapters, runtime producers/helpers, startup policy, file ownership/retrieval and artifact integration. |
| 17 | Group A — core infrastructure, B1–B3: record types/validation/serialization, local writer operations and the service API with compatibility adapters. Baseline and event-catalog prework precede B1. |
| 18 | Group B — runtime integration, B4–B7: startup configuration, ownership/retrieval, optional JSONL and context propagation. |
| 19 | Group C — event coverage, B8–B10: authentication/admin outcomes, task/workflow decisions and job/artifact events. |
| 20 | Group D — deployment capabilities, B11–B15: rotation, optional collection, archive/retention integration, optional strict admission and a deployment profile. |
| Appendix 21–23 | Separate healthcare record/exchange standards, U.S. certification controls and documented EHR implementations. |
| Appendix 24 | Define the model/job/task/result evidence needed for healthcare training. Model verification is application-owned. |
| Appendix 25–26 | Separate financial preservation obligations from transaction-reporting/message standards, then compare documented vendor layers. |
| Appendix 27 | Apply record identity, change history and original-record preservation to a financial model-review package. |
| Appendix 28 | Estimate changed LOC for groups A–D, separating production code from tests/documentation and stating scope and counting assumptions. |

## Required distinctions

- The four logging categories describe record purposes. Diagnostic JSON output
  remains diagnostic logging; training metrics do not automatically become audit
  events.
- Existing task-attempt UUIDs are reused. Resending an assignment does not
  automatically authorize a new physical attempt.
- The wrong-job check precedes attempt decoding. The proposed JSON therefore
  records `attempt_id: null`; S3 requires retaining S2's return ID and emitting a
  rejection audit event. The submitted task identifier does not prove eligibility.
- Identity provenance is defined as how identity was established. Authenticated
  identities, peer claims and unknown values must remain distinguishable.
- The model loader supplies verified model identity; the writer validates,
  sanitizes and persists metadata without reading model bytes. Identity evidence
  does not by itself prove which bytes executed.
- Appendix slide 21 distinguishes a record (one event) from a trail (related history):
  FHIR AuditEvent defines individual records; ISO 27789 covers trails and their
  constituent records; IHE ATNA covers generation, exchange and repository
  mechanisms. Synchronized clocks require more than UTC formatting, and retained-log
  protection is distinguished from policy-governed purging after retention.
- SEC audit-trail preservation and write-once/read-many storage are alternative
  routes. FINRA retention is not one universal duration. CAT reporting and FIX
  message semantics do not by themselves establish record preservation.
- Vendor descriptions establish only the documented mechanism. Database
  extraction need not identify the sole audit store; selected feeds do not prove
  complete capture; REST audit storage does not describe every native EHR store.
  Financial vendors illustrate distinct capture, reporting and archive layers,
  not a ranking or a comparison of equivalent products.
- Continue-and-alert permits evidence gaps. A synchronized intent proves a planned
  action, not completion; a failed completion write must not cause action replay.

## Implementation discussion boundaries

The new implementation slides extend the proposed mechanisms rather than
replacing their record contract. Shared validation and sanitization must cover
both `AuditService` callers and direct `Auditor` callers. Runtime producers supply
authoritative outcomes; a new serializer cannot create missing decisions. File
ownership and inventory-based authorized retrieval ship in the same usable
increment, including external output roots. Existing artifact persistors and job
storage remain responsible for bytes; their audit hooks supply metadata. Slide 16
explicitly states that application developers capture facts the framework cannot
observe, using a custom training script’s dataset-version selection as the example.

Baseline refresh and event-catalog confirmation precede B1. The B1–B15 sequence
orders shared infrastructure before runtime integration, event producers and
deployment capabilities. The four groups explain those dependencies; they are
not parallel implementation workstreams.
The stages are discussion proposals, not a dependent branch stack. Only one
implementation PR is active at a time, and later stages remain notes. After each
merge, refresh main and revisit the final API, review decisions, configuration and
failure behavior before defining the next increment. Legacy calls/output and
mixed-version peers retain compatibility. Optional later capabilities are enabled
separately; rollback preserves existing audit evidence.

The final appendix slide estimates A at 2,500–4,600 changed LOC, B at
3,300–5,800, C at 4,100–8,100 and D at 6,400–12,500; the combined range is
16,300–31,000. These are planning estimates, not measured diffs or net code
growth. Additions and deletions accumulate across PRs, including repeated edits.
The scope assumes existing infrastructure is reused, one collector integration,
one archive backend, core paths and generic owner hooks. Custom-application
instrumentation and generated presentation artifacts are excluded. Re-estimate
the next increment after each predecessor merges.

## Scope and source review

The current-implementation walkthrough is source-traced to `f787dd919`; the
logger inventory on slide 2 uses the separately pinned main source in its notes. The proposal is tied to
`docs/audit-improvement-program.md` and its pinned reference. New industry slides
carry primary-source links, review dates and limits for public documentation.
The deck contains only the retained healthcare and finance scenarios.
The two published finance exhibits have been removed.

The November 12 audience-focused revision passed source-to-PowerPoint content,
embedded notes, PDF text, slide/page bounds, JSON fields/correlation, B1–B15
sequence and 20-main/7-appendix checks. Slide 28 has been added and PowerPoint,
PDF and previews regenerated. Fresh 20-main/8-appendix, source/content/notes,
bounds and estimate-arithmetic checks passed. Independent source and visual
review found no issues with the new slide. Source footnotes remain omitted from
slide faces; references and source-review dates remain in speaker notes.
Completed checks are recorded in `validation.md`.
Runtime behavior is checked separately during implementation.
