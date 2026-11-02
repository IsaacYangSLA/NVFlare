# Fortanix confidential-computing authorizer

## Scope and baseline

This design targets NVFlare 2.9 commit
`ad047542b1cef7559a8cabfa91475cffc44478fc`. The implementation is
[`FortanixAuthorizer`](../../nvflare/app_opt/confidential_computing/fortanix_authorizer.py).
It accepts a CCM application certificate and proves possession of its private
key. It does not interpret a Trustee EAR, enroll a machine, configure CCM/DSM,
or install a Kata runtime.

The CoCo backend of the unified confidential-computing provisioner remains
Trustee-only.
This change supplies an authorizer component for manually prepared resource
configuration; it does not add a Fortanix backend to the provisioning schema.

## Analysis of the existing authorizers

Sources are under
[`nvflare/app_opt/confidential_computing`](../../nvflare/app_opt/confidential_computing).

| Authorizer | Evidence and verification | Identity, workload and freshness | Configuration and reuse |
| --- | --- | --- | --- |
| `CCAuthorizer` | Abstract generation, verification and namespace contract; typed generation/verification errors | Optional site-binding capability; base `verify_for_site` is insufficient when binding is required | Base for the new component. `generate_with_retry` supplies a generation interface; backend-specific retries need their own bounded implementation |
| `ACIAuthorizer` | Local ACI sidecar obtains MAA JWT; configured MAA JWKS verifies signature | Constant runtime data; no FL identity or workload pins. JWT time checks depend on claims being present; no explicit required age or replay check | MAA endpoint, namespace, retry settings. Not a suitable security template for peer binding |
| `AZCVMAuthorizer` | External Azure attestation client obtains MAA JWT; configured MAA JWKS verifies signature | No FL identity, workload pins, explicit maximum token age or replay check | Client binary, MAA endpoint, namespace; generation delegates to `sudo` subprocess |
| `SNPAuthorizer` | SNPGuest generates report, fetches AMD certificates/VCEK and verifies hardware report | Random ReportData and bounded process-local duplicate-nonce history; no verifier challenge, age limit, FL identity or measurement policy | SNPGuest path, CPU model, certificate directory, retry/timeout settings. Raw hardware verification does not supply workload authorization |
| `TDXAuthorizer` | External CLI generates and verifies token according to its configuration | Python layer has no FL identity or replay binding; actual appraisal/freshness depends on CLI. Success is inferred from absence of `Error:` in an error file | CLI path and configuration directory; no reusable peer-proof protocol |
| `GPUAuthorizer` | NVIDIA SDK obtains NRAS result and validates it against a detailed GPU policy | Random nonce and process-local duplicate-nonce history; no FL identity, CPU/workload binding or project audience | NRAS URL, policy file, nonce-history size. GPU policy requirements inform deployment policy, not CCM certificate parsing |
| `MockAuthorizer` | Static historical token; verification always succeeds | No security guarantees | Test/demo helper only |
| `CoCoAuthorizer` | Guest AA returns Trustee EAR and TEE key; pinned Trustee key verifies EAR and attested public key signs outer JWT | Signed site, project audience, bounded EAR/proof age, expiry and process-local replay cache; optional per-site CPU/InitData/measurement/GPU pins | Main behavioral reference: local-only credential transport, private-key containment, identity binding, fail-closed verification and bounded transport retries |
| `TrusteeAuthorizer` | Same CoCo proof/verifier with verifier-only, CoCo AA or bare-metal CVM credential providers | Inherits CoCo identity, workload, freshness and replay behavior | Demonstrates provider separation. Uses the same Trustee namespace because its proof format is identical |

[`ComponentPathAuthorizer`](../../nvflare/app_common/widgets/component_path_authorizer.py)
is a separate widget: it authorizes Python component paths against resource
allowlists at component-build time, with enforce/warn modes and auditing. It
neither generates nor verifies attestation tokens and is not a Fortanix base.

`CCManager` can require explicit site binding through
`require_site_binding: true`. With that setting it rejects verifiers that do not
advertise support and override `verify_for_site`; the legacy hardware authorizers
above do not provide that capability. The default manager setting is false, so
Fortanix deployments must set it explicitly.

Relevant existing tests are `coco_authorizer_test.py`,
`trustee_authorizer_test.py` and `cc_manager_test.py` in
`tests/unit_test/app_opt/confidential_computing`, plus
`tests/unit_test/app_common/widgets/component_path_authorizer_test.py`.
They cover peer identity, audience, signed workload constraints, freshness,
replay, secret redaction, transport restrictions and generation budgets. Legacy
ACI/Azure coverage in `tests/unit_test/lighter/cc_provision/impl/test_cc.py`
primarily checks provisioning and namespaces.

## Fortanix credential and proof

The pinned Fortanix
[AA implementation](https://github.com/fortanix/guest-components/blob/d3ae8f2c572e474d7fd36b76ba4f10042c05fefd/attestation-agent/attestation-agent/src/token/ccm_as.rs)
returns `cert_pem` and `key_pem` for
`http://127.0.0.1:8006/aa/token?token_type=ccm_as`. The
[pinned attestation SDK](https://github.com/fortanix/attestation/tree/fade7bf57c93fefaeaca77fe453b87a7909c9cd4)
connects attestation to a generated application key. The private key stays in
memory and never appears in the transmitted proof, logs or error messages.

The new proof has namespace `x-fortanix-coco`, JWT type
`NVFLARE-FORTANIX+JWT`, format version 1, and a public `cert_chain_pem` alongside
`sub`, `aud`, `iat`, `exp` and random `jti`. The leaf's RSA key signs it using
RS256; the accepted leaf key must have at least 3072 bits. An unrelated key,
Trustee EAR or arbitrary certificate cannot substitute for this credential.

Verification validates the certificate path to locally configured CCM roots,
validity periods, CA/non-CA roles and path constraints, key usage, clientAuth
extended key usage and the strict leaf DNS SAN profile. The leaf must contain
exactly the expected site DNS identity. No wildcard matching, dynamically
fetched trust anchor, JWT-provided trust root or subject-name fallback is used.
The outer signature, project audience, authenticated expected site, time bounds
and replay identifier are then checked. Malformed or unsupported inputs fail
closed.

A standalone implementation avoids inheriting Trustee-specific trust-key
validation, EAR claims, workload-pin semantics and token parsing from
`CoCoAuthorizer`. Its bounded retry and proof-validation behavior follows that
component's established pattern while keeping the trust formats distinct.

## Trust policy and freshness limits

`site_domains` maps each protected FL participant to a unique exact DNS SAN.
A CCM administrator must ensure that only the approved application/build for
that site can obtain that SAN. A broadly shared CA plus a guest-signed `sub`
is insufficient: another accepted app could otherwise claim a different site.

The initial deployment target is AMD SEV-SNP with NVIDIA GPU; TDX integration
has not been qualified. CCM policy must enforce the approved SNP measurements,
InitData and application/build identity, and require successful GPU attestation for sites
that need it. This component delegates hardware/workload appraisal to CCM.
A matching SAN by itself is not a hardware report or evidence of a particular
GPU, container image or InitData value.

Defaults and bounds:

| Setting | Default | Meaning |
| --- | --- | --- |
| `proof_lifetime_seconds` | 300 | Positive integer, at most 300; caps outer proof age and declared lifetime |
| `max_certificate_age_seconds` | 3600 | Positive integer, at most 86400; caps leaf age using its `NotBefore` timestamp |
| `proof_iat_leeway_seconds` | 30 | Bounded tolerance for a future outer `iat`; does not relax certificate validity or outer expiry |
| Generation retry attempts | 5 | Retry only transient transport failures, with delays starting at 1 second and capped at 15 seconds, within the caller's total budget |

Certificate age is based on `NotBefore`; it is not independently proven
attestation time. The pinned AA caches its credential until expiration and
provides no force-renewal operation. An old cached certificate fails closed
when it exceeds the configured age even if AA still serves it. CCM certificate
issuance/renewal lifetime must fit the accepted age and the application's
availability requirements. Regenerating an outer JWT does not refresh the
underlying attestation.

Replay rejection is process-local, with entries retained until proof expiry.
It is not a verifier challenge protocol, a shared replay database or durable
across process restarts. Certificate CRL/OCSP revocation is not implemented;
operators must account for the resulting acceptance window when choosing
certificate age/lifetime and updating local trust policy.

The guest-local AA response includes the private key. Every admitted guest
loopback caller able to retrieve it must belong to the same trusted workload.
Never expose the AA credential endpoint through a Service or ingress, print its
response, or copy it to a startup kit. Disabling proxy inheritance, redirects
and non-loopback URLs protects credential transport; it does not isolate
mutually untrusted processes sharing the guest endpoint.

## Manual resource configuration

The following is an illustrative `components` fragment for protected participant
`site-1`. Replace the CA placeholder with complete authenticated CCM root PEM
text, encoded as a JSON string with actual newline escapes. It is deliberately
not a usable certificate. Load trust inputs from an authenticated deployment
source; do not trust the leaf's supplied chain as its own root.

```json
{
  "components": [
    {
      "id": "fortanix_authorizer",
      "path": "nvflare.app_opt.confidential_computing.fortanix_authorizer.FortanixAuthorizer",
      "args": {
        "ccm_ca_certificates": "<complete trusted CCM root CA PEM text>",
        "audience": "nvflare-project-example",
        "site_domains": {"site-1": "site-1.fl-project.example.com"},
        "site_name": "site-1",
        "proof_lifetime_seconds": 300,
        "max_certificate_age_seconds": 3600
      }
    },
    {
      "id": "cc_manager",
      "path": "nvflare.app_opt.confidential_computing.cc_manager.CCManager",
      "args": {
        "cc_issuers_conf": [{"issuer_id": "fortanix_authorizer", "token_expiration": 120}],
        "cc_verifier_ids": ["fortanix_authorizer"],
        "cc_enabled_sites": ["site-1"],
        "required_site_verifier_ids": {"site-1": ["fortanix_authorizer"]},
        "require_site_binding": true,
        "verify_frequency": 120
      }
    }
  ]
}
```

Use the actual component IDs expected by the startup configuration and merge
this fragment into the trusted resource inputs before signing/building kits.
Do not overwrite an existing `components` list or edit signed kits in place.

On an ordinary verifier-only server use the same trust roots, audience,
`site_domains`, protected-site list and required-verifier mapping; omit
`site_name` and set `cc_issuers_conf` to `[]`. A protected server also needs its
own unique site/SAN mapping and issuer configuration. All participants must
agree on the protected-site requirements, including exact namespace
expectations resolved by `required_site_verifier_ids`.

`ccm_intermediate_certificates` optionally supplies inline PEM intermediate
certificates when needed. It does not make them trust roots. `token_url` defaults
to the guest-local HTTP endpoint above; it is unnecessary for verifier-only
instances. Keep project audiences distinct and synchronize clocks. These
settings configure proof acceptance, not CCM enrollment or hardware policy.

## Validation and deployment qualification

Run developer checks on the designated Colossus development node in its
isolated NVMe checkout and Python environment, after verifying the source
revision and preserving existing changes. From that checkout:

```bash
.venv/bin/python -m pytest tests/unit_test/app_opt/confidential_computing/fortanix_authorizer_test.py -q
.venv/bin/python -m pytest tests/unit_test/app_opt/confidential_computing/cc_manager_test.py -q
```

Offline tests use synthetic certificate hierarchies and mocked AA transport.
They cannot establish the certificate profile, SAN ownership, attestation
freshness or policy behavior of a real CCM tenant. Before deployment, qualify
an actual CCM-issued leaf and chain against this strict client-certificate
profile, confirm the per-site SAN issuance restriction, exercise renewal across
the configured certificate-age limit, and verify that failed workload/GPU
appraisals cannot obtain accepted credentials. No actual CCM leaf was available
during initial implementation, so live compatibility and end-to-end deployment
remain unqualified.
