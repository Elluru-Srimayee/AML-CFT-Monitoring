"""
AI Rule : Business Transaction Anomaly
======================================

Detects individual transactions that are inconsistent with
the customer's declared occupation/business.

This rule now evaluates ANY payment type, not only cash deposits.

Workflow
--------
Transaction
      ↓
Customer Profile
      ↓
Business Context Agent
      ↓
Expected Max Amount Per Transaction
      ↓
Transaction-Level Deviation Calculation
      ↓
RuleResult
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from src.rules_engine.base_rule import BaseRule
from src.rules_engine.base_rule import RuleResult

from src.ai.azure_client import AzureAIClient
from src.ai.cache_manager import CacheManager
from src.ai.business_context_agent import BusinessContextAgent


class CashBusinessAIRule(BaseRule):
    """
    AI rule to detect individual transactions that exceed the expected
    amount for the customer's declared business profile and payment type.

    Note:
    The class name is kept as CashBusinessAIRule to avoid breaking existing
    rule-engine configuration. Functionally, it now evaluates all payment types.
    """

    print("Initializing CashBusinessAIRule...")

    name = "CashBusinessAI"

    description = (
        "Individual transactions inconsistent with declared business and payment type."
    )

    def __init__(self, config: dict):
        super().__init__(config)

        self.deviation_multiplier = float(
            config.get("deviation_multiplier", 1.50)
        )

        self.minimum_confidence = float(
            config.get("minimum_confidence", 0.75)
        )

        self.azure = AzureAIClient(
            endpoint=config["azure_endpoint"],
            api_key=config["azure_api_key"],
            deployment=config["deployment_name"],
            api_version=config.get(
                "api_version",
                "2025-01-01-preview",
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
        """
        Apply the rule transaction by transaction.

        Updated behavior:
        - Processes every payment type
        - Does not skip Cross-border, Wire, Card, UPI, Cash, etc.
        - Uses AI context per account + occupation + payment type
        - Flags only the individual transaction that breaches threshold
        """

        if not self.enabled:
            return self._result([], {})

        if df is None or df.empty:
            return self._result([], {})

        self._validate_required_columns(df)

        triggered: List[int] = []
        reasons: Dict[int, str] = {}

        # Account-level transaction context is still useful for AI.
        account_txn_map = {
            self._account_key(account): txns
            for account, txns in df.groupby("Sender_account", dropna=False)
        }

        # Runtime cache to avoid repeated AI calls for the same profile
        # within one execution.
        context_cache: Dict[str, Dict[str, Any]] = {}

        for idx, txn in df.iterrows():

            account = txn.get("Sender_account")
            account_key = self._account_key(account)

            customer = txn.to_dict()
            customer_profile = self._build_customer_profile(customer)

            # Occupation is required for this AI rule.
            # If missing, skip safely instead of failing.
            if not customer_profile.get("Occupation"):
                continue

            customer_payload = dict(customer)
            customer_payload.update(customer_profile)

            profile_key = self._profile_key(
                account=account,
                customer_profile=customer_profile,
                payment_currency=txn.get("Payment_currency"),
                payment_type=txn.get("Payment_type"),
            )

            context = self._get_or_create_context(
                profile_key=profile_key,
                customer_payload=customer_payload,
                account_txns=account_txn_map.get(
                    account_key,
                    pd.DataFrame([txn]),
                ),
                context_cache=context_cache,
            )

            confidence = self._to_float(
                context.get("confidence"),
                default=0.0,
            )

            if confidence < self.minimum_confidence:
                continue

            txn_amount = self._to_float(
                txn.get("Amount"),
                default=0.0,
            )

            # Existing AI contract field.
            # For now, this field is treated as the expected max amount
            # for the current payment type.
            expected_max = self._to_float(
                context.get("expected_cash_per_transaction_max"),
                default=0.0,
            )

            if expected_max <= 0:
                continue

            threshold = expected_max * self.deviation_multiplier

            if txn_amount > threshold:
                triggered.append(idx)

                reasons[idx] = self._build_reason(
                    txn_amount=txn_amount,
                    expected_max=expected_max,
                    threshold=threshold,
                    context=context,
                    payment_type=txn.get("Payment_type"),
                )

        return self._result(
            triggered,
            reasons,
        )

    # --------------------------------------------------------

    def _validate_required_columns(
        self,
        df: pd.DataFrame,
    ) -> None:
        """
        Validate columns required for transaction-level processing.
        """
        required_columns = [
            "Sender_account",
            "Payment_type",
            "Amount",
        ]

        missing_columns = [
            col for col in required_columns
            if col not in df.columns
        ]

        if missing_columns:
            raise ValueError(
                f"{self.name} requires missing columns: "
                f"{', '.join(missing_columns)}"
            )

    # --------------------------------------------------------

    def _build_customer_profile(
        self,
        customer: dict,
    ) -> dict:
        """
        Extract customer profile from the transaction row.
        Supports enriched and raw column naming variants.
        """
        profile = {
            "Occupation": (
                customer.get("Occupation")
                or customer.get("occupation")
                or customer.get("Occupation ")
            ),
            "Complete Address": (
                customer.get("Complete Address")
                or customer.get("complete_address")
                or customer.get("Complete Address ")
                or customer.get("Sender_bank_location")
            ),
            "Total Income Per Annum": (
                customer.get("Total Income Per Annum")
                or customer.get("total_income_per_annum")
                or customer.get("Total Income Per Annum ")
            ),
            "Risk_Category": (
                customer.get("Risk_Category")
                or customer.get("risk_category")
                or customer.get("Risk_Category ")
                or customer.get("risk_tier")
            ),
            "Is_Flagged": (
                customer.get("Is_Flagged")
                or customer.get("is_flagged")
                or customer.get("Is_Flagged ")
            ),
        }

        if not profile.get("Complete Address"):
            profile["Complete Address"] = "Unknown"

        if not profile.get("Total Income Per Annum"):
            profile["Total Income Per Annum"] = 0

        if not profile.get("Risk_Category"):
            profile["Risk_Category"] = "UNKNOWN"

        if profile.get("Is_Flagged") in [None, "", "nan", "NaN"]:
            profile["Is_Flagged"] = False

        return profile

    # --------------------------------------------------------

    def _get_or_create_context(
        self,
        profile_key: str,
        customer_payload: dict,
        account_txns: pd.DataFrame,
        context_cache: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Get AI context for the exact account/profile/payment-type combination.
        """
        if profile_key not in context_cache:
            context_cache[profile_key] = self.agent.analyze(
                customer_payload,
                account_txns,
            )

        return context_cache[profile_key]

    # --------------------------------------------------------

    def _profile_key(
        self,
        account: Any,
        customer_profile: dict,
        payment_currency: Any,
        payment_type: Any,
    ) -> str:
        """
        Build runtime cache key.

        Including payment_type is important because the expected amount for
        a Cash Deposit, Cross-border payment, Wire Transfer, etc. may differ.
        """
        return "|".join(
            [
                str(account).strip().lower(),
                str(customer_profile.get("Occupation", "")).strip().lower(),
                str(customer_profile.get("Complete Address", "")).strip().lower(),
                str(customer_profile.get("Total Income Per Annum", "")).strip().lower(),
                str(customer_profile.get("Risk_Category", "")).strip().lower(),
                str(payment_currency or "").strip().lower(),
                str(payment_type or "").strip().lower(),
            ]
        )

    def _account_key(
        self,
        account: Any,
    ) -> str:
        """
        Convert account identifier into a stable key.
        """
        return str(account).strip()

    def _to_float(
        self,
        value: Any,
        default: float = 0.0,
    ) -> float:
        """
        Safely convert a value to float.
        """
        try:
            if pd.isna(value):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _build_reason(
        self,
        txn_amount: float,
        expected_max: float,
        threshold: float,
        context: Dict[str, Any],
        payment_type: Any,
    ) -> str:
        """
        Build explanation for a flagged transaction.
        """
        business_category = context.get(
            "business_category",
            "UNKNOWN",
        )

        reasoning = context.get(
            "reasoning",
            "No reasoning provided.",
        )

        return (
            f"Individual transaction amount {txn_amount:,.2f} "
            f"for payment type '{payment_type}' exceeds allowed threshold "
            f"{threshold:,.2f} "
            f"(expected max {expected_max:,.2f} x deviation multiplier "
            f"{self.deviation_multiplier:.2f}). "
            f"Business Category: {business_category}. "
            f"Reason: {reasoning}"
        )