import time
from collections import defaultdict


class CircuitBreaker:
    """
    Temporarily disables unstable tools.
    """

    def __init__(self) -> None:
        self.failures = defaultdict(list)

    def record_failure(self, tool: str) -> None:
        self.failures[tool].append(time.time())

    def is_blocked(self, tool: str) -> bool:
        now = time.time()
        recent = [t for t in self.failures[tool] if now - t < 60]
        return len(recent) >= 3  # 3 failures in 1 minute = disable
