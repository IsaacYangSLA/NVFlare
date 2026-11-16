# NVFlare audit logging — speaker manuscript

Current implementation → common record meanings → proposed design → appendix: industry references/examples.

## 1. Audit logging: current behavior and proposed design [Existing]

Improve audit coverage, record semantics and persistence without hiding producer responsibilities.

- Review explicit audit call sites, the Auditor API and the audit.log file contract.
- Separate an observed action from its acceptance, rejection or durable recording.
- Example labels: job J42, task T1, attempt A1. Retransmitting an assignment retains its attempt identity.
- Propose record and capture-point changes, writer guarantees and implementation boundaries; industry references follow in the appendix.


Existing code: reviewed baseline f787dd919. Proposed capabilities are design goals, not implemented features.


**Speaker notes**

The existing-audit walkthrough is pinned to commit f787dd919. The logging inventory on slide 2 was checked separately at main commit 2d2d6f7ac; neither is a claim about an unexamined later head. This discussion targets audit contracts, coverage gaps and implementation boundaries for NVFlare core development. J42, T1 and A1 are readable example labels. A1 is not a claim that the current text writer emits an attempt_id field. Retransmitting the same assignment retains its attempt identity; a resend does not itself authorize a new execution attempt. Explicit audit calls create the selected observations examined here. References connect observations, but do not prove complete coverage, successful validation or durable storage. The proposed capabilities are design goals. Industry standards and vendor mechanisms are cited references in the appendix; model-training scenarios are illustrations.

- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/fuel/sec/audit.py#L28-L142

## 2. Four types of logging in NVFlare [Existing]

Audit coverage comes from explicit audit calls; diagnostic, experiment and metrics outputs do not supply missing audit events.


| Category | Question it answers | Components | Typical output |
| --- | --- | --- | --- |
| Audit logging | Who performed an action, on which resource, and what happened? | Auditor, AuditService | audit.log; current coverage depends on explicit audit calls. |
| Diagnostic logging | What is the software doing, and why did it fail? | Python logging, FLComponent.log_* | Console, log.txt, error_log.txt, log.json, log_fl.txt |
| Training and experiment logging | How is the model performing? | MetricsArtifactWriter; optional TensorBoard, MLflow and WandB integrations | Loss/accuracy, round summaries, experiment records |
| Operational telemetry | How is the system or job performing? | System/job metrics collectors and publishers | Event counts and operation timings, including resource checks |

**Speaker notes**

The four-category table establishes the scope of this discussion. The audit path is Auditor/AuditService and explicit producer calls. The detailed slides show where actor, resource and outcome evidence is incomplete. Diagnostic text, JSON, error-only and filtered files are handlers or views of Python logging; changing their formatting does not add missing audit events. MetricsArtifactWriter emits round/summary artifacts, and TensorBoard, MLflow and WandB integrations are optional. Operational collectors/publishers provide event counts and operation timings, including resource-check timing; they do not directly sample hardware utilization. Log streaming transports existing records and secure exception formatting controls diagnostic detail. The inventory was source-checked at historical main commit 2d2d6f7ac. The detailed audit walkthrough remains pinned to f787dd919.

- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/apis/fl_component.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/fuel/sec/audit.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/fuel/utils/log_config.json
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/app_common/widgets/metrics_artifact_writer.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/app_common/tracking/log_writer.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/metrics/job_metrics_collector.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/metrics/system_metrics_collector.py

## 3. How selected events reach the audit file [Existing]

Application code must explicitly request an entry; the writer does not observe every action.

- Command, policy and task producers choose which observations reach Auditor or AuditService.
- Default destinations: <workspace>/audit.log and <workspace>/<job_id>/audit.log; output-root overrides and sub-worker placement qualify these paths.

| Component | Role | Actual call path |
| --- | --- | --- |
| Command / policy code | Records admin commands or permission checks | Calls Auditor directly or through AuditService |
| Job audit helper (optional) | Extracts job/task metadata from FLContext | add_job_audit_event → AuditService |
| AuditService | Holds one process’s Auditor reference | Returns the Auditor or forwards an event |
| Auditor | Formats, appends and flushes an entry | add_event / add_job_event → local file |

Auditing starts automatically in normal deployments, but event coverage depends on explicit instrumentation.


**Speaker notes**

Auditing starts automatically in normal deployments, but event coverage depends on explicit instrumentation. Server/client startup initializes AuditService, and job processes initialize their audit destination. Existing command and task calls run in their built-in processing; additional observations require additional producer calls. The table shows alternative paths, not one mandatory chain: CommandAudit obtains an Auditor and calls it directly; component authorization uses AuditService; job producers often use add_job_audit_event to extract FLContext metadata. AuditService maintains a process-local auditor reference and wrapper calls; Auditor owns the open file. The shown destinations are defaults: output-root environment variables can redirect them, some client sub-workers share the site-level destination, and simulator auditing is normally a no-op. Improving the writer cannot close a coverage gap where no producer calls the audit API.

- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/fuel/sec/audit.py#L28-L142
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/apis/utils/fl_context_utils.py#L114-L122
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/private/fed/utils/fed_utils.py

## 4. The writer is small and synchronous [Existing]

The caller waits while the writer formats, appends and flushes an entry under its thread lock.

- Formatting, write() and flush() run in the caller’s critical path; slow storage delays the caller.
- The lock serializes threads sharing one Auditor; it provides no cross-process file coordination.
- flush() runs per entry; no fsync() or power-loss durability guarantee is provided.
- No retry, rotation or audit-health alert. Open/write/flush failures can propagate to callers.

```text
self.audit_file = open(audit_file_name, "a")
self._lock = threading.Lock()

# Inside add_event():
with self._lock:
    # ... generate event ID and line ...
    self.audit_file.write(line + "\n")
    self.audit_file.flush()
    return str(event_id)
```


**Speaker notes**

Auditor opens the destination in append mode, creating it immediately if needed and retaining existing contents on reopening. The per-instance thread lock covers formatting, writing and flushing. Storage latency therefore reaches the caller. The lock does not coordinate independent Auditor instances or processes. Per-entry flush transfers Python-buffered text to the operating system; no fsync call establishes synchronization to storage. Event-ID generation and flush completion do not establish power-loss durability. The writer provides no rotation, retry/recovery or separate health/alert state; open/write/flush failures can escape to callers. These are the implementation boundaries to resolve before promising stronger persistence semantics.

- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/fuel/sec/audit.py#L28-L142

## 5. Current text format: command and job records [Existing]

Headers are concatenated; the optional message is raw trailing text.

- E = generated UUID; R = caller-supplied reference; T = local timestamp without an offset.
- U = user; J = job; S = optional scope/group; A = command or task name#task ID.
- Message text follows the headers directly; there is no [M:] wrapper or escaping.

```text
# Short example IDs; real E values are UUIDs
[E:C0][T:2026-11-05 10:00:00][U:alice][A:submit_job]

[E:C1][R:S1][T:2026-11-05 10:00:01]
[S:scope-a][J:J42][A:train#T1]received task
# Job record is wrapped here; actual output is one line.
```


**Speaker notes**

The two Auditor APIs produce different record shapes. IDs shown here are abbreviated examples. The first entry is a command; the second is a job/task observation. Its R=S1 identifies a separate server event, not command C0. Scope is the optional configured job execution scope/group. Auditor concatenates headers and message into one line; values and message text are not escaped, so embedded newlines can break physical record boundaries. R is an untyped caller-supplied string: task exchanges commonly use an earlier event ID, while some component-policy calls use a job ID. This ambiguity motivates typed references in the proposed record.

- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/fuel/sec/audit.py#L28-L142
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/apis/utils/fl_context_utils.py#L114-L122
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/app_common/widgets/component_path_authorizer.py#L130-L144

## 6. Which fields does each event contain? [Existing]

add_event() records command/policy events; add_job_event() records job/task events.


| Field | Command / policy | Job / task |
| --- | --- | --- |
| E — Event ID | Always generated | Always generated |
| T — Timestamp | Always generated | Always generated |
| U — User | Always emitted | Not emitted |
| A — Action | Always emitted | If task_name is nonempty |
| J — Job ID | Not emitted | Always emitted |
| S — Scope | Not emitted | If nonempty |
| R — Reference | If nonempty | If nonempty |
| Message text | Optional trailing text | Optional trailing text |

Header presence ≠ a valid value. The job-context helper may use ? for unknown task/scope values.


**Speaker notes**

This table describes each event successfully written by the current Auditor, not a schema enforced for all event types. General and job events use different shapes. The job action, when emitted, is task_name#task_id; the writer does not require a nonempty task_id. Generated E and T do not prove persistence. Always emitted means the header is formatted even when the supplied value is empty or otherwise unsuitable. Optional means omitted when the supplied value is falsey. Message text is appended directly and has no [M:] wrapper. Calls excluded by action or made without an initialized/open auditor may produce no event at all. The context helper may supply question-mark placeholders rather than omit task and scope metadata.

- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/fuel/sec/audit.py#L43-L89
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/apis/utils/fl_context_utils.py#L114-L122

## 7. What current records leave unknown [Existing]

Incomplete capture, ambiguous outcomes and limited persistence guarantees constrain audit evidence.

- Coverage: selected milestones are audited; rejected commands and terminal task decisions may be absent.
- Semantics: user/job headers can be empty or placeholders; a receipt message does not establish acceptance.
- Diagnostic errors do not automatically produce matching audit entries.
- Persistence: no write-failure retry, rotation, retention policy or audit-health alert.


**Speaker notes**

These gaps follow from the preceding API and file behavior. Server command auditing runs after authentication and authorization, so rejections before that filter are missed. Job producers record selected milestones without consistently recording terminal accepted/rejected outcomes. Header presence does not validate its value, and the context helper can substitute question marks. Local timestamps lack offsets, raw text permits ambiguous record boundaries, and R has no enforced identifier type. The local writer has no rotation, retention policy, write recovery or separate health reporting. The next slide traces the resulting distinction between receiving a result and accepting it.

- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/fuel/sec/audit.py#L28-L142
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/private/fed/app/client/sub_worker_process.py#L318-L319

## 8. What each task-handoff event actually proves [Existing]

Task handoffs link related events. An invalid reply can be logged as received and then rejected.


| Step | Audit entry / processing | What the evidence establishes |
| --- | --- | --- |
| 1. Server prepares task | [E:S1] sent task… | Assignment prepared; delivery unproven. |
| 2. Client receives task | [E:C1][R:S1] received task… | Client observed the task assignment S1. |
| 3. Client prepares reply | [E:C2][R:S1] submit result OK | Reply for S1 prepared; server receipt unproven. |
| 4. Server observes reply | [E:S2][R:C2] received result… | Submission observed; acceptance still unknown. |
| 5. Invalid-reply example | Reply reports J41; server expects J42 | Rejected; a separate audit entry is not guaranteed. |

R links related work, not necessarily the preceding entry. S = server, C = client; IDs are shortened.


**Speaker notes**

This source-traced exchange uses shortened event IDs S1, C1, C2 and S2; displayed messages are abbreviated. The server writes S1 while preparing the assignment and places S1 in its outgoing task header. The client writes C1 with R=S1 on receipt. Executor invocation is also audited but omitted here to focus on handoffs. The client writes C2 with R=S1 while preparing its reply and attaches C2 to it. The server writes S2 with R=C2 on receipt. The graph is S1→C1, S1→C2 and C2→S2; R is not an immediate-predecessor chain. Neither “sent task” nor “submit result OK” proves network delivery or downstream acceptance.

The last row is an invalid-submission variant, not the expected outcome of a valid J42 exchange. ServerRunner writes the receipt audit before checking the incoming peer context against the current job. If peer context reports J41 while the server expects J42, it logs a diagnostic mismatch and returns without accepting the result; a separate rejection audit entry is not guaranteed. The receipt event alone therefore leaves the outcome unknown. The sender’s job ID comes from peer context, not necessarily the result body. Receipt auditing also precedes resolution of payload references and later peer/attempt/workflow/submission checks, so it proves neither full payload availability nor validation success. Early wrong-job rejection precedes attempt decoding: do not infer attempt A1 from this branch. A later “finished processing received result” message uses diagnostic logging. The proposed S3 rejection record will link to S2 and distinguish receipt from rejection while leaving unobserved attempt identity null.

- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/private/fed/server/server_runner.py#L367-L376
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/private/fed/client/client_runner.py#L299-L300
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/private/fed/client/client_runner.py#L239-L243
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/private/fed/server/server_runner.py#L473-L515

## 9. Common practice: make an action reconstructable [Industry needs]

Each audit event should capture: Actor + action + resource + timestamp + outcome.

- Industries use comparable meanings with different field names: a shared checklist, not one universal schema.

| Essential field | Existing record | Clearer evidence example |
| --- | --- | --- |
| Actor | U for commands; absent for jobs | Who acted: server validator |
| Action | A names a command or task | What happened: validate result |
| Resource | J and task ID in A; no attempt field | On what: J42 / T1; attempt unknown |
| Timestamp | T is local time without an offset | When: 2026-11-05 18:00 UTC |
| Outcome | Free text when supplied | Result: rejected for wrong job |

Link related events by ID and record artifact versions; artifact storage owns file retention.


**Speaker notes**

The five essentials are a starting checklist, not one universal regulatory schema: actor, action, resource, timestamp and outcome. The middle column connects the checklist to the current headers introduced on slides 5 and 6. U is only present on command/policy records; the current job/task format does not identify an actor. A names a command or task rather than a standardized operation such as validation. J and the task identifier describe part of a resource, but a task attempt needs its own identity to distinguish retries. Timezone-aware UTC and clock synchronization are separate requirements. The outcome must describe the named action: receipt is not acceptance. For a trail, source/site and event references establish where related observations came from. For file-related incidents, version IDs identify exact content; retained bytes enable later recovery. An ID or digest alone cannot reconstruct deleted bytes. OWASP describes when, where, who and what, including interaction identifiers and results. OpenTelemetry supports structured log attributes and correlation; NIST discusses enterprise log management. The main section now turns to the proposed design. The appendix contains healthcare and finance standards, vendor mechanisms and illustrative record examples. The model incidents are illustrative. Industry formats do not require this literal word order or one universal five-field schema. For example, HL7 FHIR R5 AuditEvent uses agent for the actor, entity for the affected object, action for the operation, recorded for recording time and outcome for the result; field cardinalities vary by element and profile. Financial order trails use specialized order and event identifiers and may convey outcomes through linked acceptance, rejection or execution events rather than a result field in every message. In the early wrong-job rejection used here and on slide 11, attempt identity has not been established. FHIR also distinguishes recording time from when an activity occurred; implementations must state which time they record.

- 2026-11-10 — https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- 2026-11-10 — https://opentelemetry.io/docs/specs/otel/logs/data-model/
- 2026-11-10 — https://csrc.nist.gov/pubs/sp/800/92/final
- 2026-11-10 — https://hl7.org/fhir/R5/auditevent.html

## 10. Proposed pipeline: validate, save and forward events [Proposed]

One admission contract for AuditService and direct Auditor calls; preserve legacy entry points and text output.

- Validate required fields, bounds and identity context before either service or direct writes.
- Apply OWASP guidance to event coverage, secret exclusion, log injection and failure reporting.
- Keep text output compatible; optional versioned JSONL uses separate files and supported readers.
- Report local write status independently; collector delivery and archive acceptance have separate acknowledgements.

1. Producer creates structured fields → 2. Shared validation and sanitization → 3. Write local text or JSONL → 4. Optional collector forwards records → 5. External archive retains records


OWASP (Open Worldwide Application Security Project): nonprofit publishing free software-security guidance.


**Speaker notes**

The proposal keeps AuditService and Auditor while giving service calls and direct Auditor calls the same record-admission policy: event-specific required fields, bounds, approved fields, redaction and safe encoding. Compatibility adapters preserve existing signatures, returned event IDs and default text output. Allocating an ID does not establish persistence. Text and versioned JSONL use separate destinations; new-format readers, authorized retrieval and workspace-archive support ship with JSONL. Collection and remote archival remain optional deployment integrations with explicit acknowledgement semantics. Allow-listed fields and configured redaction cannot detect arbitrary secrets in unrestricted content; producers must supply approved metadata. OWASP stands for Open Worldwide Application Security Project, a nonprofit foundation publishing free software-security guidance, tools and standards. Its Logging Cheat Sheet informs authentication/authorization event coverage, the actor/action/resource/timestamp/outcome contract, secret exclusion, log-injection prevention and independent failure reporting. These apply at producer, admission and writer boundaries rather than only at the serializer. The next record shows a concrete validation rejection.

- 2026-11-10 — https://github.com/IsaacYangSLA/NVFlare/blob/9111adf826b3e6795569c8770db336fa0a22aefe/docs/audit-improvement-program.md
- 2026-11-10 — https://opentelemetry.io/docs/specs/otel/logs/data-model/
- 2026-11-10 — https://owasp.org/about
- 2026-11-10 — https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

## 11. Proposed record: an explicit validation outcome [Proposed]

Continue slide 8: after receipt S2, a proposed record S3 says that validation rejected the result.

- Continue slide 8’s invalid reply: expected job J42; incoming context reports J41.
- actor names the validator; phase names the step; outcome records the result.
- parent_event_id links rejection S3 to receipt S2; reported_context preserves the peer claim separately.
- attempt_id is null: this early rejection has not established an attempt. Unknown values must stay unknown.

```text
{"schema_version": 1, "event_id": "S3", "parent_event_id": "S2",
 "actor": {"id": "server", "role": "validator"},
 "action": "task.result.validate", "phase": "validation",
 "resource": {"job_id": "J42", "task_id": "T1", "attempt_id": null},
 "reported_context": {"job_id": "J41"},
 "timestamp": "2026-11-05T18:00:00Z",
 "outcome": "rejected", "reason": "job_mismatch"}
```


**Speaker notes**

Illustrative S3 adds an explicit rejection to the receipt S2 from slide 8; it is not current output. The actor is the local server validator. Resource job J42 is local context; task T1 is the submitted identifier and does not establish an eligible assignment. Reported J41 remains a peer claim. Capture the return ID from the current receipt audit call before emitting the linked rejection at the wrong-job branch. That branch precedes attempt decoding and validation, so attempt_id remains null even if incoming metadata claims one. Existing ClientTask attempt UUIDs can be forwarded where established; do not invent an attempt ID to fill the record. S2/S3 stand in for UUIDs. Phase identifies the validation operation; outcome and reason describe its decision, independently of receipt or later processing completion. The following tables distinguish available runtime context from new producer and writer responsibilities.

- 2026-11-10 — https://github.com/IsaacYangSLA/NVFlare/blob/9111adf826b3e6795569c8770db336fa0a22aefe/docs/audit-improvement-program.md
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/private/fed/server/server_runner.py#L477-L501

## 12. Proposed fields: data already available in the runtime [Proposed]

Wire established runtime context into the audit contract; distinguish authenticated identity from peer-supplied claims.


| Proposed fields | Existing availability | What needs changing |
| --- | --- | --- |
| event_id | UUID already generated | Reuse existing event-ID generation. |
| parent_event_id | References in selected exchanges | Keep the relevant event ID; distinguish other reference types. |
| actor.id / actor.role | Admin username, site identity and process type | Pass authoritative identity; classify the acting component. |
| action / phase | Producer knows its operation; A names a command/task | Emit explicit operation and phase fields. |
| Job / task / workflow / attempt IDs | Runtime IDs exist, including attempt UUIDs | Forward context the current audit helper omits. |

Identity provenance = how identity was established; keep peer claims and unknown values explicit.


**Speaker notes**

Runtime availability is not current audit coverage. Reuse existing UUID generation, retain event references and distinguish them from resource references. Command filters expose admin usernames; job contexts provide local site and process context. Producers must assign actor role and provenance from authoritative context. The current A field often names only a command or task, so action and phase need explicit mapping. Job, workflow, task and attempt identifiers already exist in relevant runtime paths; ClientTask generates attempt UUIDs, and retransmission of the same assignment retains that identity. The current job helper omits workflow, attempt and actor context. Extend the API/helper wiring without synthesizing values for early rejection, malformed contexts or legacy peers. Identity provenance records how the actor identity was established, such as an authenticated connection rather than an unverified request field; authentication code supplies that evidence and the writer records it.

- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/fuel/sec/audit.py#L43-L89
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/apis/utils/fl_context_utils.py#L114-L122
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/apis/controller_spec.py#L176-L189
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/private/fed/server/server_runner.py#L477-L501

## 13. Proposed fields: generation and new event producers [Proposed]

A new output format cannot create missing decisions or application evidence; the responsible producer must emit them.


| Proposed fields | Existing availability | What needs changing |
| --- | --- | --- |
| UTC timestamp | Writer generates local time without an offset | Generate timezone-aware UTC for new events. |
| outcome / reason | Decision branches know some results and reasons | Audit authoritative decisions; a return code is not acceptance. |
| Schema version / process-instance ID / sequence | Not maintained by the current audit writer | Add format-version and writer bookkeeping. |
| Model digest / patient access / approvals / external changes | Application-specific; digest = content fingerprint | Add application/external events; writer need not read models. |

For S3: retain receipt S2, emit the rejection, and leave the unestablished attempt null.


**Speaker notes**

Generate timezone-aware UTC for new records without inventing offsets for historical timestamps. Emit outcome/reason at authoritative decision branches and scope them to the named action and phase: a client return code does not establish server acceptance or workflow completion. Schema version, a fresh process-instance UUID and per-process sequence are new writer bookkeeping, not a global order. Existing specialized SHA-256 paths do not establish which model executed every task. The model-loading component supplies verified model identity linked to the attempt; the writer validates and persists that metadata without fetching, reading or hashing models. Applications and external systems emit patient-access, approval/signature and storage-change events they alone observe. For S3, retain the S2 return ID and instrument the wrong-job rejection, leaving the unestablished attempt null. Business-operation outcomes and audit-persistence states remain separate.

- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/fuel/sec/audit.py#L43-L89
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/apis/utils/fl_context_utils.py#L114-L122
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/apis/controller_spec.py#L176-L189
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/f787dd919bee1f98e1f0f36ecb9b4c37b6f66154/nvflare/private/fed/server/server_runner.py#L477-L501

## 14. Saving records and handling write failures [Proposed]

Business outcomes and audit-storage states are separate: a rejected result can still have a saved record.

- Default: continue training and alert on audit-write failures. This permits gaps in evidence.
- Health reporting exposes write errors, storage availability and recovery status.
- Optional strict mode: before a sensitive permission change, save and synchronize a planned-action record.
- If writing or sync fails, block the change. Record its outcome afterward; intent alone does not establish completion.

Created: event ID allocated → Local write + flush complete → Optional fsync completes → Optional collector acknowledges → External archive acknowledges


**Speaker notes**

Track audit persistence separately from the task or admin outcome. An allocated event ID proves neither a successful write nor any later acknowledgement. Local write/flush, successful fsync, collector delivery and archive acceptance each depend on their own storage or transport contract. Default continue-and-alert preserves training availability while permitting evidence gaps; failure diagnostics must be bounded, sanitized and independent of the failing audit path. Optional strict admission applies only to selected sensitive admin changes: require a locally synchronized intent before the action, then emit completion/failure afterward. This does not make audit I/O and the action atomic. If the action completes and its final audit write fails, report uncertainty without replaying the action. An unmatched intent leaves completion unknown. Neither local synchronization nor an archive receipt establishes permanent retention.

- 2026-11-10 — https://github.com/IsaacYangSLA/NVFlare/blob/9111adf826b3e6795569c8770db336fa0a22aefe/docs/audit-improvement-program.md
- 2026-11-10 — https://csrc.nist.gov/pubs/sp/800/92/final

## 15. One writer per file; retrieve records from every process [Proposed]

Fix the shared-file risk from slide 4: each main or worker process owns its audit file.

- Main, job, isolated-worker and client sub-worker processes need explicit file ownership.
- Assign a new unique process-instance ID at every start, including restarts.
- Inventory every process file and retained segment, including output-root overrides.
- Authorized job-audit downloads use that inventory to include all relevant evidence.

Main process → its audit file

Worker process → a separate file

Inventory → every process and part

Download → all authorized evidence


**Speaker notes**

Replace the thread-only shared-destination assumption with one process owner per audit file and an OS-level ownership lock released on exit or crash. Each start receives a fresh process-instance UUID; a reused PID must not join unrelated writer instances. Introduce file placement, ownership, inventory and authorized retrieval together, covering main/job processes, isolated workers, client sub-workers and external output roots. Retained segments belong in the inventory when rotation is introduced. A layout change that creates files without adding them to authorized downloads loses retrievability even if writing succeeds. Process-local sequence and event links support reconstruction; timestamps alone do not impose global order across sites. The implementation groups below preserve these integration boundaries.

- 2026-11-10 — https://github.com/IsaacYangSLA/NVFlare/blob/9111adf826b3e6795569c8770db336fa0a22aefe/docs/audit-improvement-program.md

## 16. Implementation scope: improve the full audit path [Proposed]

Keep the service/writer separation; improve the producers, configuration and retrieval around it.


| Area | Implementation change | Affected components |
| --- | --- | --- |
| Service / writer / contract | One validated event path; legacy adapters; safe serialization and write status. | AuditService and Auditor, including direct callers |
| Runtime producers / helpers | Supply known context; record authoritative decisions and completion. | Authentication, admin, job, workflow and task code |
| Startup / site configuration | Load site policy before auditing starts in every runtime process. | Parent, job, worker and client sub-worker startup |
| File ownership / retrieval | One owner per file; inventory all owners and parts for authorized downloads. | Workspace paths, process lifecycle and download code |
| Artifact / application integration | Emit model, package and checkpoint events from the component that owns them. | Persistors, job stores and application producers |

Application developers add audit calls only for facts the framework cannot observe. For example, a custom training script knows which dataset version it selected; the audit writer does not.


**Speaker notes**

Retain the service/writer separation and improve the complete path. One admission policy validates, bounds and sanitizes service and direct Auditor calls; compatibility adapters preserve existing entry points. Instrument authentication, authorization, admin, job, workflow and task decisions at their authoritative branches. Context helpers pass established actor provenance, workflow and attempt identity. Load trusted site policy before auditor initialization in every runtime process, without instantiating job-controlled code before security preflight or exposing policy through advertised site metadata. Job configuration cannot weaken site policy; simulator no-op remains the default. Ownership/layout changes ship with inventory and authorized retrieval, including overridden output roots. Add artifact metadata hooks to current persistors and job stores; isolate post-commit audit failures from storage rollback and cleanup. The writer does not fetch, read, hash or archive model files. Verified loaded-model identity and domain-specific access facts come from their owners; artifact storage retains file versions for recovery. Framework capture covers standard paths, while application developers add only facts the framework cannot observe. B1–B15 deliver these boundaries incrementally.

- 2026-11-10 — docs/audit-improvement-program.md
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/fuel/sec/audit.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/apis/utils/fl_context_utils.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/private/fed/utils/fed_utils.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/private/fed/server/server_runner.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/app_opt/pt/file_model_persistor.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/apis/impl/job_def_manager.py

## 17. Group A: core infrastructure [Proposed]

Build shared record support, then improve the writer and service behind compatible entry points.


| Stage | Deliverable |
| --- | --- |
| B1 | Shared record types, validation, redaction and serializers, initially inactive. |
| B2 | Auditor: safe writes, locking, close behavior, failure health and optional synchronization. |
| B3 | AuditService: structured API and legacy adapters; shared validation for direct and service calls. |

Keep existing calls and text output working; merge one PR, then revise the next stage from refreshed main.


**Speaker notes**

Reconfirm the baseline and event catalog before implementation. B1 adds inactive record types, event-specific validation, bounds, redaction and serializers; no runtime activation. Missing identity remains explicit and serializers do not infer outcomes. B2 hardens Auditor serialization/writing, lock/close lifecycle, initialization status and optional local synchronization. Keep text output, public entry points and default task behavior compatible. Failure health must be bounded, sanitized and nonrecursive. B3 adds structured AuditService entry points and legacy adapters while routing direct Auditor callers through the same admission policy. An allocated ID remains distinct from successful persistence. Each increment stays usable on its own; refresh main and revise the next stage after the predecessor merges rather than maintaining speculative dependent branches.

- 2026-11-10 — docs/audit-improvement-program.md
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/fuel/sec/audit.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/apis/utils/fl_context_utils.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/private/fed/utils/fed_utils.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/apis/controller_spec.py

## 18. Group B: runtime integration [Proposed]

Load trusted settings, make new files retrievable, and pass context before expanding event coverage.


| Stage | Deliverable |
| --- | --- |
| B4 | Load trusted audit settings before initialization in every runtime process. |
| B5 | Ship process/file ownership, inventory and authorized retrieval together. |
| B6 | Add optional JSONL with readers, authorized downloads and workspace archives. |
| B7 | Extend context helpers with established actor, job, workflow, task and attempt identity. |

No early custom-code construction or advertised audit policy; new files ship with authorized retrieval.


**Speaker notes**

B4 loads minimal typed settings from trusted site resources before auditor creation in parent, job, isolated-worker and client sub-worker processes. Do not instantiate job-controlled/custom components before security preflight, advertise local audit policy or let job configuration weaken it. Preserve simulator no-op. Reject unshipped capabilities before opening files or starting jobs. B5 ships one-owner files, process-instance IDs, inventory and authorized retrieval together, including every process and output-root override. B6 enables versioned JSONL only with readers, authorized downloads and local workspace-archive inclusion in the same increment. Text remains default with separate destinations; rollback preserves evidence and reader access. Remote collection/archive integration is later B12/B13, not a substitute for B6 retrieval. B7 forwards established actor provenance and runtime job/workflow/task/attempt IDs. Retransmission retains the assignment attempt; early rejection, malformed contexts and legacy peers may leave it unknown. Keep peer claims separate from established identity. Recheck these interfaces after each predecessor merges.

- 2026-11-10 — docs/audit-improvement-program.md
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/private/fed/server/admin.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/fuel/hci/server/audit.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/private/fed/server/server_runner.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/private/fed/client/client_runner.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/private/fed/server/job_runner.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/apis/workspace.py

## 19. Group C: event coverage [Proposed]

Add explicit outcomes at authoritative decisions and keep audit emission independent of committed operations.


| Stage | Deliverable |
| --- | --- |
| B8 | Record authentication, authorization and admin request, denial, completion and failure outcomes. |
| B9 | Record workflow/task results, validation rejections and actual completion with correlation IDs. |
| B10 | Add job/artifact lifecycle hooks in owning components, with safe post-commit audit emission. |

Post-commit audit failures stay outside storage cleanup and cannot undo a save or replay an action.


**Speaker notes**

B8 instruments authoritative authentication/authorization branches, including denials that never reach the command audit filter. Separate claimed from authenticated identities and dispatch from actual command completion; preserve existing permission checks. B9 covers assignment, receipt, execution, result preparation, server validation and actual processing completion. Retain receipt S2 before a linked rejection S3; early wrong-job rejection can leave attempt identity unknown. Reuse established attempts and record only transfer confirmations actually known. B10 adds job and artifact lifecycle hooks in current owners: job managers, model persistors and task artifact stores. Owners supply verified metadata; the writer does not fetch, hash or archive model files. Post-commit event construction, validation, serialization and I/O must all be isolated from storage rollback/cleanup. Failures cannot remove committed payloads, change completed state or replay an operation; report through independent health and verify committed artifacts survive injected emission failures. File-version recovery remains with artifact storage. Preserve task, authorization and storage behavior at each increment.

- 2026-11-10 — docs/audit-improvement-program.md
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/private/fed/server/admin.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/fuel/hci/server/audit.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/private/fed/server/server_runner.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/private/fed/client/client_runner.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/private/fed/server/job_runner.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/apis/workspace.py

## 20. Group D: deployment capabilities [Proposed]

Select optional deployment capabilities on their own prerequisites; keep activation and rollback explicit.


| Stage | Deliverable |
| --- | --- |
| B11 | Add optional rotation with safe reopening and retrieval of every retained segment. |
| B12 | Add optional authenticated collection, bounded persistent buffering, deduplication and export health. |
| B13 | Integrate archives, explicit acknowledgements and site-controlled retention. |
| B14 | Offer optional strict admission before selected sensitive admin changes; never replay on audit failure. |
| B15 | Define deployment profiles, recovery drills, performance measurements and operating guidance. |

B14 needs B2/B3/B4/B8, not a collector or archive; optional capabilities have separate prerequisites.


**Speaker notes**

B11 uses B5 ownership/inventory: only the owner rotates/reopens and retrieval includes every retained segment. Rotation defaults off and does not imply deletion. B12 adds authenticated transport, bounded persistent buffering, an explicit full-buffer policy, stable event IDs for deduplication and independent export health. B13 integrates remote archives with explicit acknowledgement levels and site-controlled retention. Distinguish local persistence, collector delivery, archive acceptance and protected-retention confirmation; automatic deletion requires explicit policy. This is separate from the local workspace-archive support required in B6, and artifact-byte retention remains separate from the audit store. B14 depends on B2/B3/B4/B8, independently of B12/B13: synchronize intent before a classified sensitive admin change, then record its result. Unmatched intent means unknown completion; failure after the action must not replay it. Audit writes and business changes are not atomic. B15 assembles deployment profiles, drills, measured limits and operating guidance for capabilities actually delivered. Each earlier stage includes its own compatibility/failure/integration checks. Explicit activation and rollback preserve evidence; refresh main and adapt the next increment after each merge.

- 2026-11-10 — docs/audit-improvement-program.md
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/fuel/sec/audit.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/apis/workspace.py
- 2026-11-10 — https://github.com/NVIDIA/NVFlare/blob/2d2d6f7acc43e81b1d181ff4c2fb8cccfba54e31/nvflare/private/fed/server/job_runner.py

# Appendix — industry standards and examples

## 21. Healthcare audit standards: content, exchange and protection [Industry needs]

An audit record describes one event; an audit trail preserves related history. Standards address different layers.


| Standard | What it specifies | Role in our design |
| --- | --- | --- |
| ISO 27789:2021 | Electronic health record (EHR) audit trails and their event records. | Define event types and the evidence each must contain. |
| ASTM E2147-18 | Healthcare access/disclosure audit contents and preservation. | Reference for healthcare-specific record requirements. |
| DICOM PS3.15, A.5 | Coded audit messages: participants, objects, time and outcome. | A concrete message structure for interoperability mapping. |
| IHE ATNA | Audit-event generation, secure exchange and repository mechanisms. | Reference for optional collection and secure transport. |
| HL7 FHIR AuditEvent | Individual audit-event records: actors, actions, entities, time and outcome. | Map our record meanings to a healthcare exchange resource. |

**Speaker notes**

This table distinguishes five related references. An audit record describes one event; an audit trail preserves the related history represented by those records. The references address different layers: FHIR AuditEvent defines individual audit records; ISO 27789 covers audit trails and their constituent records; IHE ATNA covers supporting event generation, exchange and audit-record repository mechanisms. A record format alone does not establish a complete trail. Required events must be emitted, related and preserved by the overall system. ISO 27789:2021 is the published second edition for EHR audit-trigger events, audit data and cross-system audit trails; ISO marks it for revision and lists a replacement under development. Its scope concerns EHR actions and identifies linked health-record segments rather than embedding their contents. ASTM E2147-18 specifies healthcare audit and disclosure records and their preservation; U.S. certification incorporates specified sections, not every provision of the full standard. DICOM PS3.15 Annex A.5 supplies coded audit-message structures with participants, affected objects, event time and outcome; required elements depend on the event definition. IHE Audit Trail and Node Authentication (ATNA) defines integration actors for generating and exchanging audit events and retaining them in an audit record repository, alongside authentication and secure communications. ITI-20 includes syslog transport options, with TLS recommended; an integration must select and implement the applicable options. FHIR R5 AuditEvent represents audit information using agent, action, entity, recorded, outcome and source; cardinalities and implementation profiles matter. Recording time and occurrence time are distinct. None of these references automatically supplies trusted model identity or complete model/job/task coverage. Our proposed record would need explicit event mappings and any required extensions.

- 2026-11-10 — https://www.iso.org/standard/75313.html
- 2026-11-10 — https://store.astm.org/e2147-18.html
- 2026-11-10 — https://dicom.nema.org/medical/dicom/2026b/output/html/part15.html#sect_A.5
- 2026-11-10 — https://profiles.ihe.net/ITI/TF/Volume1/ch-9.html
- 2026-11-10 — https://profiles.ihe.net/ITI/TF/Volume2/ITI-20.html
- 2026-11-10 — https://hl7.org/fhir/R5/auditevent.html

## 22. U.S. certified health IT: audit requirements [Industry needs]

For U.S. certified Health IT Modules, EHI (electronic health information) auditing covers clocks, capture and integrity.


| Requirement | Certified capability | Design implication |
| --- | --- | --- |
| EHI actions / ASTM content | Record specified EHI actions and changes to user privileges. | Define event contents and authoritative capture points. |
| Synchronized timestamps | Use a system clock synchronized with Network Time Protocol. | UTC formatting alone does not synchronize clocks. |
| Default capture / status | Enable logs; record audit status + applicable end-user-device EHI-encryption status. | Define site policy and explicit configuration-change events. |
| Disabling permissions | If disabling is allowed, restrict it to a limited set of users. | Prevent ordinary workloads from weakening audit policy. |
| Protection / detection | Prevent changes, overwrites or deletions; detect altered logs. | Need storage protection and tamper-detection controls. |

**Speaker notes**

EHI means electronic health information. This slide summarizes the audit-related criterion for U.S. certified Health IT Modules, principally 45 CFR 170.315(d)(2), with audit-content and synchronized-clock references at 170.210(e), (g) and (h). The criterion requires actions related to EHI and changes to user privileges to be recorded using the specified sections of ASTM E2147-18. Audit log status must be recorded where the technology permits auditing to be disabled. Applicable locally stored EHI encryption-status changes must also be recorded; exemptions and scope qualifications are described in the official guide. Required capture is enabled by default. If disabling is permitted, the capability is limited to a restricted set of users. Recorded actions and statuses are protected against alteration, overwriting or deletion by the technology, and alteration must be detectable, including changes made outside application control. The guide distinguishes this protection from policy-governed purging after an applicable retention period. It does not impose one general retention duration here. Timestamps use an NTP-synchronized system clock; choosing UTC alone is insufficient. A hash is one possible tamper-detection mechanism, not proof of all other controls. These capabilities inform the proposed audit design.

- 2026-11-10 — https://healthit.gov/test-method/auditable-events-and-tamper-resistance/
- 2026-11-10 — https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-D/part-170/subpart-C/section-170.315
- 2026-11-10 — https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-D/part-170/subpart-B/section-170.210

## 23. EHR vendor examples: documented audit mechanisms [Industry needs]

Real products capture and persist audit events differently; public documentation reveals only part of each implementation.


| Vendor | Documented mechanism | Public-information limit |
| --- | --- | --- |
| Epic | Clarity database extracts; selected events in CEF/LEEF/syslog formats. | An extraction source does not identify every audit store. |
| Oracle Health | Millennium audit events → repository; optional listener forwarding. | Public references do not expose the internal storage schema. |
| MEDITECH | Application audit trails; REST API audit records in SQL storage. | REST SQL storage does not identify every native EHR log store. |

CEF/LEEF/syslog are event-feed formats; public documentation does not establish complete audit coverage.


**Speaker notes**

The vendor comparison concerns audit generation, persistence and transfer, not how a person reviews logs. Epic documents an Access Logging extract script that reads key patient, user and encounter event data from an organization’s Clarity database into a pipe-delimited file. It separately documents near-real-time forwarding of selected security/privacy events in CEF, LEEF or RFC 5424 syslog. CEF and LEEF are event-feed formats; this is not evidence that every event is forwarded or delivery is lossless. Clarity is a documented extraction source, not necessarily the sole or original audit store. Oracle’s 2026 certification disclosure documents native product auditing, an optional Privacy Analytics Listener for Millennium event forwarding, and Oracle Health Privacy Analytics as a repository. These descriptions do not reveal queueing, write synchronization, raw schemas or storage algorithms. Product versions and configurations differ. MEDITECH documents native application audit trails and separately states that patient-access REST infrastructure has audit records within its SQL database, alongside EHR auditing. Its September 2026 Expanse parameter guide describes capture/category and age-based purge settings. Therefore configuration affects coverage and retention; it is incorrect to generalize REST SQL storage to every native log. None of the vendor sources establishes universal actor provenance, complete raw audit payloads, fixed retention, or end-to-end lossless guarantees. The supported design pattern is explicit event producers, a capture/storage path, and optional forwarding, with documented coverage and integrity limits.

- 2026-11-10 — https://open.epic.com/Interface/Other
- 2026-11-10 — https://www.oracle.com/a/ocom/docs/industries/healthcare/certified-health-it-transparency-disclosure-information.pdf
- 2026-11-10 — https://home.meditech.com/en/d/restapiresources/pages/patientaccessapisfaqs.htm
- 2026-11-10 — https://home.meditech.com/en/d/cstrainingresources/otherfiles/allebbpaudittrailparameterexpanse.pdf

## 24. Healthcare example: audit model training across hospitals [Industry needs]

Illustrative case: hospital B uses model v2 although job J42 assigned v3 for task T1.

- Needed trail: assign model → load/verify model identity → run training → submit result → accept/reject.
- Record context: site, job/task/attempt, model identity, timestamp and operation outcome.
- Model loader: computes or verifies a digest (content fingerprint) of the model it loads, linked to job/task/attempt.
- Audit writer: records that metadata without reading the model. Applications emit patient-access events where applicable.


Model verification belongs to the application; the writer records metadata without reading model bytes.


**Speaker notes**

This fictional federated-learning case defines the audit records needed when hospital B uses v2 although job J42 assigned v3 to task T1. The sequence is model assignment, loaded-model identification, task execution, result submission and server acceptance/rejection. Each event records known site/actor, job/task/attempt, model identity, timestamp and phase-specific outcome. Trusted model-loading code computes or verifies a digest of the actual model loaded and supplies that metadata. A digest identifies content but does not alone prove execution. The audit writer validates, sanitizes and persists the event without reading or hashing the model. Applications emit their own patient-data-access events where applicable, avoiding unnecessary raw patient data in central records. Missing producer events remain gaps. Healthcare standards and vendor examples on slides 21–23 guide the record contents and supporting controls. HHS audit controls supply healthcare context; they do not mandate model hashing.

- 2026-11-10 — https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-C/section-164.312
- 2026-11-10 — https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/audit/protocol/index.html
- 2026-11-03 — https://github.com/IsaacYangSLA/NVFlare/blob/9111adf826b3e6795569c8770db336fa0a22aefe/docs/audit-improvement-program.md

## 25. Finance: recordkeeping rules and event standards [Industry needs]

Broker-dealer preservation, regulatory reporting and trading messages address different evidence needs.


| Rule / standard | What it specifies | Design implication |
| --- | --- | --- |
| SEC Rule 17a-4(f) | Reconstructable audit trail OR write-once/read-many storage. | Link changes and preserve recoverable content in external storage. |
| FINRA Rule 4511 | Required books and records: retention periods and storage media. | Configure retention and retrieval of required records. |
| Consolidated Audit Trail (CAT) | Structured order events with IDs, event times and lifecycle linkage. | Use typed IDs, explicit event phases and precise time semantics. |
| FIX Protocol | Standard trading-message structure and lifecycle semantics. | Map trading state; preserve records through a separate storage layer. |

Scope: required broker-dealer records and reportable order events.


**Speaker notes**

These references address different layers of a broker-dealer audit design. SEC Rule 17a-4(f)(2)(i) permits two preservation routes: a complete time-stamped audit trail allowing recreation of an original after modification/deletion, or preservation in a non-rewriteable, non-erasable format, commonly called write once, read many (WORM). They are alternatives, not two simultaneous requirements. The audit-trail route covers record modifications/deletions, creation/change times, applicable individual identity and other information needed to preserve authenticity and recreate the original. Other provisions address storage-process completeness/accuracy, usable copies and redundancy. A digest or event history without recoverable content cannot recreate a deleted original. FINRA Rule 4511 requires members to make and preserve required books and records; its six-year provision applies when no other applicable retention period is specified. It requires the format/media for FINRA-required records to comply with Rule 17a-4. Retention periods therefore depend on the record category. CAT means Consolidated Audit Trail. Its Industry Member specifications define reportable-event fields, file formats and linkage. The transaction specification reviewed is v4.2.0 r4, published October 21, 2026. Event types, order/event identifiers, event timestamps, correction/feedback rules and cross-event references are concrete examples of a typed event contract. Required fields and timestamp meanings depend on event type. This does not mean every field or financial activity is CAT-reportable. FIX is the Financial Information eXchange Protocol: an application-layer standard for trading-message structure, contents and workflows. FIX supplies business-state evidence; record preservation requires storage controls. The model-review scenario assumes its package has been classified as an applicable required record; it does not classify every financial model. NVFlare can emit its observed operations and correlated resource identifiers. External systems must supply unobserved changes and the preservation/reconstruction capability.

- 2026-11-10 — https://www.ecfr.gov/current/title-17/chapter-II/part-240/section-240.17a-4
- 2026-11-10 — https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions/rule-amendments-broker
- 2026-11-10 — https://www.finra.org/rules-guidance/rulebooks/finra-rules/4511
- 2026-11-10 — https://www.catnmsplan.com/specifications/im
- 2026-11-10 — https://www.catnmsplan.com/sites/default/files/2026-10/10.21.26_CAT_Reporting_Technical_Specifications_for_Industry_Members_v4.2.0r4_CLEAN.pdf
- 2026-11-10 — https://fixtrading.org/standards/fix-protocol/

## 26. Major finance vendors: documented audit implementations [Industry needs]

Public documentation describes distinct capture, reporting and retention layers, with limited implementation detail.


| Vendor / product | Documented record mechanism | Public-information limit |
| --- | --- | --- |
| Bloomberg Vault | Capture trade data and metadata; immutable archive with configurable retention. | Archive capability does not establish complete upstream event capture. |
| Broadridge regulatory reporting | Harmonize source data; track data origins, reporting rules and audit trails. | Public page omits raw event schemas, write algorithms and retention periods. |
| FIS Compliance Reporting | Collect, normalize, validate and transmit events; central forensic repository. | CAT reporting events; public page omits storage internals and fixed retention. |

Design lesson: separate capture, normalization/reporting and protected retention; state each guarantee explicitly.


**Speaker notes**

These are major-vendor examples selected for publicly documented mechanisms, not a top-three market-share ranking or a comparison of equivalent products. Bloomberg Vault documents trade-data ingestion from third-party trading systems and direct connections to Bloomberg order/execution systems, within a normalized framework with standardized metadata. Its archive provides immutable storage, configurable retention and data holds that preserve selected records. These are archive capabilities; they do not prove complete event production by every upstream system or disclose a universal event schema. Broadridge's Regulatory Trade & Transaction Reporting platform documents harmonization of internal/external data, data lineage (origins and transformations), transparent reporting rules and consolidated audit trails, including support for CAT and other reporting regimes. Its public page does not expose raw event schemas, write synchronization or retention periods. FIS Compliance Reporting documents collection, normalization, validation, transmission and maintenance of reportable events in a central forensic repository, with submission of eligible U.S. equity/option data to FINRA CAT. This is a regulatory-event pipeline, not proof that it records every action in every source application. Its public page does not specify storage algorithms or a universal retention period. The public descriptions leave delivery guarantees and complete source-event coverage unspecified. The engineering lesson is to define event producers, transformations/correlation and protected retention separately, with explicit evidence of what each layer guarantees.

- 2026-11-10 — https://professional.bloomberg.com/products/compliance/vault/
- 2026-11-10 — https://www.broadridge.com/capability/data-analytics-and-intelligence/regulatory-trade-transaction-reporting
- 2026-11-10 — https://www.fisglobal.com/products/fis-compliance-suite

## 27. Finance example: recover an overwritten review package [Industry needs]

Illustrative case: a securities firm’s model/settings/review package v3 is replaced by v4 before an examination.

- Scope: for required securities records, one permitted storage approach keeps change history to recreate originals.
- Question: who replaced review package v3, when, and can the firm produce the original?
- Evidence: old/new version IDs, actor, time and a retrieval location; logs alone cannot recreate deleted files.
- Responsibility: an external records system preserves or reconstructs v3; NVFlare reports its own operations.


**Speaker notes**

This fictional case assumes the securities firm has determined that the package containing the model, settings and review materials is an in-scope required record. It does not classify every financial model as such. For electronically preserved broker-dealer records, SEC guidance describes two permitted preservation routes: the audit-trail alternative, which must permit reconstruction of an original after modification/deletion, and write-once/read-many storage, which prevents rewriting or erasing retained records. The audit-trail route calls for complete time-stamped modification/deletion history and identity where applicable. NVFlare reports its own observed actions; an external records system must supply replacement events, maintain required history and preserve or reconstruct the original v3 package. A version ID or content digest cannot recreate deleted bytes. These healthcare and finance examples motivate explicit outcomes, exact resource identity, linked observations and storage responsibilities. The proposed NVFlare pipeline in the main section supplies its part of that evidence.

- 2026-11-10 — https://www.sec.gov/investment/amendments-electronic-recordkeeping-requirements-broker-dealers
- 2026-11-03 — https://github.com/IsaacYangSLA/NVFlare/blob/9111adf826b3e6795569c8770db336fa0a22aefe/docs/audit-improvement-program.md

## 28. Estimated implementation size by group [Proposed]

Planning estimate: 6,100–11,800 production LOC; 16,300–31,000 including tests and documentation.


| Group / stages | Production code | Tests + docs | Total changed LOC |
| --- | --- | --- | --- |
| A. Core infrastructure / B1–B3 | 1,000–1,800 | 1,500–2,800 | 2,500–4,600 |
| B. Runtime integration / B4–B7 | 1,200–2,200 | 2,100–3,600 | 3,300–5,800 |
| C. Event coverage / B8–B10 | 1,600–3,100 | 2,500–5,000 | 4,100–8,100 |
| D. Optional capabilities / B11–B15 | 2,300–4,700 | 4,100–7,800 | 6,400–12,500 |
| Total / B1–B15 | 6,100–11,800 | 10,200–19,200 | 16,300–31,000 |

Changed LOC = additions + deletions across PRs; repeated edits count again. Scope: core paths, reused facilities, one collector and one archive integration.


**Speaker notes**

These are engineering planning estimates based on the B1–B15 design and inspected integration points, not measured patch sizes or commitments. Changed LOC means additions plus deletions accumulated across implementation PRs: replacing a line counts as a deletion and an addition, and revisiting a line in later PRs counts again. The final baseline-to-head diff may therefore be smaller. Production, tests and documentation include ordinary comments/formatting in changed files, but exclude generated presentations, vendored code and unrelated reformatting. Tests include both unit and appropriate integration coverage, failure injection, compatibility, process lifecycle and retrieval checks. Shared infrastructure is assigned once to its owning group; for example, B1 owns serializers and B6 owns their activation/readers/retrieval integration. Group A covers record validation/redaction/serialization, safe writer I/O and compatible APIs. Group B covers trusted configuration in all processes, ownership/inventory/authorized retrieval, JSONL integration and context helpers. Group C covers standard security/admin/workflow/task/job branches, generic artifact-owner hooks and representative built-in persistors; it excludes exhaustive custom-application, algorithm and backend instrumentation. Group D assumes existing transport/authentication/storage utilities and backend SDKs, one collector endpoint integration and one selected archive backend. It includes durable bounded buffering, restart recovery, deduplication and explicit acknowledgement/retention integration, but not building a standalone compliance archive product, operator UI or model-byte archive. Application-specific instrumentation, model fetching/hashing and model-file retention are excluded. Event-catalog breadth, process/retrieval integration and B12/B13 delivery/archive requirements are the main uncertainties. A–C together are 9,900–18,500 total changed lines. Revisit the estimate after each actual predecessor merge and adjust scope to the final interfaces and review decisions. Replacements count as two changed lines. These totals are discussed estimates; the linked design document defines stage scope, not a measured LOC budget.

- 2026-11-16 — docs/audit-improvement-program.md
