# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Fortanix CCM component construction for confidential CoCo peers."""

import hashlib
from pathlib import Path

from nvflare.lighter.cc_provision.deployment import plain_data


def fortanix_authorizer(plan, *, issuer):
    service = plan.attestation_service
    values = service.values
    args = {
        "ccm_ca_certificates": Path(values["ccm_ca_cert_file"]).read_text(),
        "audience": "nvflare-fortanix:" + plan.internal["project_name"],
        "site_domains": plain_data(values["site_domains"]),
        "proof_lifetime_seconds": values["token_expiration_seconds"],
    }
    if "ccm_intermediate_cert_file" in values:
        args["ccm_intermediate_certificates"] = Path(values["ccm_intermediate_cert_file"]).read_text()
    for key in ("max_certificate_age_seconds", "proof_iat_leeway_seconds"):
        if key in values:
            args[key] = values[key]
    for key, target in {
        "max_attempts": "retry_max_attempts",
        "initial_delay_seconds": "retry_initial_delay",
        "max_delay_seconds": "retry_max_delay",
        "backoff_multiplier": "retry_backoff_multiplier",
        "jitter_ratio": "retry_jitter_ratio",
    }.items():
        if key in values.get("retry", {}):
            args[target] = values["retry"][key]
    if issuer:
        args.update(site_name=plan.internal["site_name"], token_url=values["attestation_token_endpoint"])
    # Different CCM accounts must not collapse to one verifier in the peer matrix.
    suffix = hashlib.sha256(service.name.encode()).hexdigest()[:16]
    component_id = "fortanix_authorizer_" + suffix
    args["namespace"] = "x-fortanix-coco-" + suffix
    return {
        "id": component_id,
        "path": "nvflare.app_opt.confidential_computing.fortanix_authorizer.FortanixAuthorizer",
        "args": args,
        "token_expiration": values["token_expiration_seconds"],
    }
