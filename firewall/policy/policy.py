"""Firewall policy dataclass.

``FirewallPolicy`` is a frozen dataclass loaded from
:class:`core.config.settings.FirewallSettings` at startup. Once constructed
it's immutable; ``fingerprint()`` returns a stable SHA-256 hash that's
embedded in every Decision so we can audit retroactively which exact
policy was in force.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.security.hashing import sha256_hex
from firewall.risk.levels import RiskLevel


@dataclass(frozen=True)
class FirewallPolicy:
    block_threshold: float
    sanitize_threshold: float
    review_threshold: float
    finding_weight_floor: float
    pii_masking_enabled: bool = True
    references: tuple[str, ...] = (
        "P-001 deny prompt injection",
        "P-002 deny credential exfiltration",
        "P-003 sanitize PII",
        "P-004 review ambiguous suspicious prompts",
    )

    def __post_init__(self) -> None:
        # Thresholds must be ordered: review ≤ sanitize ≤ block.
        if not (
            0.0 <= self.review_threshold
            <= self.sanitize_threshold
            <= self.block_threshold
            <= 1.0
        ):
            raise ValueError(
                "thresholds must satisfy 0 ≤ review ≤ sanitize ≤ block ≤ 1; "
                f"got review={self.review_threshold} sanitize={self.sanitize_threshold} "
                f"block={self.block_threshold}"
            )
        if not 0.0 <= self.finding_weight_floor <= 1.0:
            raise ValueError("finding_weight_floor must be in [0, 1]")

    def risk_level_for(self, score: float) -> RiskLevel:
        if score >= self.block_threshold:
            return RiskLevel.MALICIOUS
        if score >= self.sanitize_threshold:
            return RiskLevel.HIGH_RISK
        if score >= self.review_threshold:
            return RiskLevel.SUSPICIOUS
        return RiskLevel.SAFE

    def fingerprint(self) -> str:
        """Stable SHA-256 hex over the policy fields.

        Same fields → same hash. Field order is the declaration order so
        the hash is reproducible across processes.
        """
        material = (
            f"{self.block_threshold}|{self.sanitize_threshold}|{self.review_threshold}|"
            f"{self.finding_weight_floor}|{self.pii_masking_enabled}|"
            f"{'/'.join(self.references)}"
        )
        return sha256_hex(material)
