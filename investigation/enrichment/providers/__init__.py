from investigation.enrichment.providers.dns_mock import DnsMockProvider
from investigation.enrichment.providers.geoip_mock import GeoIpMockProvider
from investigation.enrichment.providers.virustotal_mock import VirusTotalMockProvider
from investigation.enrichment.providers.whois_mock import WhoisMockProvider

__all__ = [
    "DnsMockProvider",
    "GeoIpMockProvider",
    "VirusTotalMockProvider",
    "WhoisMockProvider",
]


def default_providers() -> list:
    """The provider set wired in at app startup. Real providers replace these."""
    return [
        WhoisMockProvider(),
        DnsMockProvider(),
        GeoIpMockProvider(),
        VirusTotalMockProvider(),
    ]
