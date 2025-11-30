class NarratorAgent:
    """
    Final response generator.
    """

    def narrate(self, tool_results):
        if not tool_results:
            return "Done."

        parts = []
        for result in tool_results:
            parts.append(f"{result['tool']}: {result['result']}")

        return "\n".join(parts)
