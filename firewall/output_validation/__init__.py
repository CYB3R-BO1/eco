"""Output validation — symmetric counterpart to input analysis.

Scans an LLM response for indicators that the response itself violates
policy: leaked system prompt, leaked PII, hidden instructions tucked in
output (commonly used in chained-agent attacks where one model's output
becomes another's input).

The validator's vocabulary is narrower than the input firewall's
(PASS / SANITIZE / BLOCK — no REQUIRE_REVIEW, since output-validation is
end-of-pipeline) but uses the same Signal / Sanitizer plumbing.
"""
