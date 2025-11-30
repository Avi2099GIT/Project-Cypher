class MemoryAgent:
    """
    Wraps memory service.
    """

    def read(self, memory_service):
        return memory_service.debug_dump()

    def write(self, memory_service, text: str):
        memory_service.add_fact({"text": text})
        return {"stored": True}
