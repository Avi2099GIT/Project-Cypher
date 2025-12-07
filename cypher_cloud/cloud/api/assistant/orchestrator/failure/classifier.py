from __future__ import annotations

from typing import Dict


class FailureClassifier:
    """
    Translates errors into actionable categories.
    """

    @staticmethod
    def classify(error: str) -> Dict[str, str]:
        e = error.lower()

        if "timeout" in e:
            return {"category": "timeout", "severity": "medium"}
        if "rate limit" in e or "quota" in e:
            return {"category": "rate_limit", "severity": "high"}
        if "auth" in e or "permission" in e:
            return {"category": "auth", "severity": "high"}
        if "not found" in e or "404" in e:
            return {"category": "not_found", "severity": "low"}
        if "connection" in e:
            return {"category": "network", "severity": "medium"}
        if "invalid" in e or "schema" in e:
            return {"category": "bad_input", "severity": "low"}

        return {"category": "unknown", "severity": "medium"}
