"""
business_context_agent.py
=========================

Business Context AI Agent

Responsibilities
----------------
1. Summarize customer transactions
2. Check cache
3. Build prompt
4. Call Azure OpenAI
5. Parse response
6. Save cache
7. Return business context

No AML decision logic belongs here.
"""

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

    # ----------------------------------------------------------

    def analyze(
        self,
        customer: dict,
        transactions: pd.DataFrame,
    ) -> dict:
        """
        Returns expected business behaviour.

        Parameters
        ----------
        customer

        transactions

        Returns
        -------
        dict
        """

        summary = self._build_transaction_summary(transactions)

        occupation = customer["Occupation"]

        country = customer["Complete Address"]

        income = float(customer["Total Income Per Annum"])

        cache_key = self.cache.build_cache_key(

            occupation=occupation,

            country=country,

            income=income,
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

    # ----------------------------------------------------------

    @staticmethod
    def _build_transaction_summary(
        df: pd.DataFrame,
    ) -> dict:
        """
        Aggregate transaction statistics.

        This keeps prompts small and fast.
        """

        if df.empty:

            return {

                "monthly_cash_deposit": 0,

                "cash_deposit_count": 0,

                "average_cash_deposit": 0,

                "maximum_cash_deposit": 0,

                "sender_locations": "",

                "receiver_locations": "",

                "payment_types": "",
            }

        cash_df = df.copy()

        #
        # NOTE
        #
        # Replace this condition according to your
        # actual dataset if cash transactions
        # are identified differently.
        #

        cash_df = cash_df[
            cash_df["Payment_type"]
            .astype(str)
            .str.upper()
            .str.contains("CASH", na=False)
        ]

        if cash_df.empty:

            return {

                "monthly_cash_deposit": 0,

                "cash_deposit_count": 0,

                "average_cash_deposit": 0,

                "maximum_cash_deposit": 0,

                "sender_locations": "",

                "receiver_locations": "",

                "payment_types": "",
            }

        return {

            "monthly_cash_deposit":

                float(cash_df["Amount"].sum()),

            "cash_deposit_count":

                int(len(cash_df)),

            "average_cash_deposit":

                float(cash_df["Amount"].mean()),

            "maximum_cash_deposit":

                float(cash_df["Amount"].max()),

            "sender_locations":

                ", ".join(
                    sorted(
                        cash_df["Sender_bank_location"]
                        .astype(str)
                        .unique()
                    )
                ),

            "receiver_locations":

                ", ".join(
                    sorted(
                        cash_df["Receiver_bank_location"]
                        .astype(str)
                        .unique()
                    )
                ),

            "payment_types":

                ", ".join(
                    sorted(
                        cash_df["Payment_type"]
                        .astype(str)
                        .unique()
                    )
                ),
        }