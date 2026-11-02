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

"""Offline Fortanix provisioning contract and negative configuration coverage."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from nvflare.lighter.cc_provision.impl.cc import CCBuilder
from nvflare.lighter.constants import CtxKey, ProvFileName
from nvflare.lighter.ctx import ProvisionContext
from nvflare.lighter.prov_utils import prepare_builders
from nvflare.lighter.provision import prepare_project
from nvflare.lighter.provisioner import Provisioner
from nvflare.lighter.utils import verify_folder_signature
from tests.unit_test.lighter.cc_provision.impl.test_cc import _coco_project


def _write(path, value):
    path.write_text(yaml.safe_dump(value, sort_keys=False))


def _fixture(tmp_path):
    _coco_project(tmp_path)
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Offline CCM fixture")])
    now = datetime.now(timezone.utc)
    root = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
        .sign(key, hashes.SHA256())
    )
    (tmp_path / "ccm.pem").write_bytes(root.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "cosign.pub").write_bytes(
        key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    common = yaml.safe_load((tmp_path / "cc_project.yml").read_text())
    common["attestation_services"] = {
        "ccm": {
            "type": "fortanix_ccm",
            "ccm_ca_cert_file": "ccm.pem",
            "image_signing_public_key_file": "cosign.pub",
            "site_domains": {"site-1": "site-1.example.com", "site-2": "site-2.example.com"},
            "attestation_token_endpoint": "http://127.0.0.1:8006/aa/token",
            "runtime_class": "kata-fortanix-snp-gpu",
            "dsm_endpoint": "https://dsm.example.com",
            "dsm_app_id": "11111111-1111-4111-8111-111111111111",
            "token_expiration_seconds": 300,
            "check_frequency_seconds": 120,
            "registration_token_timeout_seconds": 300,
            "refresh_token_timeout_seconds": 30,
            "get_token_request_timeout_seconds": 45,
        }
    }
    _write(tmp_path / "cc_project.yml", common)
    template = yaml.safe_load((tmp_path / "cc_site.yml").read_text())
    for site in ("site-1", "site-2"):
        config = {
            **template,
            "attestation": {"service": "ccm"},
            "coco": {**template["coco"], "release_name": site + "-v1"},
        }
        _write(tmp_path / f"cc_{site}.yml", config)
    definition = {
        "api_version": 3,
        "name": "fortanix",
        "cc_project_config": "cc_project.yml",
        "participants": [
            {"name": "server.example.com", "type": "server", "org": "owner", "fed_learn_port": 8002},
            *[
                {"name": site, "type": "client", "org": "owner", "cc_config": f"cc_{site}.yml"}
                for site in ("site-1", "site-2")
            ],
        ],
        "builders": [
            {"path": "nvflare.lighter.impl.workspace.WorkspaceBuilder"},
            {"path": "nvflare.lighter.impl.static_file.StaticFileBuilder", "args": {"config_folder": "config"}},
            {"path": "nvflare.lighter.impl.cert.CertBuilder"},
            {"path": "nvflare.lighter.cc_provision.impl.cc.CCBuilder"},
            {"path": "nvflare.lighter.impl.signature.SignatureBuilder"},
        ],
        "packager": {"path": "nvflare.lighter.cc_provision.impl.cc_packager.CCPackager"},
    }
    _write(tmp_path / "project.yaml", definition)
    return common, definition


def test_fortanix_real_builders_sign_two_clients_and_verifier_server(tmp_path):
    _, definition = _fixture(tmp_path)
    project = prepare_project(definition, project_file=str(tmp_path / "project.yaml"))
    ctx = Provisioner(str(tmp_path / "workspace"), prepare_builders(definition)).provision(project)
    assert ctx.get(CtxKey.PROVISION_SUCCESS) is True, ctx.get_errors()
    output = Path(ctx[CtxKey.CURRENT_PROD_DIR])
    for site in ("server.example.com", "site-1", "site-2"):
        kit = output / site
        manager = json.loads((kit / "local/cc_manager__p_resources.json").read_text())["components"][0]["args"]
        component_id = manager["cc_verifier_ids"][0]
        component = json.loads((kit / f"local/{component_id}__p_resources.json").read_text())["components"][0]
        args = component["args"]
        assert component["path"].endswith("fortanix_authorizer.FortanixAuthorizer")
        assert args["audience"] == "nvflare-fortanix:fortanix"
        assert args["site_domains"] == {"site-1": "site-1.example.com", "site-2": "site-2.example.com"}
        assert "trustee_public_key" not in args
        assert "dsm_app_id" not in args
        assert manager["require_site_binding"] is True
        assert manager["required_site_verifier_ids"] == {s: [component_id] for s in ("site-1", "site-2")}
        assert manager["registration_token_timeout"] == 300
        assert manager["refresh_token_timeout"] == 30
        assert manager["get_token_request_timeout"] == 45
        if site == "server.example.com":
            assert manager["cc_issuers_conf"] == []
            assert "site_name" not in args and "token_url" not in args
        else:
            assert args["site_name"] == site
            assert manager["cc_issuers_conf"] == [{"issuer_id": component_id, "token_expiration": 300}]
            assert verify_folder_signature(
                str(kit),
                str(kit / "startup/rootCA.pem"),
                single_signer=True,
                signature_file=ProvFileName.SIGNATURE_JSON,
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("site_domains", {"wrong-site": "site-1.example.com"}),
        ("site_domains", {"site-1": "duplicate.example.com", "site-2": "duplicate.example.com"}),
        ("runtime_class", ""),
        ("runtime_class", "Kata-Fortanix"),
        ("image_signing_public_key_file", "ca.pem"),
        ("dsm_endpoint", "http://dsm.example.com"),
        ("dsm_app_id", "not-a-uuid"),
        ("token_expiration_seconds", 301),
        ("check_frequency_seconds", 300),
        ("attestation_token_endpoint", "http://evil.example.com:8006/aa/token"),
        ("get_token_request_timeout_seconds", 20),
        ("ccm_ca_cert_file", "ca.pem"),
    ],
)
def test_fortanix_rejects_invalid_service_before_provisioning(tmp_path, field, value):
    common, definition = _fixture(tmp_path)
    common["attestation_services"]["ccm"][field] = value
    _write(tmp_path / "cc_project.yml", common)
    project = prepare_project(definition, project_file=str(tmp_path / "project.yaml"))
    with pytest.raises(ValueError):
        CCBuilder().initialize(project, ProvisionContext(str(tmp_path / "workspace"), project))


def test_fortanix_rejects_unqualified_tdx(tmp_path):
    _, definition = _fixture(tmp_path)
    config = yaml.safe_load((tmp_path / "cc_site-1.yml").read_text())
    config["cpu_tee"] = "intel_tdx"
    _write(tmp_path / "cc_site-1.yml", config)
    project = prepare_project(definition, project_file=str(tmp_path / "project.yaml"))
    with pytest.raises(ValueError, match="amd_sev_snp"):
        CCBuilder().initialize(project, ProvisionContext(str(tmp_path / "workspace"), project))


def test_two_ccm_services_have_distinct_namespaces_and_route_by_site(tmp_path):
    from unittest.mock import Mock

    from nvflare.app_opt.confidential_computing.cc_manager import CC_NAMESPACE, CC_TOKEN, CCManager
    from nvflare.app_opt.confidential_computing.fortanix_authorizer import FortanixAuthorizer

    common, definition = _fixture(tmp_path)
    service = common["attestation_services"]["ccm"]
    common["attestation_services"]["ccm-2"] = {**service, "site_domains": {"site-2": "site-2.example.com"}}
    service["site_domains"] = {"site-1": "site-1.example.com"}
    _write(tmp_path / "cc_project.yml", common)
    config = yaml.safe_load((tmp_path / "cc_site-2.yml").read_text())
    config["attestation"]["service"] = "ccm-2"
    _write(tmp_path / "cc_site-2.yml", config)
    project = prepare_project(definition, project_file=str(tmp_path / "project.yaml"))
    ctx = Provisioner(str(tmp_path / "workspace"), prepare_builders(definition)).provision(project)
    assert ctx.get(CtxKey.PROVISION_SUCCESS) is True, ctx.get_errors()
    local = Path(ctx[CtxKey.CURRENT_PROD_DIR]) / "server.example.com/local"
    manager_args = json.loads((local / "cc_manager__p_resources.json").read_text())["components"][0]["args"]
    components = {}
    for component_id in manager_args["cc_verifier_ids"]:
        spec = json.loads((local / f"{component_id}__p_resources.json").read_text())["components"][0]
        authorizer = FortanixAuthorizer(**spec["args"])
        authorizer.verify_for_site = Mock(return_value=True)
        components[component_id] = authorizer
    assert len(components) == 2
    namespaces = {component.get_namespace() for component in components.values()}
    assert len(namespaces) == 2
    manager = CCManager(**manager_args)
    fl_ctx = Mock()
    fl_ctx.get_engine.return_value.get_component.side_effect = components.get
    manager._setup_cc_authorizers(fl_ctx)
    for site in ("site-1", "site-2"):
        component_id = manager_args["required_site_verifier_ids"][site][0]
        own = components[component_id]
        other = next(component for key, component in components.items() if key != component_id)
        assert manager._check_namespaces(site, [{CC_NAMESPACE: own.get_namespace(), CC_TOKEN: "proof"}])
        assert not manager._check_namespaces(site, [{CC_NAMESPACE: other.get_namespace(), CC_TOKEN: "proof"}])
    first = next(iter(components.values()))
    kwargs = {
        "ccm_ca_certificates": (tmp_path / "ccm.pem").read_text(),
        "audience": "test",
        "site_domains": {"site-1": "site-1.example.com"},
    }
    assert FortanixAuthorizer(**kwargs).get_namespace() == "x-fortanix-coco"
    for namespace in (None, "", "other-service", "x-fortanix-coco-BAD", "x-fortanix-coco-" + "a" * 100):
        with pytest.raises(ValueError, match="namespace"):
            FortanixAuthorizer(**kwargs, namespace=namespace)
    assert first.get_namespace().startswith("x-fortanix-coco-")
