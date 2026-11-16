# Audit improvement program

This internal design discussion is for the NVFlare core development team, with
existing knowledge of the runtime and its execution paths. It focuses on the
audit log: which decisions produce records, what those records mean, how they
are persisted and retrieved, and how changes preserve existing deployments.

The technical design covers the event-capture contract; record schema, identity
provenance and cross-event correlation; emission and persistence failures;
process/file ownership and authorized retrieval; and compatibility across
incremental changes. The [bottom-up B1–B15 stages](#bottom-up-discussion-plan-and-ledger)
describe proposed implementation boundaries. They are discussion items, not
implemented capabilities.

For current behavior and its limitations, see
[Auditing](user_guide/admin_guide/security/auditing.rst). The technical sections
below precede the stage ledger, delivery contract and validation requirements.

## Accepted direction and constraints

These are intended future requirements, not current deployment settings:

- Preserve existing path precedence, default legacy text output and the
  simulator's default no-op auditor. Make JSONL, rotation, collection, deletion
  and strict admission opt-in.
- Target regulated deployments while continuing operation and alerting on audit
  failures by default once the new path is integrated. This permits evidence
  gaps and must not be advertised as lossless auditing.
- Introduce administrator-controlled audit configuration in site
  `local/resources.json`, loaded before auditor creation in every runtime. Job
  configuration must not weaken site policy. Current child startup initializes
  auditing before its normal resource configuration; B4 must address this.
- Distinguish generated event identity from successful configured persistence,
  export acknowledgement, failure and uncertainty. Recovery summaries count
  known failures, not exact losses across crashes.
- Include UTC time, site/role, process incarnation and sequence, actor provenance,
  action/phase/outcome and applicable job, workflow, task-attempt and resource
  identifiers in the structured contract. Keep parent event IDs separate from
  resource IDs; peer-provided metadata is not independently verified identity.
- Preserve existing cross-site event references. Additional fields are optional
  for mixed-version peers. Do not infer success from missing evidence or impose
  a global event ordering from timestamps alone.
- Give secondary writers process-incarnation UUID filenames, with primary
  ownership enforced by a crash-released OS lock. Inventory and authorized
  retrieval must include secondary and rotated files, including external roots.
- Redact before serialization or fallback diagnostics. Exclude credentials,
  raw command arguments, model contents and private dataset locations by
  default. Record allow-listed identifiers and existing artifact digests.
- Strict admission requires successful local synchronization of an intent before
  a classified sensitive mutation. Audit and business changes are not atomic:
  unmatched intents have unknown outcomes; completion-write failure after commit
  alerts without replay. Retention duration is deployment-specific.

## Implementation scope for discussion

Improve the existing audit path incrementally. Retain the useful separation
between producers, the service API and the file writer. Add a shared event
contract and explicit integration points; changing only `AuditService` and
`Auditor` cannot supply decisions those classes never observe. Optional
deployment features remain disabled by default.

### Components that need changes

| Area | Proposed implementation change | Existing integration points / stages |
| --- | --- | --- |
| Record contract, validation and serialization | Build event-specific required fields, bounded values, approved metadata, redaction, safe text encoding and separate event/resource references. Both service and direct-writer entry points must share admission. Keep legacy encoding and string event-ID returns through adapters; expose richer persistence results through a new interface. | `fuel/sec/audit.py`, shared record/serializer modules, command filters; B1–B3. |
| Auditor I/O and AuditService | Separate record construction from file operations; preserve process-local lifecycle, UUIDs, thread exclusion and synchronous local writing initially. Add explicit unavailable/failed/recovered states, bounded health reporting and optional synchronization. Preserve direct Auditor consumers and the simulator no-op implementation. | `AuditService`, `Auditor`, `SimulatorAuditor`; B2–B3, integrated through B4–B6. |
| Startup and site configuration | Load only trusted minimal typed audit settings before audit creation in parent, job, isolated-worker and client sub-worker processes. Preserve security initialization and worker policy preflight before arbitrary component construction. Exclude local audit policy/paths from advertised client site metadata. Reject unshipped feature settings. | `fed_utils.security_init*`, process entry points, `task_worker/worker.py`, `app/client/sub_worker_process.py`, `site_config.SITE_CONFIG_EXCLUDED_TOP_LEVEL_KEYS`; B4. |
| File ownership, inventory and retrieval | Give each file one process owner, identify every process start and list every file/segment. Include new placement in authorized downloads and finished-job archives immediately; do the same when JSONL and rotation add formats or segments. Preserve `NVFL_AUDIT_ROOT` / log/result-root fallback behavior. | `Workspace`, startup code, `JobRunner._save_workspace`, job manager and download paths; B5–B6 and B11. |
| Context helpers and event producers | First wire authoritative actor/site/role, workflow, task and existing attempt identity through helpers; then instrument admission, rejection and terminal decisions at their source. Authentication failures and authorization denials need calls before the normal command audit filter. | `fl_context_utils.py`, HCI login/authz/audit handlers, client/server admin dispatch, controller/communicator, job and task runners; B7–B10. |
| Artifact and application evidence | Add metadata hooks to the component that loads, verifies, saves or transfers an artifact. Keep file writing with model persistors, application code, task artifact stores and job storage. Isolate the entire post-commit audit call outside storage rollback/cleanup scopes. The writer does not fetch, hash or archive model files. | Model persistors/workflows, `FileTaskArtifactStore`, `SimpleJobDefManager`, configured `job_store`; B10. |
| Health and optional delivery | Reuse Python diagnostic logging for bounded, redacted health reports with a defined fallback if that destination fails. Avoid recursive calls to the failing audit writer. Later add configured delivery/storage adapters, persistent buffering, deduplication and explicit acknowledgement conditions. | Writer/service health; B2–B3. Collector/archive adapters; B12–B13. |
| Deployment policy and documentation | Document each increment's capture policy, permissions, configuration, acknowledgement semantics and rollback as it ships. Add optional strict admission and assemble measured profiles/drills from the implemented subset. | Site policy and deployment guidance throughout; strict admission B14, profile assembly B15. |

Normal startup currently initializes auditing, but event coverage depends on
explicit instrumentation. Framework-owned events belong at stable framework
boundaries; application-specific observations require the responsible application
to emit them. Diagnostic messages, training metrics and internal framework events
do not become audit records automatically.

Reuse existing diagnostic logging, telemetry and experiment-tracking facilities
for their current purposes; this plan does not require rewriting them. Connect
audit health to approved reporting interfaces where useful. Reuse artifact and
job storage interfaces for metadata integration; a new general-purpose model
archive is not a prerequisite for local audit improvements.

### Event catalog and capture boundaries

Agree the minimum catalog during prework; introduce each producer only after its
infrastructure and context integration are available. For each type, define the
actor source, resource identifiers, phase, outcome/reason vocabulary, correlation
rules and treatment of unavailable context. Do not copy an unverified peer claim
into an authoritative identity field.

| Event family | Required observations to define | Producing boundary / stage |
| --- | --- | --- |
| Authentication and participation | Authentication success/failure; session creation/revocation/expiry; site registration accepted/rejected. Keep claimed identities distinct from authenticated identities. | Login/session and registration handlers; B8. |
| Authorization and administration | Denial, evaluation error, allowed exception and sensitive-command request/dispatch/actual completion. Include protected downloads and audit-policy changes, not only mutations. | Authorization checks and command handlers; B8. |
| Task attempt and result | Assignment, receipt, execution admission/start/end, timeout/cancellation, result preparation, observed transfer outcome, server receipt and acceptance/rejection/processing outcome. Reuse the attempt UUID on retransmission of the same assignment. | Client/server runners and controller/communicator decisions; B9. |
| Workflow and aggregation | Workflow/round start and terminal state; included/excluded contribution IDs; resulting model/checkpoint identity where available. Custom workflow semantics require producer-owned mappings. | Controller/workflow and aggregator decisions; B9–B10. |
| Job lifecycle | Submission validation, deployment result per site, actual start, completion/failure/cancellation and deletion/export. A request receipt is separate from a committed job state. | Job manager, deployer and job runner; B10. |
| Artifact lifecycle | Verification, load/restore, save/publication, replacement, deletion and protected export with exact identity when known. A digest neither establishes execution nor recovers deleted bytes. | Persistor, loader, task artifact or job storage operation; B10. |
| Application-specific evidence | Dataset/cohort access, approvals and externally managed model/version changes where relevant. Avoid raw patient records, model contents and private dataset paths. | Application or external producer, correlated to job/attempt; B10 integration contract. |
| Audit lifecycle | Initialization/configuration changes, write/export failure, recovery, rotation and authorized retention deletion. Keep storage milestones separate from business outcomes. | Service/writer and runtime integration B2–B6; optional adapters B11–B13. |

Routine heartbeat/resource polling, per-batch losses, tensor values and stack
traces remain diagnostic or metric data. Audit the significant state transition
or decision, including rejected attempts, rather than every method call or
network message. Rate-aware failure reporting must retain known counts and
disclose suppression rather than present a complete trail after omissions.

## Proposed record fields and existing data

The proposed record uses actor, action, resource, timestamp and outcome as its
core questions. Industry formats often express comparable meanings with different
field names and event-specific requirements. Existing runtime code already knows
many of the values needed to answer them, but the current audit API does not collect them all. This table
separates available runtime data from the changes needed to produce structured
records; it does not describe fields already present in every `audit.log` entry.

| Proposed fields | Existing availability | Required design change |
| --- | --- | --- |
| `event_id` | The [Auditor](../nvflare/fuel/sec/audit.py#L43) already generates a UUID for each emitted record. | Reuse event-ID generation and distinguish identity from successful persistence. |
| `parent_event_id` | Selected exchanges already carry audit IDs through `ref`; other callers use references for different kinds of ID. | Retain the relevant event ID and distinguish event references from resource IDs. |
| `actor.id`, `actor.role` | Admin usernames, local site identity and process type exist in relevant contexts. The job audit API has no actor parameter. | Pass authoritative actor context and explicitly classify the acting component. Keep peer-reported identity separate from verified identity. |
| `action`, `phase` | Producers know the operation they perform; current action headers mainly name commands or tasks. | Emit standardized operation and phase fields at the producing code. |
| Job, task, workflow and attempt IDs | Relevant runtime paths already have these IDs; the [job audit helper](../nvflare/apis/utils/fl_context_utils.py#L114) forwards job/task fields but omits workflow and attempt identity. | Pass available context through the helper/API and preserve unknown values for legacy, malformed or early-rejected messages. |
| UTC `timestamp` | The writer generates local time without an offset. | Generate timezone-aware UTC for new events; do not infer an unknown historical offset. |
| `outcome`, `reason` | Validation branches, return codes and lifecycle state supply some facts, but do not consistently emit audit events. | Add explicit events at authoritative decisions. A client return code does not establish server acceptance. |
| `schema_version`, process-instance ID, sequence | No structured audit schema, restart identity or event counter exists in the current writer. | Add schema/version handling and writer/runtime bookkeeping. A process ID alone does not distinguish restarts. |
| Model digest, patient access, approvals and external changes | Some artifact paths compute digests, but verified loaded-model identity and application/external-system actions are not universally available to the audit helper. | Instrument the responsible producer and correlate its evidence. The model loader computes/verifies model identity; the audit writer records supplied metadata without reading the model. |

Attempt IDs are already implemented: [ClientTask](../nvflare/apis/controller_spec.py#L173)
generates an `attempt_id` UUID. Resending the same assignment retains its attempt
identity; a network resend is not automatically a new physical attempt.
[Shareable.get_task_attempt_id()](../nvflare/apis/shareable.py#L130) checks
header/cookie consistency and reserves `None` for legacy unfenced protocols.
The design should reuse this identity instead of inventing another attempt ID.

The result-rejection example illustrates why a field can remain unknown even
when the runtime supports it. In
[ServerRunner._process_submission](../nvflare/private/fed/server/server_runner.py#L473),
the existing receipt audit call discards its returned event ID. The peer job-ID
check can then reject the submission before attempt identity is decoded or
validated. To produce rejection S3 linked to receipt S2, retain S2's generated
ID and emit a rejection event at that decision. Expected job J42 and reported
job J41 are available there; an established attempt A1 cannot be assumed.
The proposed record should omit the unknown attempt or represent it as `null`,
according to the eventual schema, unless a separate trustworthy lookup supplies it.

Each event type must define its required fields and its treatment of unavailable
context. Missing values must remain explicit rather than being invented to make
a record appear complete. A supplied model digest identifies content; it does
not by itself prove which bytes executed. Complete patient-access, approval and
external-change coverage requires events from the responsible applications or
systems. Changing only serialization cannot supply those missing observations.

## Prework before implementation

Refresh the coverage map and characterization evidence against current `main`;
identify direct `Auditor` consumers, service callers and runtime startup paths.
Agree the minimum shared event contract and initial event catalog before B1:
actor provenance, action/phase, resource identity, timestamp, outcome/reason,
correlation and explicit unknown values. This gives the lower layers a concrete
contract without pre-implementing future producers or optional deployment tools.

GitHub state checked on 2026-11-10: earlier baseline PR
[#5677](https://github.com/NVIDIA/NVFlare/pull/5677) was closed without merging.
Its branch tests and original `f787dd919` baseline are historical evidence, not
a merged prerequisite or a completed B stage. The component inventory above was
checked at `2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31`; refresh that head again
when implementation begins.

## Bottom-up discussion plan and ledger

Stage boundaries are provisional. A stage can be split only when each increment
has a complete behavior and compatibility boundary. Status values are planned,
active, merged and superseded. PR/commit entries come from verified GitHub state,
not a local branch or approval. All B stages below are planned discussion items;
no new implementation PR is represented as created or merged.

| Group | Stages | Purpose and result |
| --- | --- | --- |
| A. Core infrastructure | B1–B3 | Build the shared record/serialization contract, writer I/O and compatible service/direct-call adapters. |
| B. Runtime integration | B4–B7 | Connect trusted startup policy, file ownership/retrieval, optional JSONL and runtime context helpers. |
| C. Event producers | B8–B10 | Instrument security/admin, workflow/task and job/artifact decisions using the integrated infrastructure. |
| D. Optional deployment capabilities | B11–B15 | Add rotation, collection, archive integration, strict admission and a deployment profile assembled from working capabilities. |

| Stage | Status | Deliverable and compatibility boundary | PR / merge commit |
| --- | --- | --- | --- |
| B1 | Planned | Shared record builder, event-specific validator and serializers; preserve legacy formatting through an explicit adapter and do not activate new file formats. | — |
| B2 | Planned | Auditor I/O, safe lifecycle, restrictive new-file permissions, failure/health behavior and optional synchronization behind the existing runtime defaults. | — |
| B3 | Planned | AuditService integration and compatibility adapters for service and direct Auditor callers; preserve existing signatures and string event-ID returns. | — |
| B4 | Planned | Trusted, versioned site audit configuration loaded before audit creation in every process, without moving arbitrary construction before security/policy preflight. | — |
| B5 | Planned | Process/file ownership, process-instance IDs, file placement/inventory and complete authorized retrieval; changes ship together. | — |
| B6 | Planned | Optional versioned JSONL, readers, downloads and workspace-archive coverage; separate files and legacy default. | — |
| B7 | Planned | Context helper integration for authoritative actor/site/role and available workflow/task/attempt identifiers, with explicit unknown values. | — |
| B8 | Planned | Authentication, authorization and administrative request/denial/dispatch/actual outcome events; preserve security and command semantics. | — |
| B9 | Planned | Workflow/task-attempt and result-decision events with cross-site correlation; mixed-version peers remain supported. | — |
| B10 | Planned | Job, aggregation-output and artifact metadata hooks at authoritative boundaries; post-commit audit failure cannot undo or replay storage operations. | — |
| B11 | Planned | Optional single-owner rotation, safe reopen and retrieval of every segment; automatic deletion remains disabled. | — |
| B12 | Planned | Optional authenticated collection, bounded persistent buffering, deduplication and explicit delivery health. | — |
| B13 | Planned | Explicit audit-record archive/retention integration and acknowledgement conditions; artifact-version retention stays with artifact storage. | — |
| B14 | Planned | Optional synchronized intent admission for classified sensitive administrative mutations, followed by actual outcomes; no replay after completion-write failure. | — |
| B15 | Planned | Deployment profiles, recovery/failure drills and measured operating limits assembled from completed capabilities; per-stage checks/docs are already required. | — |

B1–B3 are additive foundations behind the existing runtime defaults until their
integration is complete. A lower layer must not advertise a deployment option
that its callers cannot yet use. B4 configuration validates supported capability
versions and rejects attempts to enable unshipped JSONL, rotation, collection,
archive or strict-admission features. Each later stage adds its configuration
capability and operational guidance in the same increment that makes it usable.

These groups are not parallel implementation branches. Optional stages may be
selected or reordered only after their actual prerequisites and the final
merged interfaces are reviewed. B11 relies on B5 ownership/inventory. B14 needs
B2 local synchronization, B3 service/admission results, B4 trusted policy and B8
classified administrative decisions; it does not require B12 collection or B13
archive integration. B15 assembles a deployment profile rather than deferring
checks, documentation or recovery behavior needed by any earlier stage.

## Completion and dependency boundaries

Each B stage must produce a reviewable result that works before the next exists.
Lower-layer abstractions may remain behind existing defaults while their runtime
integration is added. No future stage is responsible for repairing a broken
merged behavior, providing a missing reader or making new file placement
retrievable. Stage-local checks and documentation are part of completion.

| Stage | Completion boundary for discussion | Main risk to verify |
| --- | --- | --- |
| B1 | Implement the agreed record builder, event-specific validation/redaction and serializers as additive infrastructure. Specify escaping/truncation and explicit unknowns; retain a legacy adapter and activate no new output format. | Newline/header injection, secret disclosure, incompatible escaping or invented identity/outcome fields. |
| B2 | Add the writer I/O/lifecycle boundary, safe file creation, explicit persistence results, bounded failure recovery/health and optional local sync, behind existing defaults until integrated. Keep record IDs distinct from successful writes. | A full disk or permission error changes a task outcome, failure reporting recurses, or writer close/write races lose admitted work silently. |
| B3 | Wire AuditService and direct Auditor consumers through the shared B1/B2 path. Preserve legacy signatures, string IDs, no-op behavior and direct-instance expectations; use an explicit new interface for richer status. | Direct calls bypass admission, an empty string gains a false success meaning, or existing callers break on a changed return type. |
| B4 | Integrate versioned minimal typed site settings before audit creation in every supported process. Exclude local settings from advertised metadata, preserve policy-preflight ordering and reject unsupported/unshipped options. | Startup imports job-controlled code too early, an audit setting leaks local paths, workers use different policies, or config enables a feature before its reader/retrieval path ships. |
| B5 | Integrate one owner per file, process-instance IDs and file placement/inventory with complete authorized downloads and workspace archives in the same increment. Exercise all supported output-root overrides. | A worker record becomes inaccessible, processes share an uncoordinated destination, or external roots are omitted from retrieval. |
| B6 | Enable optional versioned JSONL only with readers, inventory format handling, authorized downloads and workspace archives for the new files. Keep text default and formats in separate files. | A new format cannot be read/retrieved, JSONL is mixed with text, or rollback deletes previously produced evidence. |
| B7 | Extend context helpers for available authoritative actor/site/role, workflow, task and existing attempt IDs using the integrated contract. Preserve old peers and unknown context. | Peer claims are promoted to trusted identity, absent metadata is fabricated, or a resend is assigned a false new execution identity. |
| B8 | Add security/admin decision events, including denied requests before normal command auditing and authoritative completion. Use the bounded failure policy without changing authorization or command behavior. | A denied command disappears, receipt is reported as completion, or audit failure bypasses a security decision. |
| B9 | Add workflow/task-attempt and result-decision producers with existing cross-site correlation. Retain receipt IDs before rejection events; early wrong-job rejection keeps attempt identity unknown. | Stale/duplicate results appear accepted, retries imply a fresh attempt, or an outcome is emitted before the authoritative decision. |
| B10 | Add job and artifact-owner hooks, including aggregation-output identity. Isolate construction, validation, serialization and I/O failures after storage commit and outside rollback/cleanup scopes; no replay. | Audit failure removes published bytes, rolls back completed state, repeats an operation or claims an uncommitted save. |
| B11 | Add optional rotation only on the ownership/inventory path from B5. Ship safe reopen and retrieval of every segment together; automatic deletion stays disabled. | Rotation races, readers miss a segment, or rollback discards evidence. |
| B12 | Add optional authenticated collection with bounded persistent buffering, stable IDs, deduplication and explicit delivery status through the integrated record/configuration/inventory interfaces. | Outage fills storage, retries duplicate records or a transport response is mistaken for archival persistence. |
| B13 | Integrate explicit audit-record archive/retention policy and exact acknowledgement conditions with a selected backend. Keep artifact retention with artifact storage; do not require building a general model archive. | Bytes are deleted before policy permits it, or an archive receipt is interpreted as permanent retention. |
| B14 | Integrate opt-in synchronized intent admission for classified sensitive admin actions using B2 sync, B3 admission results, B4 site policy and B8 decision boundaries. Record the actual outcome; neither collection nor archive is required. | An unmatched intent is treated as completion, a failed pre-action write allows the action, or a failed completion record causes replay. |
| B15 | Assemble deployment profiles, failure/recovery drills and measured limits from completed capabilities. Retain each prior stage's checks/docs; optional capability combinations must be explicit. | Profiles promise behavior the selected components have not demonstrated, or required checks/docs were postponed until this final stage. |

For B10 post-commit events, isolate the entire audit emission path, including
construction, validation, serialization and I/O. A completed save must remain
committed if any step fails. Do not insert a hook inside a storage `try` block
whose exception cleanup deletes newly published payloads. Emit after that scope
and report failure independently without repeating the operation. Verify that a
failed post-commit emission leaves retained bytes and completion state intact.

UTC belongs to the new structured contract. Preserve the documented legacy text
contract through its adapter; do not infer timezone offsets for old records.
Mixed-version peers may omit new metadata. Readers retain that unknown state
rather than infer acceptance or completion from a missing event.

Acknowledgements distinguish generated, locally written, flushed, synchronized,
delivered and archived states. Specify each backend's actual acknowledgement
condition. A failed writer cannot reliably log its own failure, so health reporting
must remain independently available. Do not add a default asynchronous queue
without measuring the need and defining capacity, overflow, crash-loss and
shutdown-drain behavior.

Configuration and schema changes require explicit version handling. Reject
unsupported or unshipped settings before opening new output files or launching
jobs. Rollback disables the new producer/format/export path without mixing
formats, deleting files or replaying actions. Readers and inventory needed for
retained evidence must remain available. Applications requiring recovery of an
old model retain that version through their persistor/storage policy; an audit
record or checkpoint replacement cannot supply it.

## Delivery and merge contract

Only one implementation PR is active at a time. Future stages remain discussion
notes, without dependent implementation branches. Every merged PR must leave
NVFlare working and deployable without a later stage. Tests reduce risk; they do
not guarantee the absence of defects.

Before each stage:

1. Refresh canonical `NVIDIA/NVFlare` `main` and verify that the actual required
   predecessor PRs have merged. Prework has no implementation predecessor.
2. Read the final diffs, review decisions and relevant CI results. Recheck the
   actual APIs, configuration, file layout, event semantics and failure behavior.
3. Update downstream assumptions and split or reorder stages when required.
4. Branch from refreshed `main` and define the next PR's complete behavior,
   preserved defaults, compatibility checks and rollback procedure.

During review, update tests, documentation and this roadmap when a decision
changes a shared assumption. After merge, record the PR and merge commit here
in the next stage's PR; an open or approved PR is not a stable dependency.
Fix defects in merged prerequisites through a separate PR before dependent work.
Do not rely on a later stage to restore functionality or complete retrieval.

Each PR requires targeted tests, affected integration tests with verified CI
selection, project style checks and independent review of the final diff against
its base. Resolve review findings before publication. Include configuration,
reader, peer, download and rollback checks whenever those boundaries change.
Keep documentation current in the same increment. Preserve evidence during
rollback and keep deployment activation opt-in.

## Baseline and validation evidence

The original baseline branch used canonical `main` commit
`f787dd919bee1f98e1f0f36ecb9b4c37b6f66154`. Its tests characterize that writer,
service and workspace behavior; the coverage map is source-traced. Refresh this
evidence against current `main` during prework before B1. End-to-end federation
and collection checks are added with the implementation stages that cross those
boundaries, rather than postponed to B15.

Use the repository-local `.venv`. Targeted suites are
`tests/unit_test/fuel/sec/audit_test.py` and
`tests/unit_test/apis/workspace_audit_test.py`, together with existing workspace
tests. They use temporary files and controlled in-process boundaries, not real
child runtimes. The premerge unit command in `.github/workflows/premerge.yml`
collects `tests/unit_test` through `runtest.sh`; no new test runner is needed.

Later stages must add fast integration coverage for actual child startup,
ownership, transport, rotation, retrieval, and collectors as those features ship.
Follow [test placement and review rules](../tests/README.md). A focused passing
suite does not establish a full test-suite audit. Record actual commands and
results in each PR's Testing section, including unavailable checks.

Before submitting each implementation PR, activate the project environment,
run the formatting command and then the full CPU unit suite as requested:

```bash
source .venv/bin/activate
./runtest.sh -f
umask 022
./runtest.sh -u --skip-install --torch-backend=cpu
```

Run the affected fast integration cases separately where the change crosses
startup, process, file-ownership, download or collector boundaries. For example,
inject a write failure to verify the task's outcome remains unchanged under the
default policy; reject J41 for expected J42 to verify receipt/rejection correlation;
and start a real worker to verify its selected audit file appears in an authorized
download. Test rollback against retained text/JSONL files and old peers, not only
against a freshly initialized process.

## Industry references

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): safe security event contents, sensitive-data exclusion, injection prevention, and failure testing.
- [OpenTelemetry log model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): structured timestamps, source identity, and correlation; no mandatory SDK is implied.
- [NIST SP 800-92](https://csrc.nist.gov/pubs/sp/800/92/final): log management throughout collection, access, retention, and disposal.

Retention duration is configured by deployment policy.
