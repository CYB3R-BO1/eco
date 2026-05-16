from __future__ import annotations

import pytest

from investigation.extraction.extractor import extract_iocs
from investigation.extraction.json_walker import extract_iocs_from_json
from investigation.extraction.patterns import refang
from resolution.types import EntityType


def test_refang_url() -> None:
    assert refang("hxxp://malicious[.]com") == "http://malicious.com"


def test_refang_email() -> None:
    assert refang("user[at]example[.]com") == "user@example.com"


def test_extract_url() -> None:
    iocs = extract_iocs("Visit https://example.com/path for details")
    types = {i.entity_type for i in iocs}
    assert EntityType.URL in types
    url_iocs = [i for i in iocs if i.entity_type is EntityType.URL]
    assert url_iocs[0].canonical_form == "https://example.com/path"


def test_extract_defanged_url_marks_lower_confidence() -> None:
    iocs = extract_iocs("Visit hxxp://malicious[.]com/path")
    url_iocs = [i for i in iocs if i.entity_type is EntityType.URL]
    assert len(url_iocs) == 1
    assert url_iocs[0].confidence == 0.85  # defanged → lowered
    assert url_iocs[0].canonical_form == "http://malicious.com/path"


def test_extract_ip_v4() -> None:
    iocs = extract_iocs("traffic from 8.8.8.8 observed")
    ips = [i for i in iocs if i.entity_type is EntityType.IP]
    assert ips and ips[0].canonical_form == "8.8.8.8"


def test_extract_md5_hash() -> None:
    payload = "hash=44d88612fea8a8f36de82e1278abb02f end"
    iocs = extract_iocs(payload)
    md5s = [i for i in iocs if i.entity_type is EntityType.HASH_MD5]
    assert md5s
    assert md5s[0].canonical_form == "44d88612fea8a8f36de82e1278abb02f"


def test_extract_dedupes_repeats() -> None:
    iocs = extract_iocs("a 8.8.8.8 b 8.8.8.8 c 8.8.8.8")
    ips = [i for i in iocs if i.entity_type is EntityType.IP]
    assert len(ips) == 1


def test_extract_filters_by_type() -> None:
    iocs = extract_iocs(
        "Mix https://example.com and 8.8.8.8 and 44d88612fea8a8f36de82e1278abb02f",
        types=[EntityType.IP],
    )
    assert all(i.entity_type is EntityType.IP for i in iocs)


def test_extract_from_json_carries_path() -> None:
    payload = {"alerts": [{"src": "8.8.8.8"}, {"url": "https://example.com"}]}
    iocs = extract_iocs_from_json(payload)
    sources = {i.metadata.get("source_context") for i in iocs}
    assert "$.alerts[0].src" in sources
    assert "$.alerts[1].url" in sources


def test_extract_rejects_oversized_payload() -> None:
    from investigation.extraction.extractor import MAX_INPUT_BYTES, TooLargeError

    with pytest.raises(TooLargeError):
        extract_iocs("x" * (MAX_INPUT_BYTES + 1))
