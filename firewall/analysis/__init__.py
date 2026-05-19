"""Analysis layers 1, 2, 3, 5 of the six-layer firewall pipeline.

(Layer 4 — composite rules — lives in :mod:`firewall.rules.engine`
because rules are evaluated against the signals already produced here.
Layer 6 — risk scoring — lives in :mod:`firewall.risk.scorer`.)
"""
