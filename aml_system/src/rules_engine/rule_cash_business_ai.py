"""
AI Rule : Cash Intensive Business Anomaly
=========================================

Detects customers whose cash deposits are inconsistent with
their declared occupation/business.

Unlike traditional rules, the expected cash behaviour is
determined dynamically using Azure OpenAI.

Workflow
--------
Customer
      ↓
Transaction Summary
      ↓
Business Context Agent
      ↓
Expected Cash Behaviour
      ↓
Deviation Calculation
      ↓
RuleResult
"""

from __future__ import annotations

import pandas as pd

from src.rules_engine.base_rule import BaseRule
from src.rules_engine.base_rule import RuleResult

from src.ai.azure_client import AzureAIClient
from src.ai.cache_manager import CacheManager
from src.ai.business_context_agent import BusinessContextAgent


class CashBusinessAIRule(BaseRule):

    name = "CashBusinessAI"

    description = (
        "Cash deposits inconsistent with declared business."
    )

    def __init__(self, config: dict):

        super().__init__(config)

        self.deviation_multiplier = float(
            config.get("deviation_multiplier", 1.50)
        )

        self.minimum_confidence = float(
            config.get("minimum_confidence", 0.75)
        )

        # Azure Client

        self.azure = AzureAIClient(

            endpoint=config["azure_endpoint"],

            api_key=config["azure_api_key"],

            deployment=config["deployment_name"],

            api_version=config.get(
                "api_version",
                "2024-02-15-preview",
            ),
        )

        self.cache = CacheManager()

        self.agent = BusinessContextAgent(

            self.azure,

            self.cache,
        )

    # --------------------------------------------------------

    def apply(
        self,
        df: pd.DataFrame,
    ) -> RuleResult:

        if not self.enabled:

            return self._result([], {})

        triggered = []

        reasons = {}

        #
        # Group customer transactions
        #

        grouped = df.groupby("Sender_account")

        for account, txns in grouped:

            #
            # Customer profile
            #

            customer = txns.iloc[0]

            #
            # Skip if customer information
            # is unavailable
            #

            if pd.isna(customer.get("Occupation")):

                continue

            #
            # AI Agent
            #

            context = self.agent.analyze(

                customer.to_dict(),

                txns,
            )

            #
            # Ignore uncertain responses
            #

            if (

                context["confidence"]

                <

                self.minimum_confidence

            ):

                continue

            #
            # Actual cash deposits
            #

            cash_txns = txns[

                txns["Payment_type"]

                .astype(str)

                .str.upper()

                .str.contains("CASH", na=False)

            ]

            if cash_txns.empty:

                continue

            observed_cash = float(

                cash_txns["Amount"].sum()

            )

            expected_max = float(

                context["expected_monthly_cash_max"]

            )

            #
            # Compare
            #

            if observed_cash > (

                expected_max

                *

                self.deviation_multiplier

            ):

                for idx in cash_txns.index:

                    triggered.append(idx)

                    reasons[idx] = (

                        f"Observed cash deposits "

                        f"{observed_cash:,.2f} "

                        f"exceed expected "

                        f"maximum "

                        f"{expected_max:,.2f}. "

                        f"Business Category: "

                        f"{context['business_category']}. "

                        f"Reason: "

                        f"{context['reasoning']}"

                    )

        return self._result(

            triggered,

            reasons,
        )