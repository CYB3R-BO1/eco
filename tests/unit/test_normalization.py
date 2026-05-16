from __future__ import annotations

import pytest

from resolution.normalization import (
    normalize_domain,
    normalize_email,
    normalize_hash,
    normalize_ip,
    normalize_url,
    parent_domain,
)
from resolution.service import EntityResolutionService
from resolution.types import EntityType


def test_domain_case_insensitive() -> None:
    assert normalize_domain("Google.com") == "google.com"


def test_domain_strips_protocol_and_path() -> None:
    assert normalize_domain("https://Google.com/login?ref=foo") == "google.com"


def test_domain_strips_trailing_dot() -> None:
    assert normalize_domain("example.com.") == "example.com"


def test_domain_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        normalize_domain("not a domain")


def test_url_lowercases_host_keeps_path() -> None:
    assert normalize_url("HTTPS://Google.COM/Login") == "https://google.com/Login"


def test_url_strips_fragment() -> None:
    assert normalize_url("https://google.com/path#section") == "https://google.com/path"


def test_parent_domain() -> None:
    assert parent_domain("https://google.com/login") == "google.com"


def test_ipv4_canonicalisation() -> None:
    assert normalize_ip("8.8.8.8") == "8.8.8.8"


def test_ipv6_compression() -> None:
    assert normalize_ip("2001:0db8:0000:0000:0000:0000:0000:0001") == "2001:db8::1"


def test_email_lowercases() -> None:
    assert normalize_email("User@Example.COM") == "user@example.com"


def test_hash_md5() -> None:
    canonical, etype = normalize_hash("44D88612FEA8A8F36DE82E1278ABB02F")
    assert canonical == "44d88612fea8a8f36de82e1278abb02f"
    assert etype is EntityType.HASH_MD5


def test_hash_sha1_length() -> None:
    canonical, etype = normalize_hash("a" * 40)
    assert canonical == "a" * 40
    assert etype is EntityType.HASH_SHA1


def test_hash_sha256_length() -> None:
    canonical, etype = normalize_hash("0" * 64)
    assert etype is EntityType.HASH_SHA256


def test_resolution_service_normalize_classifies_variants() -> None:
    svc = EntityResolutionService()

    plain = svc.normalize("google.com", EntityType.DOMAIN)
    assert plain.canonical_form == "google.com"
    assert plain.variant_relation is None

    cased = svc.normalize("Google.com", EntityType.DOMAIN)
    assert cased.canonical_form == "google.com"
    assert cased.variant_relation == "case_variant"

    with_proto = svc.normalize("https://google.com", EntityType.DOMAIN)
    assert with_proto.canonical_form == "google.com"
    assert with_proto.variant_relation == "protocol_stripped"
