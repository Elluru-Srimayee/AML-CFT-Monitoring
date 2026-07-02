from __future__ import annotations

import pandas as pd

from src.ai.azure_client import AzureAIClient
from src.ai.cache_manager import CacheManager
from src.ai.prompt_builder import PromptBuilder
from src.ai.response_parser import ResponseParser


class BusinessContextAgent:

    def __init__(
        self,
        azure_client: AzureAIClient,
        cache_manager: CacheManager,
    ):
        self.azure = azure_client
        self.cache = cache_manager

    def analyze(
        self,
        customer: dict,
        transactions: pd.DataFrame,
    ) -> dict:
        """
        Returns expected business behaviour for the current transaction profile.

        Now includes payment type in the cache key so Cash Deposit and Cross-border
        transactions do not reuse the same AI context incorrectly.
        """

        summary = self._build_transaction_summary(transactions)

        occupation = customer.get("Occupation", "")
        country = customer.get("Complete Address", "Unknown")

        try:
            income = float(customer.get("Total Income Per Annum", 0) or 0)
        except (TypeError, ValueError):
            income = 0.0

        sender_account = str(customer.get("Sender_account", "")).strip()
        risk_category = str(customer.get("Risk_Category", "UNKNOWN")).strip()
        currency = str(customer.get("Payment_currency", "")).strip()
        payment_type = str(customer.get("Payment_type", "")).strip()

        cache_key = self.cache.build_cache_key(
            occupation=occupation,
            country=country,
            income=income,
            sender_account=sender_account,
            risk_category=risk_category,
            currency=currency,
            payment_type=payment_type,
        )

        cached = self.cache.get(cache_key)

        if cached is not None:
            return cached

        prompt = PromptBuilder.build_cash_business_prompt(
            customer,
            summary,
        )

        response = self.azure.generate(prompt)

        context = ResponseParser.parse(response)

        self.cache.save(
            cache_key=cache_key,
            occupation=occupation,
            country=country,
            income_band=self.cache.income_band(income),
            response=context,
        )

        return context


    @staticmethod
    def _build_transaction_summary(
        df: pd.DataFrame,
    ) -> dict:
        """
        Aggregate transaction statistics for all payment types.

        This no longer filters only CASH transactions.
        """

        default_summary = {
            "total_transaction_amount": 0.0,
            "transaction_count": 0,
            "average_transaction_amount": 0.0,
            "maximum_transaction_amount": 0.0,

            # Legacy keys kept so existing PromptBuilder does not break.
            "monthly_cash_deposit": 0.0,
            "total_cash_deposit": 0.0,
            "cash_deposit_count": 0,
            "average_cash_deposit": 0.0,
            "maximum_cash_deposit": 0.0,

            "sender_locations": "",
            "receiver_locations": "",
            "payment_types": "",
            "payment_currencies": "",
            "received_currencies": "",
        }

        if df is None or df.empty:
            return default_summary

        txn_df = df.copy()

        if "Amount" not in txn_df.columns:
            return default_summary

        txn_df["Amount"] = pd.to_numeric(
            txn_df["Amount"],
            errors="coerce",
        ).fillna(0.0)

        transaction_count = int(len(txn_df))
        total_amount = float(txn_df["Amount"].sum())
        average_amount = float(txn_df["Amount"].mean()) if transaction_count > 0 else 0.0
        maximum_amount = float(txn_df["Amount"].max()) if transaction_count > 0 else 0.0

        return {
            "total_transaction_amount": total_amount,
            "transaction_count": transaction_count,
            "average_transaction_amount": average_amount,
            "maximum_transaction_amount": maximum_amount,

            # Legacy aliases.
            # These are no longer cash-only; they are retained only to avoid
            # breaking the existing prompt/parser contract immediately.
            "monthly_cash_deposit": total_amount,
            "total_cash_deposit": total_amount,
            "cash_deposit_count": transaction_count,
            "average_cash_deposit": average_amount,
            "maximum_cash_deposit": maximum_amount,

            "sender_locations": ", ".join(
                sorted(txn_df["Sender_bank_location"].astype(str).unique())
            ) if "Sender_bank_location" in txn_df.columns else "",

            "receiver_locations": ", ".join(
                sorted(txn_df["Receiver_bank_location"].astype(str).unique())
            ) if "Receiver_bank_location" in txn_df.columns else "",

            "payment_types": ", ".join(
                sorted(txn_df["Payment_type"].astype(str).unique())
            ) if "Payment_type" in txn_df.columns else "",

            "payment_currencies": ", ".join(
                sorted(txn_df["Payment_currency"].astype(str).unique())
            ) if "Payment_currency" in txn_df.columns else "",

            "received_currencies": ", ".join(
                sorted(txn_df["Received_currency"].astype(str).unique())
            ) if "Received_currency" in txn_df.columns else "",
        }