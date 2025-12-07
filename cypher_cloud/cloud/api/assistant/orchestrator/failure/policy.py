import time
import random


class RetryPolicy:
    """
    Exponential backoff system.
    """

    def __init__(self) -> None:
        self.max_retries = 3
        self.base_delay = 0.6

    def should_retry(self, failure: Dict[str, str], attempt: int) -> bool:
        if attempt >= self.max_retries:
            return False
        if failure["category"] in ("auth",):
            return False  # auth errors are not retryable
        return True

    def delay(self, attempt: int) -> float:
        return self.base_delay * (2 ** attempt) + random.random() * 0.2
