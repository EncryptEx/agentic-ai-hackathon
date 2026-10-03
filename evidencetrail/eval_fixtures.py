"""Evaluator-only fixtures. Never import this from the agent, tools or policy path."""

# Illustrative policy labels for synthetic cases; not evidence of real-world accuracy.
EXPECTED_ACTIONS = {
    "case-familiar": "ALLOW",
    "case-takeover": "REVIEW",
    "case-manipulated": "CONTEXT_CHECK",  # simulated coercion answer "yes" -> REVIEW
    "case-legit-high": "ALLOW",
    "case-missing-tool": "REVIEW",  # status INCOMPLETE
}
