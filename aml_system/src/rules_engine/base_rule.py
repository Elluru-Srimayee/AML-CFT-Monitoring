"""
Base Rule
=========
Abstract contract every AML detection rule must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

import pandas as pd


@dataclass
class RuleResult:
    """Outcome of applying one rule to the dataset."""
    rule_name: str
    triggered_indices: list[int]        # DataFrame indices that triggered
    score: int                          # Points added to risk score per trigger
    reasons: dict[int, str] = field(default_factory=dict)   # index → human reason

    def __len__(self) -> int:
        return len(self.triggered_indices)

    def __repr__(self) -> str:
        return (
            f"RuleResult(rule={self.rule_name!r}, "
            f"triggered={len(self.triggered_indices)}, score={self.score})"
        )


class BaseRule(ABC):
    """Abstract base class for all AML detection rules."""

    name: str = "BaseRule"
    description: str = ""

    def __init__(self, config: dict):
        """
        Args:
            config: The rule-specific block from config.yaml
                    e.g.  config["rules"]["large_transaction"]
        """
        self.config = config
        self.enabled: bool = config.get("enabled", True)
        self.score: int = int(config.get("score", 0))

    @abstractmethod
    def apply(self, df: pd.DataFrame) -> RuleResult:
        """
        Evaluate the rule against the full (or chunk) DataFrame.

        Args:
            df: Cleaned transaction DataFrame from TransactionLoader.

        Returns:
            RuleResult with triggered row indices and reasons.
        """
        ...

    def _result(
        self,
        triggered_indices: list[int],
        reasons: dict[int, str] | None = None,
    ) -> RuleResult:
        """Convenience factory for sub-classes."""
        return RuleResult(
            rule_name=self.name,
            triggered_indices=triggered_indices,
            score=self.score,
            reasons=reasons or {},
        )
