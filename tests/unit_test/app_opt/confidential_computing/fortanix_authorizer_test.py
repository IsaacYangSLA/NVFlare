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

"""Synthetic PKI tests; these do not establish live CCM hardware appraisal."""

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest
import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID, ObjectIdentifier

from nvflare.apis.event_type import EventType
from nvflare.apis.fl_constant import FLContextKey
from nvflare.apis.fl_context import FLContext
from nvflare.apis.fl_exception import NotAuthenticated
from nvflare.app_opt.confidential_computing.cc_authorizer import CCTokenGenerateError
from nvflare.app_opt.confidential_computing.cc_manager import CC_INFO, CC_NAMESPACE, CC_TOKEN, CCManager
from nvflare.app_opt.confidential_computing.fortanix_authorizer import FortanixAuthorizer

MODULE = "nvflare.app_opt.confidential_computing.fortanix_authorizer"
AUDIENCE = "nvflare-fortanix:test-project"
SITE_DOMAINS = {"site-1": "site-1.apps.example.com", "site-2": "site-2.apps.example.com"}


def pem(certificate):
    return certificate.public_bytes(serialization.Encoding.PEM).decode()


def private_pem(key):
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


def name(value):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, value)])


def issue_certificate(
    subject,
    key,
    issuer_name,
    issuer_key,
    *,
    ca=False,
    path_length=None,
    san=None,
    eku=(ExtendedKeyUsageOID.CLIENT_AUTH,),
    digital_signature=True,
    key_cert_sign=None,
    not_before=None,
    not_after=None,
    name_constraints=None,
    unknown_critical=False,
):
    now = datetime.now(timezone.utc)
    if key_cert_sign is None:
        key_cert_sign = ca
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before or now - timedelta(minutes=1))
        .not_valid_after(not_after or now + timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=path_length), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=digital_signature,
                content_commitment=False,
                key_encipherment=not ca,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=key_cert_sign,
                crl_sign=ca,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()), critical=False)
    )
    if san is not None:
        builder = builder.add_extension(x509.SubjectAlternativeName(san), critical=False)
    if eku is not None and not ca:
        builder = builder.add_extension(x509.ExtendedKeyUsage(eku), critical=False)
    if name_constraints is not None:
        builder = builder.add_extension(name_constraints, critical=True)
    if unknown_critical:
        builder = builder.add_extension(
            x509.UnrecognizedExtension(ObjectIdentifier("1.2.3.4.5.6.7"), b"\x05\x00"), True
        )
    return builder.sign(issuer_key, hashes.SHA256())


@pytest.fixture(scope="module")
def keys():
    # Reuse synthetic keys across cases; every test gets independent certificates,
    # authorizers and replay state. No network or production key material is used.
    return {
        "root": rsa.generate_private_key(public_exponent=65537, key_size=2048),
        "intermediate": rsa.generate_private_key(public_exponent=65537, key_size=2048),
        "leaf": rsa.generate_private_key(public_exponent=65537, key_size=3072),
        "other": rsa.generate_private_key(public_exponent=65537, key_size=3072),
        "weak": rsa.generate_private_key(public_exponent=65537, key_size=2048),
        "ec": ec.generate_private_key(ec.SECP256R1()),
    }


@pytest.fixture
def pki(keys):
    root = issue_certificate(
        name("Pinned CCM zone root"), keys["root"], name("Pinned CCM zone root"), keys["root"], ca=True
    )
    intermediate = issue_certificate(
        name("CCM intermediate"), keys["intermediate"], root.subject, keys["root"], ca=True, path_length=0
    )

    def leaf(**options):
        key = options.pop("key", keys["leaf"])
        issuer = options.pop("issuer", intermediate)
        issuer_key = options.pop("issuer_key", keys["intermediate"])
        options.setdefault("san", [x509.DNSName(SITE_DOMAINS["site-1"])])
        return issue_certificate(name("CCM application credential"), key, issuer.subject, issuer_key, **options)

    certificate = leaf()

    def authorizer(site_name=None, **options):
        config = {"ccm_ca_certificates": pem(root), "audience": AUDIENCE, "site_domains": dict(SITE_DOMAINS)}
        config.update(options)
        return FortanixAuthorizer(**config, site_name=site_name)

    def proof(certificate=certificate, key=None, chain=None, headers=None, **claims):
        now = int(time.time())
        payload = {
            "version": 1,
            "cert_chain_pem": chain if chain is not None else pem(certificate) + pem(intermediate),
            "sub": "site-1",
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + 120,
            "jti": "a" * 48,
        }
        payload.update(claims)
        return jwt.encode(
            payload,
            key or keys["leaf"],
            algorithm="RS256",
            headers=headers or {"typ": "NVFLARE-FORTANIX+JWT"},
        )

    return {
        "root": root,
        "intermediate": intermediate,
        "leaf": leaf,
        "certificate": certificate,
        "authorizer": authorizer,
        "proof": proof,
        "reply": {"cert_pem": pem(certificate) + pem(intermediate), "key_pem": private_pem(keys["leaf"])},
    }


def test_guest_generation_and_single_use_site_bound_verification(pki):
    client, verifier = pki["authorizer"]("site-1"), pki["authorizer"]()
    with patch.object(client, "_get_guest_token", return_value=pki["reply"]):
        first, second = client.generate(), client.generate()
    assert client.get_namespace() == "x-fortanix-coco"
    assert first != second
    claims = jwt.decode(first, options={"verify_signature": False})
    assert claims["version"] == 1
    assert claims["sub"] == "site-1"
    assert claims["aud"] == AUDIENCE
    assert claims["exp"] - claims["iat"] <= 300
    assert len(claims["jti"]) == 48
    assert jwt.get_unverified_header(first)["typ"] == "NVFLARE-FORTANIX+JWT"
    assert "PRIVATE KEY" not in first
    assert "key_pem" not in claims
    assert "PRIVATE KEY" not in json.dumps(claims)
    assert not verifier.verify_for_site(first, "site-2")
    assert verifier.verify_for_site(first, "site-1")
    assert not verifier.verify(first)
    assert verifier.verify(second)


def test_verifier_only_never_calls_guest_api(pki):
    verifier = pki["authorizer"]()
    with patch.object(verifier, "_get_guest_token") as get:
        with pytest.raises(CCTokenGenerateError):
            verifier.generate()
        assert verifier.verify_for_site(pki["proof"](), "site-1")
    get.assert_not_called()


def test_configured_intermediate_completes_leaf_only_chain(pki):
    verifier = pki["authorizer"](ccm_intermediate_certificates=pem(pki["intermediate"]))
    assert verifier.verify_for_site(pki["proof"](chain=pem(pki["certificate"])), "site-1")
    assert not pki["authorizer"]().verify(pki["proof"](chain=pem(pki["certificate"])))


@pytest.mark.parametrize(
    "failure", ["unknown_root", "forged_intermediate", "non_ca", "missing_key_cert_sign", "path_length"]
)
def test_certificate_path_is_validated(pki, keys, failure):
    intermediate = pki["intermediate"]
    root = pki["root"]
    if failure == "unknown_root":
        root = issue_certificate(name("Untrusted root"), keys["other"], name("Untrusted root"), keys["other"], ca=True)
        intermediate = issue_certificate(
            name("CCM intermediate"), keys["intermediate"], root.subject, keys["other"], ca=True
        )
    elif failure == "forged_intermediate":
        intermediate = issue_certificate(
            intermediate.subject, keys["intermediate"], root.subject, keys["other"], ca=True
        )
    elif failure in ("non_ca", "missing_key_cert_sign"):
        intermediate = issue_certificate(
            intermediate.subject,
            keys["intermediate"],
            root.subject,
            keys["root"],
            ca=failure != "non_ca",
            key_cert_sign=False,
        )
    else:
        root = issue_certificate(root.subject, keys["root"], root.subject, keys["root"], ca=True, path_length=0)
    cert = pki["leaf"](issuer=intermediate)
    verifier = pki["authorizer"](ccm_ca_certificates=pem(root) if failure == "path_length" else pem(pki["root"]))
    assert not verifier.verify(pki["proof"](certificate=cert, chain=pem(cert) + pem(intermediate)))


def test_name_constraints_and_unknown_critical_extensions_rejected(pki, keys):
    constrained = issue_certificate(
        pki["intermediate"].subject,
        keys["intermediate"],
        pki["root"].subject,
        keys["root"],
        ca=True,
        name_constraints=x509.NameConstraints(
            permitted_subtrees=[x509.DNSName("other.example.com")], excluded_subtrees=None
        ),
    )
    cert = pki["leaf"](issuer=constrained)
    assert not pki["authorizer"]().verify(pki["proof"](certificate=cert, chain=pem(cert) + pem(constrained)))
    critical = pki["leaf"](unknown_critical=True)
    assert not pki["authorizer"]().verify(pki["proof"](certificate=critical))


@pytest.mark.parametrize(
    "san",
    [
        None,
        [],
        [x509.DNSName(SITE_DOMAINS["site-2"])],
        [x509.DNSName("*.apps.example.com")],
        [x509.DNSName(SITE_DOMAINS["site-1"]), x509.DNSName(SITE_DOMAINS["site-2"])],
        [x509.DNSName(SITE_DOMAINS["site-1"]), x509.UniformResourceIdentifier("spiffe://other/site")],
    ],
)
def test_leaf_requires_single_exact_site_dns(pki, san):
    certificate = pki["leaf"](san=san)
    assert not pki["authorizer"]().verify_for_site(pki["proof"](certificate=certificate), "site-1")


@pytest.mark.parametrize(
    "options",
    [
        {"ca": True},
        {"digital_signature": False},
        {"eku": None},
        {"eku": (ExtendedKeyUsageOID.SERVER_AUTH,)},
    ],
)
def test_leaf_usage_is_restricted(pki, options):
    certificate = pki["leaf"](**options)
    assert not pki["authorizer"]().verify(pki["proof"](certificate=certificate))


@pytest.mark.parametrize("key_type", ["weak", "ec"])
def test_leaf_requires_rsa_3072_or_stronger(pki, keys, key_type):
    key = keys[key_type]
    certificate = pki["leaf"](key=key)
    payload = jwt.decode(pki["proof"](certificate=certificate), options={"verify_signature": False})
    token = jwt.encode(
        payload, key, algorithm="ES256" if key_type == "ec" else "RS256", headers={"typ": "NVFLARE-FORTANIX+JWT"}
    )
    assert not pki["authorizer"]().verify(token)
    client = pki["authorizer"]("site-1")
    with patch.object(
        client,
        "_get_guest_token",
        return_value={"cert_pem": pem(certificate) + pem(pki["intermediate"]), "key_pem": private_pem(key)},
    ):
        with pytest.raises(CCTokenGenerateError):
            client.generate()


@pytest.mark.parametrize("state", ["expired", "future", "aged"])
def test_certificate_validity_and_age_bound_cannot_be_refreshed_by_new_jwt(pki, state):
    now = datetime.now(timezone.utc)
    options = {
        "expired": {"not_before": now - timedelta(hours=2), "not_after": now - timedelta(seconds=1)},
        "future": {"not_before": now + timedelta(minutes=1)},
        "aged": {"not_before": now - timedelta(seconds=3601)},
    }[state]
    certificate = pki["leaf"](**options)
    assert not pki["authorizer"]().verify(pki["proof"](certificate=certificate))
    client = pki["authorizer"]("site-1")
    reply = dict(pki["reply"], cert_pem=pem(certificate) + pem(pki["intermediate"]))
    with patch.object(client, "_get_guest_token", return_value=reply) as get:
        with pytest.raises(CCTokenGenerateError):
            client.generate_with_retry(2, threading.Event())
        get.assert_called_once()


def test_generated_proof_expiry_is_capped_by_certificate_age_and_validity(pki):
    now = datetime.now(timezone.utc)
    certificate = pki["leaf"](not_after=now + timedelta(seconds=60))
    client = pki["authorizer"]("site-1")
    with patch.object(
        client,
        "_get_guest_token",
        return_value=dict(pki["reply"], cert_pem=pem(certificate) + pem(pki["intermediate"])),
    ):
        token = client.generate()
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["exp"] <= int(certificate.not_valid_after_utc.timestamp())
    assert pki["authorizer"]().verify(token)


@pytest.mark.parametrize(
    "change",
    [
        {"version": 2},
        {"version": True},
        {"version": "1"},
        {"aud": "wrong-project"},
        {"aud": [AUDIENCE]},
        {"sub": "site-2"},
        {"sub": "unconfigured"},
        {"sub": 1},
        {"iat": True},
        {"iat": "123"},
        {"iat": 1.5},
        {"exp": True},
        {"exp": "9999999999"},
        {"exp": 9999999999.0},
        {"jti": "a" * 47},
        {"jti": "g" * 48},
        {"jti": "A" * 48},
        {"jti": None},
        {"cert_chain_pem": "invalid"},
        {"cert_chain_pem": []},
    ],
)
def test_signed_proof_claims_are_strict(pki, change):
    assert not pki["authorizer"]().verify(pki["proof"](**change))


@pytest.mark.parametrize("case", ["expired", "future", "old", "zero_lifetime", "excessive_lifetime", "nbf"])
def test_proof_time_bounds(pki, case):
    now = int(time.time())
    changes = {
        "expired": {"iat": now - 120, "exp": now - 1},
        "future": {"iat": now + 31, "exp": now + 120},
        "old": {"iat": now - 301, "exp": now + 1},
        "zero_lifetime": {"iat": now, "exp": now},
        "excessive_lifetime": {"iat": now, "exp": now + 301},
        "nbf": {"nbf": now + 1},
    }[case]
    assert not pki["authorizer"]().verify(pki["proof"](**changes))


@pytest.mark.parametrize(
    "headers", [{"typ": "JWT"}, {"typ": "NVFLARE-FORTANIX+JWT", "crit": ["unknown"], "unknown": True}]
)
def test_wrong_type_or_unrecognized_critical_jose_header_rejected(pki, headers):
    assert not pki["authorizer"]().verify(pki["proof"](headers=headers))


def test_invalid_signature_and_algorithm_rejected(pki, keys):
    assert not pki["authorizer"]().verify(pki["proof"](key=keys["other"]))
    claims = jwt.decode(pki["proof"](), options={"verify_signature": False})
    token = jwt.encode(claims, keys["leaf"], algorithm="RS512", headers={"typ": "NVFLARE-FORTANIX+JWT"})
    assert not pki["authorizer"]().verify(token)
    unsigned = jwt.encode(claims, key="", algorithm="none", headers={"typ": "NVFLARE-FORTANIX+JWT"})
    assert not pki["authorizer"]().verify(unsigned)


def test_verification_failures_do_not_consume_another_sites_proof(pki):
    verifier = pki["authorizer"]()
    token = pki["proof"]()
    assert not verifier.verify_for_site(token, "site-2")
    assert not verifier.verify_for_site(token, "")
    assert verifier.verify_for_site(token, "site-1")
    assert not verifier.verify_for_site(token, "site-1")


def test_replay_check_is_atomic_between_threads(pki):
    verifier, token = pki["authorizer"](), pki["proof"]()
    barrier = threading.Barrier(5)
    results = []

    def verify():
        barrier.wait(timeout=5)
        results.append(verifier.verify(token))

    workers = [threading.Thread(target=verify) for _ in range(4)]
    for worker in workers:
        worker.start()
    barrier.wait(timeout=5)
    for worker in workers:
        worker.join(timeout=5)
        assert not worker.is_alive()
    assert sorted(results) == [False, False, False, True]


@pytest.mark.parametrize(
    "reply", [{}, {"cert_pem": "SECRET", "key_pem": "SECRET"}, {"cert_pem": None, "key_pem": None}]
)
def test_guest_malformed_credentials_are_redacted_and_not_retried(pki, reply, caplog):
    client = pki["authorizer"]("site-1")
    with patch.object(client, "_get_guest_token", return_value=reply) as get:
        with pytest.raises(CCTokenGenerateError) as error:
            client.generate_with_retry(2, threading.Event())
        get.assert_called_once()
    assert "SECRET" not in str(error.value)
    assert "SECRET" not in caplog.text


def test_guest_private_key_must_match_certificate(pki, keys):
    client = pki["authorizer"]("site-1")
    with patch.object(client, "_get_guest_token", return_value=dict(pki["reply"], key_pem=private_pem(keys["other"]))):
        with pytest.raises(CCTokenGenerateError):
            client.generate()


@pytest.mark.parametrize(
    "url",
    [
        "http://host/aa/token",
        "https://127.0.0.1:8006/aa/token",
        "http://user@127.0.0.1:8006/aa/token",
        "http://127.0.0.1:8006/aa/token?token_type=kbs",
        "http://127.0.0.1:8006/aa/token#fragment",
        "http://127.0.0.1:8006/other",
        "http://127.0.0.2:8006/aa/token",
    ],
)
def test_credential_endpoint_must_be_unambiguous_local_guest_api(pki, url):
    with pytest.raises(ValueError):
        pki["authorizer"]("site-1", token_url=url)


def test_guest_transport_disables_proxies_and_redirects(pki):
    client = pki["authorizer"]("site-1")
    with patch(MODULE + ".requests.Session") as factory:
        session = factory.return_value.__enter__.return_value
        response = session.get.return_value.__enter__.return_value
        response.status_code = 200
        response.iter_content.return_value = [json.dumps(pki["reply"]).encode()]
        assert client._get_guest_token() == pki["reply"]
        assert session.trust_env is False
        assert session.get.call_args.kwargs["allow_redirects"] is False
        assert session.get.call_args.kwargs["stream"] is True
        assert session.get.call_args.kwargs["params"] == {"token_type": "ccm_as"}
        response.status_code = 302
        with pytest.raises(CCTokenGenerateError):
            client._get_guest_token()
        response.status_code = 200
        response.iter_content.return_value = [b"x" * (1024 * 1024 + 1)]
        with pytest.raises(CCTokenGenerateError):
            client._get_guest_token()


@pytest.mark.parametrize("status", [429, 502, 503, 504, 400, 401, 403, 500, 302])
def test_only_transient_http_statuses_are_retried(pki, status):
    client = pki["authorizer"]("site-1", retry_initial_delay=0.001)
    with patch(MODULE + ".requests.Session") as factory:
        sessions = []
        for code in (status, 200):
            session = MagicMock()
            response = session.__enter__.return_value.get.return_value.__enter__.return_value
            response.status_code = code
            response.iter_content.return_value = [json.dumps(pki["reply"]).encode()]
            sessions.append(session)
        factory.side_effect = sessions
        if status in (429, 502, 503, 504):
            assert pki["authorizer"]().verify(client.generate_with_retry(2, threading.Event()))
            assert factory.call_count == 2
        else:
            with pytest.raises(CCTokenGenerateError):
                client.generate_with_retry(2, threading.Event())
            assert factory.call_count == 1


@pytest.mark.parametrize("failure", [requests.exceptions.Timeout, requests.exceptions.ConnectionError])
def test_transport_failure_is_redacted_then_recovers(pki, failure, caplog):
    client = pki["authorizer"]("site-1", retry_initial_delay=0.001)
    with patch.object(client, "_get_guest_token", side_effect=[failure("PRIVATE SECRET"), pki["reply"]]) as get:
        token = client.generate_with_retry(2, threading.Event())
    assert get.call_count == 2
    assert pki["authorizer"]().verify(token)
    assert "SECRET" not in caplog.text


def test_retry_attempt_budget(pki):
    client = pki["authorizer"]("site-1", retry_max_attempts=3, retry_initial_delay=0.001)
    with patch.object(client, "_get_guest_token", side_effect=requests.exceptions.Timeout("SECRET")) as get:
        with pytest.raises(CCTokenGenerateError):
            client.generate_with_retry(2, threading.Event())
    assert get.call_count == 3


def test_stalled_guest_request_is_bounded_and_single_flight(pki):
    client = pki["authorizer"]("site-1")
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def stalled():
        started.set()
        try:
            assert release.wait(5)
            return pki["reply"]
        finally:
            finished.set()

    with patch.object(client, "_get_guest_token", side_effect=stalled) as get:
        try:
            before = time.monotonic()
            with pytest.raises(CCTokenGenerateError):
                client.generate_with_retry(0.1, threading.Event())
            assert time.monotonic() - before < 1
            assert started.is_set()
            with pytest.raises(CCTokenGenerateError):
                client.generate_with_retry(0.1, threading.Event())
            assert get.call_count == 1
        finally:
            release.set()
            assert finished.wait(2)
            assert client._generation_lock.acquire(timeout=2)
            client._generation_lock.release()
    with patch.object(client, "_get_guest_token", return_value=pki["reply"]):
        assert pki["authorizer"]().verify(client.generate_with_retry(2, threading.Event()))


def test_precancelled_generation_skips_guest_api(pki):
    client, cancel = pki["authorizer"]("site-1"), threading.Event()
    cancel.set()
    with patch.object(client, "_get_guest_token") as get:
        with pytest.raises(CCTokenGenerateError):
            client.generate_with_retry(2, cancel)
        get.assert_not_called()


@pytest.mark.parametrize(
    "options",
    [
        {"proof_lifetime_seconds": True},
        {"proof_lifetime_seconds": 301},
        {"proof_lifetime_seconds": 0},
        {"proof_lifetime_seconds": 1.5},
        {"max_certificate_age_seconds": 0},
        {"max_certificate_age_seconds": 86401},
        {"max_certificate_age_seconds": True},
        {"proof_iat_leeway_seconds": -1},
        {"proof_iat_leeway_seconds": 181},
        {"proof_iat_leeway_seconds": True},
        {"retry_max_attempts": 0},
        {"retry_max_attempts": True},
        {"site_domains": {}},
        {"site_domains": {"site-1": "*.example.com"}},
        {"site_domains": {"site-1": "same.example.com", "site-2": "same.example.com"}},
        {"audience": ""},
        {"ccm_ca_certificates": "not a certificate"},
    ],
)
def test_invalid_configuration_rejected(pki, options):
    with pytest.raises((ValueError, TypeError)):
        pki["authorizer"](**options)


def test_cc_manager_enforces_authenticated_peer_site_with_real_verifier(pki):
    verifier = pki["authorizer"]()
    manager = CCManager(
        [],
        ["fortanix"],
        cc_enabled_sites=["site-1", "site-2"],
        required_site_verifier_ids={"site-1": ["fortanix"], "site-2": ["fortanix"]},
        require_site_binding=True,
    )
    manager.cc_verifiers = {verifier.get_namespace(): verifier}
    manager.required_site_namespaces = {site: {verifier.get_namespace()} for site in SITE_DOMAINS}
    context, peer = FLContext(), FLContext()
    context.set_peer_context(peer)
    token = pki["proof"]()
    context.set_prop(FLContextKey.CLIENT_NAME, "site-2")
    peer.set_prop(CC_INFO, {"site-2": [{CC_NAMESPACE: verifier.get_namespace(), CC_TOKEN: token}]})
    with pytest.raises(NotAuthenticated):
        manager.handle_event(EventType.CLIENT_REGISTER_RECEIVED, context)
    context.set_prop(FLContextKey.CLIENT_NAME, "site-1")
    peer.set_prop(CC_INFO, {"site-1": [{CC_NAMESPACE: verifier.get_namespace(), CC_TOKEN: token}]})
    manager.handle_event(EventType.CLIENT_REGISTER_RECEIVED, context)


def test_dns_comparison_is_case_insensitive_without_wildcard_expansion(pki):
    certificate = pki["leaf"](san=[x509.DNSName("SITE-1.APPS.EXAMPLE.COM")])
    verifier = pki["authorizer"](site_domains={"site-1": "SITE-1.apps.example.com"})
    assert verifier.verify_for_site(pki["proof"](certificate=certificate), "site-1")


def test_replay_cache_fails_closed_at_capacity_and_prunes_expired_entries(pki):
    verifier = pki["authorizer"]()
    expiry = int(time.time()) + 120
    verifier.seen = {("site-1", str(index)): expiry for index in range(10000)}
    token = pki["proof"]()
    assert not verifier.verify(token)
    verifier.seen[("site-1", "0")] = int(time.time()) - 1
    assert verifier.verify(token)
    assert len(verifier.seen) == 10000
    assert not verifier.verify(token)


def test_certificate_age_also_caps_generated_proof_lifetime(pki):
    now = datetime.now(timezone.utc)
    certificate = pki["leaf"](not_before=now - timedelta(seconds=3580))
    client = pki["authorizer"]("site-1")
    reply = dict(pki["reply"], cert_pem=pem(certificate) + pem(pki["intermediate"]))
    with patch.object(client, "_get_guest_token", return_value=reply):
        token = client.generate()
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["exp"] <= int(certificate.not_valid_before_utc.timestamp()) + 3600
    assert 0 < claims["exp"] - claims["iat"] <= 20
    assert pki["authorizer"]().verify(token)


@pytest.mark.parametrize("phase", ["request", "backoff"])
def test_cancellation_interrupts_running_generation_and_recovers(pki, phase):
    client = pki["authorizer"]("site-1", retry_initial_delay=5, retry_max_delay=5)
    cancel = threading.Event()
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    outcome = {}

    def guest_request():
        if phase == "backoff":
            raise requests.exceptions.Timeout("temporary transport failure")
        started.set()
        try:
            assert release.wait(5)
            return pki["reply"]
        finally:
            finished.set()

    def retry_delay(*args):
        started.set()
        return 5

    def caller():
        try:
            outcome["token"] = client.generate_with_retry(5, cancel)
        except CCTokenGenerateError as error:
            outcome["error"] = str(error)

    caller_thread = threading.Thread(target=caller, daemon=True)
    with patch.object(client, "_get_guest_token", side_effect=guest_request) as get:
        with patch(MODULE + ".random.uniform", side_effect=retry_delay):
            try:
                caller_thread.start()
                assert started.wait(2)
                before = time.monotonic()
                cancel.set()
                caller_thread.join(timeout=1)
                assert not caller_thread.is_alive()
                assert time.monotonic() - before < 1
                assert "cancelled" in outcome.get("error", "")
                assert "token" not in outcome
                assert get.call_count == 1
                if phase == "request":
                    # Cancellation bounds the caller's wait, but the outstanding
                    # guest request keeps its guard until its worker exits.
                    assert not client._generation_lock.acquire(blocking=False)
                    release.set()
                    assert finished.wait(2)
                assert client._generation_lock.acquire(timeout=2)
                client._generation_lock.release()
                assert get.call_count == 1
            finally:
                cancel.set()
                release.set()
                caller_thread.join(timeout=2)
    with patch.object(client, "_get_guest_token", return_value=pki["reply"]):
        assert pki["authorizer"]().verify(client.generate_with_retry(2, threading.Event()))
