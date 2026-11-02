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

"""Fortanix CCM certificate verification and guest-held key proof of possession.

CCM issuance policy must restrict each configured DNS SAN to the approved FL
site, build, InitData and required GPU appraisal. Certificates do not expose
locally verifiable measurements: trusting their issuing CA delegates those
checks to CCM. All callers of the guest-local AA API must be trusted.

Certificate age measures certificate freshness, not hardware attestation time.
AA may cache a credential until expiry; an aged credential is rejected rather
than forcibly refreshed. This authorizer does not implement certificate
revocation. Replay protection is bounded and local to this process.

The AA response contains a private key, consumed only in memory. It must never
be forwarded, persisted, logged or included in exception messages.
"""

import json
import logging
import math
import random
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import jwt
import requests
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID
from cryptography.x509.verification import PolicyBuilder, Store

from .cc_authorizer import CCAuthorizer, CCTokenGenerateError

FORTANIX_NAMESPACE = "x-fortanix-coco"
PROOF_TYPE = "NVFLARE-FORTANIX+JWT"
PROOF_VERSION = 1
MAX_TOKEN_BYTES = 128 * 1024
_MAX_CERTIFICATES = 7
_PEM_CERTIFICATE = re.compile(rb"-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----")
_DNS_NAME = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)


class _TemporaryTokenError(CCTokenGenerateError):
    """A guest API transport failure that may safely be retried."""


class FortanixAuthorizer(CCAuthorizer):
    """Authorize CCM-issued site credentials under explicitly pinned roots.

    ccm_ca_certificates and ccm_intermediate_certificates contain PEM, not paths.
    site_domains maps FL site names to unique, exact DNS SANs. site_name=None
    creates a verifier-only instance. Only an RSA key of at least 3072 bits is
    supported by this initial CCM integration.
    """

    supports_site_binding = True

    def __init__(
        self,
        ccm_ca_certificates,
        audience,
        site_domains,
        site_name=None,
        ccm_intermediate_certificates="",
        token_url="http://127.0.0.1:8006/aa/token",
        proof_lifetime_seconds=300,
        max_certificate_age_seconds=3600,
        proof_iat_leeway_seconds=30,
        retry_max_attempts=5,
        retry_initial_delay=1.0,
        retry_max_delay=15.0,
        retry_backoff_multiplier=2.0,
        retry_jitter_ratio=0.5,
    ):
        if not isinstance(audience, str) or not audience.strip():
            raise ValueError("A project-specific audience is required")
        if not isinstance(site_domains, dict) or not site_domains:
            raise ValueError("site_domains must be a non-empty site mapping")
        domains = {}
        for site, domain in site_domains.items():
            if not isinstance(site, str) or not site.strip() or not isinstance(domain, str):
                raise ValueError("Invalid site_domains mapping")
            domain = domain.lower()
            if not _DNS_NAME.fullmatch(domain) or domain in domains.values():
                raise ValueError("Site domains must be unique exact DNS names")
            domains[site] = domain
        if site_name is not None and (not isinstance(site_name, str) or site_name not in domains):
            raise ValueError("site_name must identify a configured site or be None")
        for name, value, lower, upper in (
            ("proof_lifetime_seconds", proof_lifetime_seconds, 1, 300),
            ("max_certificate_age_seconds", max_certificate_age_seconds, 1, 86400),
            ("proof_iat_leeway_seconds", proof_iat_leeway_seconds, 0, 180),
            ("retry_max_attempts", retry_max_attempts, 1, 100),
        ):
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f"{name} must be {lower}..{upper}")
        for name, value in (
            ("retry_initial_delay", retry_initial_delay),
            ("retry_max_delay", retry_max_delay),
            ("retry_backoff_multiplier", retry_backoff_multiplier),
            ("retry_jitter_ratio", retry_jitter_ratio),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        if retry_initial_delay <= 0 or retry_max_delay < retry_initial_delay:
            raise ValueError("Require 0 < retry_initial_delay <= retry_max_delay")
        if retry_backoff_multiplier < 1:
            raise ValueError("retry_backoff_multiplier must be >= 1")
        if not 0 <= retry_jitter_ratio <= 1:
            raise ValueError("retry_jitter_ratio must be 0..1")
        try:
            url = urlsplit(token_url)
            port = url.port
            if (
                url.scheme != "http"
                or url.hostname != "127.0.0.1"
                or url.path != "/aa/token"
                or url.username is not None
                or url.password is not None
                or url.query
                or url.fragment
                or port is None
                or not 1 <= port <= 65535
            ):
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError(
                "token_url must address the guest-local 127.0.0.1 /aa/token API with an explicit port"
            ) from None

        roots = self._certificates(ccm_ca_certificates)
        intermediates = self._certificates(ccm_intermediate_certificates, allow_empty=True)
        for certificate in roots + intermediates:
            self._validate_ca(certificate)
        self._store = Store(roots)
        self._intermediates = intermediates
        self.audience = audience
        self.site_domains = domains
        self.site_name = site_name
        self.token_url = token_url
        self.proof_lifetime_seconds = proof_lifetime_seconds
        self.max_certificate_age_seconds = max_certificate_age_seconds
        self.proof_iat_leeway_seconds = proof_iat_leeway_seconds
        self.retry_max_attempts = retry_max_attempts
        self.retry_initial_delay = retry_initial_delay
        self.retry_max_delay = retry_max_delay
        self.retry_backoff_multiplier = retry_backoff_multiplier
        self.retry_jitter_ratio = retry_jitter_ratio
        self.seen = {}
        self.lock = threading.Lock()
        self._generation_lock = threading.Lock()
        self._generation_context = threading.local()

    @staticmethod
    def _certificates(pem, allow_empty=False):
        if not isinstance(pem, str) or len(pem) > MAX_TOKEN_BYTES:
            raise ValueError("Invalid certificate bundle")
        try:
            data = pem.encode("ascii")
            blocks = _PEM_CERTIFICATE.findall(data)
            if _PEM_CERTIFICATE.sub(b"", data).strip() or len(blocks) > _MAX_CERTIFICATES:
                raise ValueError
            if not blocks and not allow_empty:
                raise ValueError
            return [x509.load_pem_x509_certificate(block) for block in blocks]
        except (ValueError, UnicodeError):
            raise ValueError("Invalid certificate bundle") from None

    @staticmethod
    def _validate_ca(certificate):
        try:
            constraints = certificate.extensions.get_extension_for_class(x509.BasicConstraints).value
            usage = certificate.extensions.get_extension_for_class(x509.KeyUsage).value
            if not constraints.ca or not usage.key_cert_sign:
                raise ValueError
        except (ValueError, x509.ExtensionNotFound):
            raise ValueError("Pinned issuers must be CA certificates with certificate-signing key usage") from None

    def get_namespace(self):
        return FORTANIX_NAMESPACE

    def _credential(self, pem, site, now):
        certificates = self._certificates(pem)
        leaf = certificates[0]
        verifier = (
            PolicyBuilder()
            .store(self._store)
            .max_chain_depth(5)
            .time(datetime.fromtimestamp(now, timezone.utc))
            .build_client_verifier()
        )
        verifier.verify(leaf, certificates[1:] + self._intermediates)
        constraints = leaf.extensions.get_extension_for_class(x509.BasicConstraints).value
        usage = leaf.extensions.get_extension_for_class(x509.KeyUsage).value
        eku = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names = list(san)
        if (
            constraints.ca
            or not usage.digital_signature
            or ExtendedKeyUsageOID.CLIENT_AUTH not in eku
            or len(names) != 1
            or not isinstance(names[0], x509.DNSName)
            or names[0].value.lower() != self.site_domains.get(site)
        ):
            raise ValueError("Certificate does not authorize the configured site")
        public = leaf.public_key()
        if not isinstance(public, rsa.RSAPublicKey) or public.key_size < 3072:
            raise ValueError("CCM proof key must be RSA with at least 3072 bits")
        issued = leaf.not_valid_before_utc.timestamp()
        expires = min(leaf.not_valid_after_utc.timestamp(), issued + self.max_certificate_age_seconds)
        if not issued <= now < expires:
            raise ValueError("CCM certificate is outside its accepted freshness interval")
        return public, issued, expires

    def _check_generation_budget(self):
        check = getattr(self._generation_context, "check_budget", None)
        if check is not None:
            check()

    def _get_guest_token(self):
        self._check_generation_budget()
        deadline = getattr(self._generation_context, "deadline", None)
        remaining = 60.0 if deadline is None else min(60.0, deadline - time.monotonic())
        if remaining <= 0:
            raise CCTokenGenerateError("Token generation deadline exhausted")
        with requests.Session() as session:
            session.trust_env = False
            with session.get(
                self.token_url,
                params={"token_type": "ccm_as"},
                timeout=(min(5.0, remaining), remaining),
                allow_redirects=False,
                stream=True,
            ) as response:
                if response.status_code in (429, 502, 503, 504):
                    raise _TemporaryTokenError("Guest token API temporarily unavailable")
                if response.status_code != 200:
                    raise CCTokenGenerateError("Guest token API rejected the request")
                chunks, size = [], 0
                for chunk in response.iter_content(chunk_size=4096):
                    self._check_generation_budget()
                    size += len(chunk)
                    if size > MAX_TOKEN_BYTES:
                        raise CCTokenGenerateError("Guest token API response exceeds size limit")
                    chunks.append(chunk)
                self._check_generation_budget()
                return json.loads(b"".join(chunks))

    def generate(self):
        """Generate once; temporary failures are retried only by generate_with_retry."""
        if self.site_name is None:
            raise CCTokenGenerateError("Verifier-only Fortanix authorizer cannot generate tokens")
        try:
            reply = self._get_guest_token()
            pem = reply["cert_pem"]
            now = int(time.time())
            public, issued, expires = self._credential(pem, self.site_name, now)
            private_pem = reply["key_pem"]
            if not isinstance(private_pem, str) or len(private_pem) > MAX_TOKEN_BYTES:
                raise ValueError("Invalid guest key")
            private = serialization.load_pem_private_key(private_pem.encode(), password=None)
            if (
                not isinstance(private, rsa.RSAPrivateKey)
                or private.public_key().public_numbers() != public.public_numbers()
            ):
                raise ValueError("Guest private key does not match CCM certificate")
            expiry = min(now + self.proof_lifetime_seconds, int(expires))
            if expiry <= now or now < issued:
                raise ValueError("CCM certificate cannot support a fresh proof")
            token = jwt.encode(
                {
                    "version": PROOF_VERSION,
                    "cert_chain_pem": pem,
                    "sub": self.site_name,
                    "aud": self.audience,
                    "iat": now,
                    "exp": expiry,
                    "jti": secrets.token_hex(24),
                },
                private,
                algorithm="RS256",
                headers={"typ": PROOF_TYPE},
            )
            if len(token) > MAX_TOKEN_BYTES:
                raise ValueError("Generated proof exceeds size limit")
            return token
        except (_TemporaryTokenError, requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            raise _TemporaryTokenError("Guest token API temporarily unavailable") from None
        except Exception:
            raise CCTokenGenerateError("Unable to generate a verified Fortanix attestation proof") from None

    def generate_with_retry(self, timeout, cancel_event):
        """Bound caller wait and keep one worker until an in-flight request exits.

        Python cannot terminate a stalled request. The worker retains its lock
        after caller cancellation/timeout, preventing accumulation of workers.
        """
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("Token generation timeout must be finite and positive")
        deadline = time.monotonic() + timeout
        stopped, done = threading.Event(), threading.Event()
        outcome = {}

        def check_budget():
            if cancel_event.is_set() or stopped.is_set():
                raise CCTokenGenerateError("Token generation cancelled")
            if time.monotonic() >= deadline:
                raise CCTokenGenerateError("Token generation deadline exhausted")

        def wait(delay):
            until = min(deadline, time.monotonic() + delay)
            while time.monotonic() < until:
                check_budget()
                stopped.wait(min(0.05, max(0, until - time.monotonic())))
            check_budget()

        def run():
            self._generation_context.deadline = deadline
            self._generation_context.check_budget = check_budget
            try:
                delay = self.retry_initial_delay
                for attempt in range(1, self.retry_max_attempts + 1):
                    check_budget()
                    try:
                        token = self.generate()
                        check_budget()
                        outcome["token"] = token
                        return
                    except _TemporaryTokenError:
                        check_budget()
                        if attempt == self.retry_max_attempts:
                            raise CCTokenGenerateError("Token generation retry attempts exhausted") from None
                        logging.getLogger(__name__).warning(
                            "Temporary guest token API failure; retrying after attempt %d", attempt
                        )
                        wait(random.uniform(delay * (1 - self.retry_jitter_ratio), delay))
                        delay = min(self.retry_max_delay, delay * self.retry_backoff_multiplier)
            except CCTokenGenerateError as error:
                outcome["error"] = CCTokenGenerateError(str(error))
            except Exception:
                outcome["error"] = CCTokenGenerateError("Unable to generate a verified Fortanix attestation proof")
            finally:
                self._generation_lock.release()
                done.set()

        while True:
            check_budget()
            if self._generation_lock.acquire(blocking=False):
                break
            wait(0.05)
        worker = threading.Thread(target=run, daemon=True, name="Fortanix-TokenGeneration")
        try:
            worker.start()
        except Exception:
            self._generation_lock.release()
            raise CCTokenGenerateError("Unable to start token generation") from None
        try:
            while not done.wait(min(0.05, max(0, deadline - time.monotonic()))):
                check_budget()
            check_budget()
            if "error" in outcome:
                raise outcome["error"]
            return outcome["token"]
        finally:
            stopped.set()

    def verify(self, token):
        """Verify validity; use verify_for_site at a transport-authenticated peer boundary."""
        return self._verify(token)

    def verify_for_site(self, token, site_name):
        """Bind proof identity to the independently authenticated FL peer."""
        if not isinstance(site_name, str) or not site_name:
            return False
        return self._verify(token, expected_site=site_name)

    def _verify(self, token, expected_site=None):
        try:
            if not isinstance(token, str) or len(token) > MAX_TOKEN_BYTES:
                return False
            header = jwt.get_unverified_header(token)
            if header != {"alg": "RS256", "typ": PROOF_TYPE}:
                return False
            untrusted = jwt.decode(token, options={"verify_signature": False})
            site = untrusted["sub"]
            if not isinstance(site, str) or site not in self.site_domains:
                return False
            now = time.time()
            public, issued, expires = self._credential(untrusted["cert_chain_pem"], site, now)
            proof = jwt.decode(
                token,
                public,
                algorithms=["RS256"],
                audience=self.audience,
                options={
                    "require": ["version", "cert_chain_pem", "sub", "aud", "iat", "exp", "jti"],
                    "verify_iat": False,
                },
                leeway=0,
            )
            if (
                type(proof["version"]) is not int
                or proof["version"] != PROOF_VERSION
                or proof["aud"] != self.audience
                or (expected_site is not None and proof["sub"] != expected_site)
                or type(proof["iat"]) is not int
                or type(proof["exp"]) is not int
                or ("nbf" in proof and type(proof["nbf"]) is not int)
                or not -self.proof_iat_leeway_seconds <= now - proof["iat"] <= self.proof_lifetime_seconds
                or not 0 < proof["exp"] - proof["iat"] <= self.proof_lifetime_seconds
                or not issued <= proof["iat"] < proof["exp"] <= expires
                or not isinstance(proof["jti"], str)
                or not re.fullmatch(r"[0-9a-f]{48}", proof["jti"])
            ):
                return False
            with self.lock:
                self.seen = {key: expiry for key, expiry in self.seen.items() if expiry > now}
                key = (proof["sub"], proof["jti"])
                if key in self.seen or len(self.seen) >= 10000:
                    return False
                self.seen[key] = proof["exp"]
            return True
        except Exception:
            return False
