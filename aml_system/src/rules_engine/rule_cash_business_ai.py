"""
AI Rule : Business Transaction Anomaly
======================================

Detects individual transactions inconsistent with the customer's
declared occupation/business.

This version:
- evaluates all payment types
- parallelizes AI context fetches
"""

from __future__ import annotations

from typing import Any, Dict, List
from pathlib import Path

from src.utils.helpers import load_config

import pandas as pd

from src.rules_engine.base_rule import BaseRule
from src.rules_engine.base_rule import RuleResult

from src.ai.azure_client import AzureAIClient
from src.ai.cache_manager import CacheManager
from src.ai.business_context_agent import BusinessContextAgent
from src.rules_engine.parallel_mixin import ParallelExecutionMixin


class CashBusinessAIRule(ParallelExecutionMixin, BaseRule):
    print("Initializing CashBusinessAIRule...")

    name = "CashBusinessAI"

    description = (
        "Individual transactions inconsistent with declared business."
    )

    def __init__(self, config: dict):
        super().__init__(config)

        self.deviation_multiplier = float(
            config.get("deviation_multiplier", 1.50)
        )

        self.minimum_confidence = float(
            config.get("minimum_confidence", 0.75)
        )

        self.max_parallel_workers = int(
            config.get("max_parallel_workers", 8)
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

        # Load customer master for sender/receiver lookups (optional)
        try:
            cfg = load_config()
            project_root = Path(__file__).resolve().parents[2]
            cust_path = cfg.get("investigation", {}).get("customer_details_file")
            if cust_path:
                cust_file = project_root / cust_path
                if cust_file.exists():
                    cust_df = pd.read_csv(cust_file)
                    cust_df.columns = cust_df.columns.str.strip()
                    # build quick lookup map by Account Number (stringified)
                    self._customer_map: Dict[str, Dict[str, Any]] = {
                        str(row.get("Account Number")).strip(): {
                            k: (v if pd.notna(v) else None)
                            for k, v in row.items()
                        }
                        for _, row in cust_df.fillna("").iterrows()
                    }
                else:
                    self._customer_map = {}
            else:
                self._customer_map = {}
        except Exception:
            # Non-fatal: agent will still operate using transaction-level profile
            self._customer_map = {}

    # --------------------------------------------------------

    def apply(
        self,
        df: pd.DataFrame,
    ) -> RuleResult:
        """
        Apply the rule transaction-by-transaction.

        AI calls are parallelized across unique profile/payment combinations.
        """

        if not self.enabled:
            return self._result([], {})

        if df is None or df.empty:
            return self._result([], {})

        self._validate_required_columns(df)

        candidate_rows: List[Dict[str, Any]] = []
        unique_requests: Dict[str, Dict[str, Any]] = {}

        account_txn_map = {
            self._account_key(account): txns
            for account, txns in df.groupby("Sender_account", dropna=False)
        }

        # ----------------------------------------------------
        # Build unique AI requests
        # ----------------------------------------------------

        for idx, txn in df.iterrows():
            customer = txn.to_dict()
            customer_profile = self._build_customer_profile(customer)

            # Enrich from master customer file when available
            sender_master = None
            receiver_master = None
            try:
                if getattr(self, "_customer_map", None):
                    sender_master = self._customer_map.get(str(txn.get("Sender_account") or "").strip())
                    receiver_master = self._customer_map.get(str(txn.get("Receiver_account") or "").strip())
            except Exception:
                sender_master = None
                receiver_master = None

            # prefer master values for sender profile
            if sender_master:
                for k in [
                    "Occupation",
                    "Complete Address",
                    "Total Income Per Annum",
                    "Risk_Category",
                    "Is_Flagged",
                ]:
                    if sender_master.get(k):
                        customer_profile[k] = sender_master.get(k)

            if not customer_profile.get("Occupation"):
                continue

            account = txn.get("Sender_account")
            account_key = self._account_key(account)

            customer_payload = dict(customer)
            customer_payload.update(customer_profile)

            # attach receiver/master as Counterparty_* keys so agent can see counterparty info
            if receiver_master:
                for rk, rv in receiver_master.items():
                    if rk and isinstance(rk, str):
                        customer_payload[f"Counterparty_{rk}"] = rv

            profile_key = self._profile_key(
                account=account,
                counterparty_account=txn.get("Receiver_account"),
                customer_profile=customer_profile,
                payment_currency=txn.get("Payment_currency"),
                payment_type=txn.get("Payment_type"),
            )

            candidate_rows.append(
                {
                    "idx": idx,
                    "txn": txn,
                    "profile_key": profile_key,
                }
            )

            if profile_key not in unique_requests:
                unique_requests[profile_key] = {
                    "customer_payload": customer_payload,
                    "account_txns": account_txn_map.get(
                        account_key,
                        pd.DataFrame([txn]),
                    ),
                }

        # ----------------------------------------------------
        # Fetch AI contexts in parallel
        # ----------------------------------------------------

        context_map = self.run_parallel_tasks(
            task_map=unique_requests,
            worker_fn=self._analyze_profile_request,
            max_workers=self.max_parallel_workers,
        )

        # ----------------------------------------------------
        # Evaluate transactions
        # ----------------------------------------------------

        triggered: List[int] = []
        reasons: Dict[int, str] = {}

        for item in candidate_rows:
            idx = item["idx"]
            txn = item["txn"]
            profile_key = item["profile_key"]

            context = context_map.get(profile_key, {})

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

            expected_max = self._get_expected_max(context)

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

        return self._result(triggered, reasons)

    # --------------------------------------------------------

    def _analyze_profile_request(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Worker function used by parallel executor.
        """
        return self.agent.analyze(
            payload["customer_payload"],
            payload["account_txns"],
        )

    # --------------------------------------------------------

    def _validate_required_columns(
        self,
        df: pd.DataFrame,
    ) -> None:
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

    def _build_customer_profile(
        self,
        customer: dict,
    ) -> dict:
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

    def _profile_key(
        self,
        account: Any,
        counterparty_account: Any,
        customer_profile: dict,
        payment_currency: Any,
        payment_type: Any,
    ) -> str:
        """
        Unique runtime key for one AI business context request.
        """
        return "|".join(
            [
                str(account).strip().lower(),
                str(counterparty_account or "").strip().lower(),
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
        return str(account).strip()

    def _to_float(
        self,
        value: Any,
        default: float = 0.0,
    ) -> float:
        try:
            if pd.isna(value):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _get_expected_max(
        self,
        context: Dict[str, Any],
    ) -> float:
        """
        Support both old and new response contracts.
        """
        if "expected_transaction_amount_max" in context:
            return self._to_float(
                context.get("expected_transaction_amount_max"),
                default=0.0,
            )

        return self._to_float(
            context.get("expected_cash_per_transaction_max"),
            default=0.0,
        )

    def _build_reason(
        self,
        txn_amount: float,
        expected_max: float,
        threshold: float,
        context: Dict[str, Any],
        payment_type: Any,
    ) -> str:
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