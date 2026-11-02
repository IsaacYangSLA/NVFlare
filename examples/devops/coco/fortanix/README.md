# Fortanix integration implementation guide

This guide is for engineers who know Fortanix CCM and DSM and are implementing
the NVFlare side of a Confidential Containers deployment. Start with an ordinary
NVFlare server and two protected AMD SEV-SNP clients, each with one NVIDIA
confidential GPU. A protected server can follow after that deployment passes.
The ordinary server's administrator is trusted with aggregation data and
server memory during this first deployment.

The code provides certificate-based peer authentication. Live CCM certificate
compatibility, runtime qualification, and successful CCM/DSM release are still
deployment acceptance gates. A passing provisioning or unit test does not
establish those properties.

| Area | Available in this branch | Remaining work |
| --- | --- | --- |
| Peer authentication | `FortanixAuthorizer`, strict certificate/proof checks, verifier-only mode and synthetic positive/negative tests. | Qualify a real CCM certificate and issuance/renewal policy. |
| Provisioning | `fortanix_ccm` service validation, CoCo issuer/verifier generation, per-service namespaces and per-site required verifiers. | Populate authenticated deployment trust, identities and approved service values. |
| Packaging | Private signed-kit build context, explicit Fortanix runner request/receipt, final Pod and InitData validation. | Supply the reviewed DSM/CCM build runner and qualify runtime/policy semantics. |
| Examples | Ordinary server plus two protected SNP/GPU client configurations and a workload Dockerfile. | Replace placeholders and supply the trusted runtime, registry, runner and administrator approvals. |
| Live deployment | Defined acceptance and evidence requirements. | Prove CCM/DSM release and finite NVFlare GPU federation with negative tests. |

## How NVFlare fits into the Fortanix flow

An NVFlare project contains a server, named clients such as `site-1`, and an
administrator. Provisioning creates a signed startup kit for each participant.
The kit holds its transport identity, configuration, and startup scripts. A
confidential participant's private kit is embedded into its application image
on a trusted build machine. The cluster operator receives a Pod YAML and an
encrypted image reference; private kits and publisher credentials stay with
their trusted owners.

NVFlare uses two authorization decisions:

1. CCM and DSM approve a confidential workload and its access to image key
   operations. This decision permits the guest to decrypt and run the image.
2. `CCManager` authenticates confidential peers during NVFlare registration and
   subsequent proof refreshes. `FortanixAuthorizer` checks a CCM certificate and
   a proof signed by its corresponding guest-held key. This permits the named
   participant to join or remain in the federation.

The certificate's DNS SAN must be restricted by CCM issuance policy to the
approved build for that exact NVFlare site. Transport mTLS authenticates the
logical site; the authorizer then checks that the signed proof and certificate
authorize that same site. NVFlare cannot infer CPU/GPU measurements from a DNS
SAN or from the existence of a certificate.

| Function | Standard CoCo path | Fortanix-enabled CoCo path |
| --- | --- | --- |
| Confidential pod | Kata VM | Kata VM |
| Guest attestation and secrets | AA and CDH | AA with `ccm_as`; CDH with `ccm_kbc` |
| Remote appraisal | Trustee AS and reference/policy services | Fortanix CCM |
| Image-key operations | Trustee/KBS path | Fortanix DSM |
| NVFlare peer credential | Trustee EAR plus guest-key proof | CCM certificate plus guest-key proof |

For the rationale and threats, read the
[integration assessment](../docs/fortanix-integration-assessment.md) and
[authorizer design](../../../../docs/design/fortanix_authorizer.md).

## Repository map

All paths below are relative to the repository root. Read them in this order.

| Entry point | Responsibility and extension contract |
| --- | --- |
| `nvflare/lighter/cc_provision/config.py` | Loads project/participant YAML, resolves paths, validates service trust inputs and deployment compatibility before signed kits are emitted. |
| `nvflare/lighter/cc_provision/deployment.py` | Defines normalized immutable plans, service inputs, artifacts, and deployment results used between builders and packagers. |
| `nvflare/lighter/cc_provision/impl/coco.py` | Selects authorizers for CoCo plans and dispatches packaging. |
| `nvflare/lighter/cc_provision/impl/cc.py` | Builds the issuer/verifier matrix for every participant, including verifier-only ordinary sites, and writes `CCManager` resource files. |
| `nvflare/app_opt/confidential_computing/fortanix_authorizer.py` | Obtains guest-local `ccm_as` credentials, signs proofs, and verifies certificate, site, audience, time, and replay constraints. |
| `nvflare/app_opt/confidential_computing/cc_manager.py` | Calls issuers under registration/refresh deadlines and verifies peer proofs against authenticated logical site names. |
| `nvflare/lighter/cc_provision/impl/coco_packager.py` | Copies a signed kit into a private build context, emits a runner request, and validates the returned Pod's command, security context, runtime, resources, image digest, and InitData presence. |
| `nvflare/lighter/cc_provision/impl/cc_packager.py` | Moves confidential kits out of public output before packaging, invokes the runner, and emits public delivery manifests. |
| `examples/devops/coco/admin/build_coco_image.sh` | Existing Trustee runner. Its build, encryption, policy, and handoff stages explain the release pipeline that a Fortanix runner must provide. |

Use a new Fortanix path for the DSM/CCM-specific stages. The existing Trustee
runner embeds KBS inputs and `cc_kbc`; its stages are not a Fortanix publisher.
Retain signed kits, private staging, immutable image references, and the
packager's final Pod checks when supplying a Fortanix implementation.

## Roles and prerequisites

| Owner | Required inputs or work |
| --- | --- |
| Platform owner | SNP firmware/TCB and BIOS readiness, confidential GPU mode and passthrough, a pinned Fortanix-enabled Kata guest, AA/CDH APIs, and node enrollment through the Fortanix Node Agent. |
| CCM administrator | Approved application/build measurements, per-site DNS SAN authorization, CPU/GPU policy, certificate lifetime/renewal policy, and authenticated Zone CA/intermediate distribution. |
| DSM administrator | Trusted-CA application authentication, release-specific non-exportable KEK permissions, and denied unrelated decrypt/export access. |
| NVFlare provisioner/publisher | Application images, project/participant configuration, signed kits, private registry credentials, image encryption/signing and policy generation. |
| Cluster operator | Ciphertext image reference, public Pod YAML, existing RuntimeClass and registry trust; launches the approved release. |

Use the [official Fortanix SNP deployment guide](https://support.fortanix.com/docs/deploy-confidential-container-coco-workloads-on-amd-sev-snp-platform)
for Fortanix installation and enrollment. Record image digests and embedded Kata,
guest-components, kernel, GPU-library, and policy-generator versions. A
RuntimeClass name or a successfully enrolled host does not prove that a
workload has been approved.

## Configure and provision

The supplied [project.yaml](project.yaml), [cc_project.yml](cc_project.yml),
[cc_site-1.yml](cc_site-1.yml), and [cc_site-2.yml](cc_site-2.yml) define an
ordinary server and two protected SNP/GPU clients. The
[workload Dockerfile](workload/Dockerfile) requires an approved application
base image containing this NVFlare source revision and its runtime
dependencies. The project files contain public placeholders; they cannot be
used unchanged for a live deployment.

1. **Trusted publisher:** replace server/site identities, registry names,
   RuntimeClass, DSM endpoint/application UUID, and approved workload base image.
   In the service's `site_domains`, map each protected logical name to a unique
   exact DNS SAN. If protecting the server later, its logical name is `server`,
   even when its transport certificate names `server.example.com`. Map every
   protected participant using that service and no unrelated participant.
2. **CCM administrator:** provide the authenticated public Zone CA bundle as
   `private/ccm-zone-ca.pem`, plus an intermediate bundle if necessary. Approve
   the application/build and SAN issuance restrictions after qualifying the
   [contracts below](#fortanix-contracts-to-qualify). No enrollment token is
   needed in these project files. All participants receive the required public
   verifier trust and site mappings; an ordinary participant receives no
   Fortanix credential issuer.
3. **Trusted publisher:** place registry CA and publisher credential files at
   the configured paths, and supply the authenticated public Cosign PEM as
   `image_signing_public_key_file`. Keep its signing private key with the
   publisher. Install the reviewed executable Fortanix
   runner as `build-fortanix` or change `build_tools.coco.build_command` to its
   absolute path. Copy [platform.env.example](platform.env.example) to
   `private/platform.env` and adapt it to that runner. The template's variable
   names are runner-owned; NVFlare passes the directory and does not parse
   those variables. The existing Trustee `admin/build_coco_image.sh` cannot
   consume the Fortanix request.
4. **Trusted publisher:** provision from this directory:

   ```bash
   install -d -m 0700 private
   cp platform.env.example private/platform.env
   chmod 0600 private/platform.env
   # Populate the referenced trust/credential files and edit the examples first.
   nvflare provision -p project.yaml -w ./workspace
   ```

   The configured runner is invoked with one private request JSON path per
   protected participant. Successful provisioning emits
   `workspace/fortanix_project/prod_NN/site-1/site-1-v1-pod.yaml` and the
   corresponding site-2 Pod, plus `cc_manifests/<participant>.json`. Use the
   actual production directory printed by the CLI. Signed plaintext kits and
   intermediate build state stay under `state/cc-private/`. A runner failure
   must stop packaging and retain recovery inputs privately.
5. **CCM/DSM administrators:** confirm final InitData/build approval and the
   release-specific DSM permissions from the runner's trusted handoff. Do this
   before launch. NVFlare does not create or approve a CCM application, enroll
   a node, or register DSM policy.
6. **Cluster operator:** inspect the public Pod/manifest, verify the target
   runtime and one pGPU allocation, and apply the approved Pods with `kubectl
   apply -f <pod.yaml>`. Start the ordinary server/admin with their normal
   startup kits, then submit a finite NVFlare job. Confirm client registration,
   periodic peer proof acceptance, and the GPU training result. On failure,
   distinguish guest launch/CCM/DSM denial from NVFlare peer admission denial;
   preserve sanitized records of the stage that rejected the request.

Paths in `cc_project.yml` and participant configuration resolve beside their
own YAML file. CA files contain public trust; registry passwords, join tokens,
DSM publisher credentials, signing private keys, and plaintext kits remain
private. Do not commit the configured `private/` directory or place it inside
the workload context. The example `.gitignore` excludes `private/`, generated
workspace, and the local runner.

`token_expiration_seconds` caps the signed NVFlare proof at 300 seconds;
`check_frequency_seconds` must be shorter. `max_certificate_age_seconds`
defaults to 3600 and caps the accepted certificate age, not measured hardware
attestation age. Registration/refresh/request deadlines are explicit service
settings; the total request budget must exceed the refresh deadline. Tune
these only after CCM renewal behavior is qualified. Startup resource files
must preserve `require_site_binding: true` and the generated per-site required
verifier IDs.

The provisioner derives a unique component ID and proof namespace for each
Fortanix service. This prevents distinct CCM trust roots from being collapsed
into one verifier when a project has multiple services. Use the generated
resources as a set; manually configured authorizers default to
`x-fortanix-coco`, so separate manual trust services also need distinct
namespaces. Generated identifiers use the first 16 hex characters of SHA-256
of the service name: `fortanix_authorizer_<suffix>` and
`x-fortanix-coco-<suffix>`.

## External runner contract

The trusted runner is an executable invoked as:

```text
build-fortanix /absolute/private/build-request.json
```

The request uses schema `nvflare-fortanix-coco-build-request/v1` and backend
`fortanix_ccm`. It contains absolute `workload_env`, `admin_dir`, and
`result_file` paths, participant/service names, `runtime_class`, CCM public
root/intermediate PEM bundles and the participant's single `site_domain`, and
DSM `endpoint`/`app_id`. `workload_env` describes the prepared private build
context, release, repository, signed kit command, UID/GID, GPU count, and
registry inputs. It contains paths to publisher credential files, not a
host-facing credential payload. Treat the request, environment, and build
context as private trusted-build inputs. For example, the request shape is:

```json
{
  "schema": "nvflare-fortanix-coco-build-request/v1",
  "backend": "fortanix_ccm",
  "workload_env": "/private/site-1/workload.env",
  "admin_dir": "/trusted/fortanix-admin",
  "result_file": "/private/site-1/result.json",
  "participant": "site-1",
  "service": "ccm",
  "runtime_class": "kata-fortanix-snp-gpu",
  "image_signing_public_key": "<authenticated public Cosign PEM>",
  "ccm": {
    "site_domain": "site-1.fl-project.example.com",
    "root_ca_certificates": "<authenticated CCM root PEM bundle>",
    "intermediate_certificates": ""
  },
  "dsm": {
    "endpoint": "https://apps.dsm.example.com",
    "app_id": "11111111-1111-4111-8111-111111111111"
  }
}
```

The runner must perform these stages before returning success:

| Stage | Required result |
| --- | --- |
| Build | Build the prepared `Dockerfile.coco` with its embedded signed kit; preserve the injected command and UID/GID 65532. |
| Encrypt/sign/publish | Use a fresh non-exportable DSM release KEK, publish encrypted layers only, verify signatures and encryption metadata, and obtain an immutable registry digest. |
| Generate policies | Embed approved image verification material, registry trust, Kata Agent policy, AA `ccm_as` domain and CDH `ccm_kbc` DSM configuration in final measured InitData. |
| Approve/handoff | Produce private CCM/DSM registration and release-key mapping inputs for the trusted administrators, plus the public Pod. Never include image keys, AA private keys, or publisher secrets in the Pod or public manifest. |
| Receipt | Create the specified result file only after success, using the receipt below. Exit nonzero on partial completion or denied policy. |

The result is JSON with `schema: nvflare-fortanix-coco-build-result/v1`,
`backend: fortanix_ccm`, the exact `release_name`, and an absolute regular
`pod_yaml` path, for example:

```json
{
  "schema": "nvflare-fortanix-coco-build-result/v1",
  "backend": "fortanix_ccm",
  "release_name": "site-1-v1",
  "pod_yaml": "/private/site-1/handoff/site-1-v1-pod.yaml"
}
```

It is a build receipt, not proof of CCM approval or attestation.
The packager validates the Pod's immutable image, RuntimeClass, command,
security context, allocation, and bounded encoded InitData. The decoded AA
domain and CDH `ccm_kbc` DSM endpoint/application must match the plan. Preserve
the shared validator's restrictions rather than bypassing it to accommodate a
different guest profile.

The accepted InitData is a base64-encoded gzip TOML document with version
`0.1.0` and algorithm `sha256` or `sha384`; qualify the actual hardware binding
for the selected algorithm. `data["aa.toml"]` must select only `ccm_as` with
the exact participant SAN. `data["cdh.toml"]` must select `ccm_kbc`, the exact
DSM URL and application ID. Its `image.image_security_policy` is inline JSON;
`image_security_policy_uri` is rejected. The required policy shape is:

```json
{
  "default": [{"type": "reject"}],
  "transports": {
    "docker": {
      "registry.example.com:5000/workloads/site-1": [{
        "type": "sigstoreSigned",
        "keyData": "<exact configured public Cosign PEM>",
        "signedIdentity": {"type": "matchRepository"}
      }]
    }
  }
}
```

The repository scope must equal the returned image repository without its
`@sha256:` digest. The shared checks also validate `data["policy.rego"]` against
the approved command/security context and permitted Kata requests. Structural
checks establish consistency with the plan. They do not prove that a deployed
guest enforces the policy, that its image was signed/encrypted correctly, or
that a different signed image from the same repository is denied by the final
release policy. Those remain live negative tests.

Compare the existing Trustee runner's request and five stage scripts when
implementing this pipeline. Its key-provider invocation, KBS URIs, `cc_kbc`
InitData and `image_key`/Trustee policy handoff require Fortanix replacements.
Keep the private/public artifact boundary and failure behavior.

The standard Trustee service/operator handoff scripts, including
`coco/50-launch-handoff.sh`, are unsupported for this Fortanix path. They assume
Trustee inputs and the standard runtime profile. The Fortanix runner must
produce its own administrator approval handoff and approved public launch
artifact. Launch that reviewed artifact using the explicit `kubectl apply`
step above; do not route it through the Trustee release-registration workflow.

## Fortanix contracts to qualify

Obtain a sanitized real application certificate chain and a snapshot of the
CCM/DSM policies before claiming deployment compatibility. The current
authorizer accepts an RSA key of at least 3072 bits, a clientAuth leaf with one
exact DNS SAN, appropriate CA/leaf key usages, and a valid path to configured
CCM roots. If actual credentials use a different profile, change the
authorizer and its negative tests together; do not relax checks to make an
unrelated certificate pass.

| Contract | Evidence required |
| --- | --- |
| Site/build identity | Another CCM application or build cannot request the protected site's accepted SAN. Modified image/InitData fails issuance. |
| CPU and GPU appraisal | Required TCB, measurements, VMPL, debug restrictions and GPU evidence are enforced. Missing or failed GPU appraisal denies issuance. |
| Freshness | Establish evidence age, certificate lifetime, renewal behavior and withdrawal behavior. Certificate `NotBefore` age is not independently proven hardware evidence age. |
| InitData | Verify the exact hash transformation and binding and that the guest loads the same AA, CDH, image, and Agent policies. |
| DSM isolation | Each immutable release decrypts only its own wrapped material; unrelated KEKs/resources and KEK export are denied. |
| Node Agent trust | Demonstrate independently verified hardware evidence or protected delegated appraisal and key binding despite host control of the agent process. |
| Guest key endpoint | Guest loopback callers are in the same trusted workload; no Service/ingress or host-facing log exposes the AA private key response. |

## Acceptance and evidence

Run developer tests on the designated development host in an isolated checkout
at the exact source revision. The focused authorizer checks are:

```bash
.venv/bin/python -m pytest \
  tests/unit_test/app_opt/confidential_computing/fortanix_authorizer_test.py \
  tests/unit_test/app_opt/confidential_computing/cc_manager_test.py \
  tests/unit_test/lighter/cc_provision/impl/fortanix_backend_test.py \
  tests/unit_test/lighter/cc_provision/impl/fortanix_packaging_test.py -q
```

Expected result: all tests pass using synthetic certificate hierarchies and
mocked AA transport. These tests cover invalid chains, wrong site/audience,
certificate/key mismatch, expiry, replay, malformed input, transport failure,
and bounded generation behavior. They do not contact CCM/DSM or prove hardware
confidentiality.

The first live milestone is one approved encrypted client image successfully
obtaining a CCM certificate and permitted DSM unwrap, followed by NVFlare
registration at an ordinary verifier-only server. The second milestone is two
protected clients completing a finite GPU training job with valid periodic
proofs and renewal across the configured certificate-age window. Record the
GPU used by CUDA and correlate it with the approved evidence identity; CPU
fallback does not satisfy this GPU profile.

For each milestone retain source and artifact digests, sanitized certificate
metadata, policy snapshots, generated public manifests, CCM/DSM audit records,
and a finite-job result. Negative cases in the
[acceptance matrix](../docs/fortanix-integration-assessment.md#acceptance-tests)
must show denial at the documented stage. Do not include private keys, join
tokens, registry credentials, plaintext kits, or raw AA credential replies in
evidence bundles.

## Remaining implementation work

The Fortanix operator must supply and qualify the versioned runtime and
DSM/CCM publisher path. The runner needs to build the private application
context, encrypt/sign/publish by immutable digest, generate inline public image
verification material and final Agent policy in InitData, and produce a Pod
that satisfies NVFlare's validation contract. CCM policy registration and DSM
permissions must be established by their trusted administrators before launch.

The [gap assessment](../docs/fortanix-integration-assessment.md#security-gaps-and-required-decisions)
records the decisions still requiring Fortanix evidence. Passing the offline
checks is the development gate; passing those live policy and federation
checks is the deployment gate.
