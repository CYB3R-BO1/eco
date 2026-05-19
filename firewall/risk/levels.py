"""Risk-level enumeration.

Mapped 1:1 from the final risk score via thresholds in
:class:`firewall.policy.policy.FirewallPolicy`. The four levels are the
public-facing taxonomy — internal scoring stays on the float scale so
small policy nudges don't reshape the API.
"""
from __future__ import annotations

from enum import Enum


class RiskLevel(str, Enum):
    SAFE = "SAFE"
    SUSPICIOUS = "SUSPICIOUS"
    HIGH_RISK = "HIGH_RISK"
    MALICIOUS = "MALICIOUS"
