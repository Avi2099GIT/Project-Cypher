class RecoveryPlanner:
    """
    Rewrites plans in case of failure.
    """

    @staticmethod
    def repair(plan: list, failed_tool: str) -> list:
        """
        Drop failed tool & allow system to recover gracefully.
        """
        return [step for step in plan if step.get("tool") != failed_tool]
