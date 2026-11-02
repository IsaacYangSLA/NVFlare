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

"""Offline contracts for a trusted external Fortanix CoCo publisher."""

import base64
import gzip
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from nvflare.lighter.cc_provision.deployment import CCDeploymentMode
from nvflare.lighter.cc_provision.impl.cc_packager import package_coco_plan
from nvflare.lighter.cc_provision.impl.coco_packager import CoCoPlanPackager, validate_fortanix_initdata
from nvflare.lighter.cc_provision.impl.coco_release import COCO_STARTUP_PROLOGUE, coco_runtime_class
from nvflare.lighter.cc_provision.workload_security import decode_initdata
from tests.unit_test.lighter.cc_provision.impl.test_coco import coco_pod, make_plan

ANNOTATION = "io.katacontainers.config.hypervisor.cc_init_data"


def fortanix_plan(tmp_path):
    plan = make_plan(tmp_path)
    plan.mode = CCDeploymentMode.COCO
    plan.config_path = tmp_path / "cc_site.yml"
    ca = tmp_path / "zone-ca.pem"
    ca.write_text("public CA fixture")
    signing_key = tmp_path / "cosign.pub"
    signing_key.write_text("public signing key fixture")
    plan.attestation_service = SimpleNamespace(
        name="ccm",
        service_type="fortanix_ccm",
        config_path=tmp_path / "cc_project.yml",
        values={
            "runtime_class": "kata-fortanix-snp-gpu",
            "ccm_ca_cert_file": str(ca),
            "image_signing_public_key_file": str(signing_key),
            "site_domains": {"site-1": "site-1.example.com"},
            "dsm_endpoint": "https://dsm.example.com",
            "dsm_app_id": "b001beef-1234-4000-8000-000000000001",
        },
    )
    plan.internal["site_name"] = "site-1"
    return plan


def initdata(plan, policy=""):
    service = plan.attestation_service.values
    aa = '[token_configs.ccm_as]\nccm_domain_names = ["site-1.example.com"]\n'
    cdh = (
        '[kbc]\nname = "ccm_kbc"\nurl = '
        + json.dumps(service["dsm_endpoint"])
        + "\n[kbc_configs.ccm_kbc]\ndsm_app_id = "
        + json.dumps(service["dsm_app_id"])
        + "\n"
    )
    image_policy = {
        "default": [{"type": "reject"}],
        "transports": {
            "docker": {
                "registry.example.com/workloads/site": [
                    {
                        "type": "sigstoreSigned",
                        "keyData": Path(service["image_signing_public_key_file"]).read_text(),
                        "signedIdentity": {"type": "matchRepository"},
                    }
                ]
            }
        },
    }
    cdh += "[image]\nimage_security_policy = " + json.dumps(json.dumps(image_policy)) + "\n"
    return {"aa.toml": aa, "cdh.toml": cdh, "policy.rego": policy}


def encode(data):
    text = 'version = "0.1.0"\nalgorithm = "sha256"\n[data]\n'
    text += "".join(json.dumps(key) + " = " + json.dumps(value) + "\n" for key, value in data.items())
    return base64.b64encode(gzip.compress(text.encode())).decode()


def prepare_kit(tmp_path):
    owner = tmp_path / "private/site-1"
    kit = owner / "startup-kit"
    (kit / "startup").mkdir(parents=True)
    (kit / "startup/sub_start.sh").write_text(COCO_STARTUP_PROLOGUE + "exec nvflare\n")
    for name in ("startup/rootCA.pem", "startup/client.key", "signature.json"):
        (kit / name).write_text("fixture")
    return owner, kit


def fortanix_pod(plan):
    image = "registry.example.com/workloads/site@sha256:" + "a" * 64
    pod = coco_pod(coco_runtime_class(plan), "nvidia", image)
    policy = decode_initdata(pod["metadata"]["annotations"][ANNOTATION])["data"]["policy.rego"]
    pod["metadata"]["annotations"][ANNOTATION] = encode(initdata(plan, policy))
    return pod


def test_fortanix_request_is_distinct_from_trustee(tmp_path):
    plan = fortanix_plan(tmp_path)
    owner, _ = prepare_kit(tmp_path)
    with patch("nvflare.lighter.cc_provision.impl.coco_packager.verify_folder_signature", return_value=True):
        request, _ = CoCoPlanPackager().prepare(owner, plan)
    payload = json.loads(request.read_text())
    assert payload["schema"] == "nvflare-fortanix-coco-build-request/v1"
    assert payload["backend"] == "fortanix_ccm"
    assert payload["ccm"]["site_domain"] == "site-1.example.com"
    assert payload["dsm"]["app_id"] == plan.attestation_service.values["dsm_app_id"]
    runner = Path(__file__).parents[5] / "examples/devops/coco/admin/build_coco_image.sh"
    result = subprocess.run(["bash", str(runner), str(request)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "invalid CoCo build request" in result.stderr


@pytest.mark.parametrize("field", ["domain", "kbc", "endpoint", "app", "missing", "signer", "repository", "allow"])
def test_wrong_fortanix_guest_wiring_rejected(tmp_path, field):
    plan = fortanix_plan(tmp_path)
    data = initdata(plan)
    if field == "domain":
        data["aa.toml"] = data["aa.toml"].replace("site-1", "site-2")
    elif field == "kbc":
        data["cdh.toml"] = data["cdh.toml"].replace("ccm_kbc", "cc_kbc")
    elif field == "endpoint":
        data["cdh.toml"] = data["cdh.toml"].replace("dsm.example.com", "other.example.com")
    elif field == "app":
        data["cdh.toml"] = data["cdh.toml"].replace("b001beef", "00000000")
    elif field == "missing":
        del data["aa.toml"]
    elif field == "signer":
        data["cdh.toml"] = data["cdh.toml"].replace("public signing key fixture", "untrusted signer")
    elif field == "repository":
        data["cdh.toml"] = data["cdh.toml"].replace("registry.example.com/workloads/site", "registry.example.com/other")
    else:
        data["cdh.toml"] = data["cdh.toml"].replace("reject", "insecureAcceptAnything")
    with pytest.raises(ValueError):
        validate_fortanix_initdata(encode(data), plan, "registry.example.com/workloads/site@sha256:" + "a" * 64)


@pytest.mark.parametrize("change", ["missing", "uri"])
def test_inline_image_policy_required_without_remote_override(tmp_path, change):
    plan = fortanix_plan(tmp_path)
    data = initdata(plan)
    if change == "missing":
        data["cdh.toml"] = data["cdh.toml"].split("[image]")[0]
    else:
        data["cdh.toml"] += 'image_security_policy_uri = "kbs:///default/policy/key"\n'
    with pytest.raises(ValueError):
        validate_fortanix_initdata(encode(data), plan, "registry.example.com/workloads/site@sha256:" + "a" * 64)


def test_fortanix_custom_runtime_keeps_full_pod_policy_checks(tmp_path):
    plan = fortanix_plan(tmp_path)
    pod = fortanix_pod(plan)
    path = tmp_path / "pod.yaml"
    path.write_text(yaml.safe_dump(pod))
    CoCoPlanPackager.validate_pod(path, plan)
    pod["spec"]["containers"][0]["securityContext"]["privileged"] = True
    path.write_text(yaml.safe_dump(pod))
    with pytest.raises(ValueError):
        CoCoPlanPackager.validate_pod(path, plan)


@pytest.mark.parametrize("wrong_backend", [False, True])
def test_fortanix_receipt_and_publication_without_kbs_inputs(tmp_path, wrong_backend):
    plan = fortanix_plan(tmp_path)
    owner, kit = prepare_kit(tmp_path)
    plan.internal["registry"] = {
        "endpoint": "https://registry.example.com",
        "ca_cert_file": str(tmp_path / "registry-ca.pem"),
        "publisher_username_file": str(tmp_path / "registry-user"),
        "publisher_password_file": str(tmp_path / "registry-password"),
    }

    def runner(*args, **kwargs):
        pod = owner / "pod.yaml"
        pod.write_text(yaml.safe_dump(fortanix_pod(plan)))
        (owner / "result.json").write_text(
            json.dumps(
                {
                    "schema": (
                        "nvflare-coco-build-result/v1" if wrong_backend else "nvflare-fortanix-coco-build-result/v1"
                    ),
                    "backend": "trustee" if wrong_backend else "fortanix_ccm",
                    "release_name": "site-v1",
                    "pod_yaml": str(pod),
                }
            )
        )

    with (
        patch("nvflare.lighter.cc_provision.impl.coco_packager.verify_folder_signature", return_value=True),
        patch("nvflare.lighter.cc_provision.impl.cc_packager.subprocess.run", side_effect=runner),
    ):
        if wrong_backend:
            with pytest.raises(ValueError, match="Invalid CoCo build result"):
                package_coco_plan(plan, kit, tmp_path / "public", None)
        else:
            result = package_coco_plan(plan, kit, tmp_path / "public", None)
            assert result.artifacts[0].metadata["runtime_class"] == "kata-fortanix-snp-gpu"
    assert "KBS_" not in (owner / "workload.env").read_text()
