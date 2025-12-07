from cloud.api.assistant.memory import memory_service


class FailureMemory:
    """
    Records failures into episodic memory.
    """

    @staticmethod
    def store(device, tool: str, error: str) -> None:
        memory_service.store_episode(
            device=device,
            role="system",
            content=f"Tool failure: {tool}",
            meta={"error": error},
        )
