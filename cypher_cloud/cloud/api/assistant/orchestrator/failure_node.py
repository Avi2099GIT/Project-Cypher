from cloud.api.assistant.orchestrator.failure.classifier import FailureClassifier
from cloud.api.assistant.orchestrator.failure.policy import RetryPolicy
from cloud.api.assistant.orchestrator.failure.breaker import CircuitBreaker
from cloud.api.assistant.orchestrator.failure.memory import FailureMemory
from cloud.api.assistant.orchestrator.failure.recovery import RecoveryPlanner
from cloud.api.assistant.orchestrator.tracer import tracer
from cloud.api.assistant.orchestrator.node import NodeStatus

import asyncio


class FailureNode:
    """
    Central failure management system.
    """

    def __init__(self) -> None:
        self.policy = RetryPolicy()
        self.breaker = CircuitBreaker()
        self.memory = FailureMemory()

    async def handle(self, ctx) -> None:
        failures = []

        for node, result in ctx.node_results.items():
            if result.status.name == "FAILED":
                failures.append((node, result.error))

        for node_name, error in failures:
            print("❌ FAILURE NODE DETECTED ERROR")
            print("Node:", node_name)
            print("Error:", error)

            info = FailureClassifier.classify(error)

            # 🔴 record failure in tracer so /debug/trace sees it
            tracer.record(
                trace_id=ctx.trace_id,
                node="failure",
                status=NodeStatus.FAILED,
                message=str(error),
            )

            # Record failure
            self.memory.store(ctx.device, node_name, error)

            # Block unstable node
            self.breaker.record_failure(node_name)

            # Retry policy (future hook)
            for attempt in range(self.policy.max_retries):
                if not self.policy.should_retry(info, attempt):
                    break
                await asyncio.sleep(self.policy.delay(attempt))

        # 🔴 If we saw any failures, make sure the graph knows this
        if failures:
            raise RuntimeError("Execution failed — failure node triggered")