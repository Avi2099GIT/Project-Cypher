from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum


class PlanRisk(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class PlanStep:
    tool: str
    args: Dict[str, Any]
    expected: Optional[str] = None


@dataclass
class ExecutionPlan:
    """
    Planner v2 output structure.
    """
    steps: List[PlanStep]
    reason: str
    risk: PlanRisk
    estimated_cost: float = 1.0
    confidence: float = 0.5
    fallbacks: List["ExecutionPlan"] = field(default_factory=list)
    explanation: Dict[str, Any] = field(default_factory=dict)
    rejected: List[Dict[str, Any]] = field(default_factory=list)
    score_breakdown: Dict[str, Any] = field(default_factory=dict)
