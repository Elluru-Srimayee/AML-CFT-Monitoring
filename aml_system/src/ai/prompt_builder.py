"""
prompt_builder.py
=================

Builds prompts for Azure OpenAI.

Responsibilities
----------------
* Accept customer profile
* Accept aggregated transaction statistics
* Build deterministic prompt
* Minimize token usage
"""

from __future__ import annotations

from textwrap import dedent


class PromptBuilder:
    """
    Builds prompts for the Business Context AI Agent.
    """

    @staticmethod
    def build_cash_business_prompt(
        customer: dict,
        transaction_summary: dict,
    ) -> str:
        """
        Create prompt for Cash Intensive Business Rule.

        Parameters
        ----------
        customer : dict
            Customer profile

        transaction_summary : dict
            Aggregated transaction statistics

        Returns
        -------
        str
        """

        prompt = dedent(
            f"""
            You are a Certified Anti-Money Laundering (AML) Investigator.

            Your task is NOT to determine whether money laundering occurred.

            Your task is ONLY to estimate what NORMAL cash transaction behaviour
            should look like for this customer based on their declared occupation,
            income level and location.

            -------------------------------
            CUSTOMER PROFILE
            -------------------------------

            Occupation:
            {customer["Occupation"]}

            Annual Income:
            {customer["Total Income Per Annum"]}

            Address:
            {customer["Complete Address"]}

            Current Risk Category:
            {customer["Risk_Category"]}

            Previous AML Flag:
            {customer["Is_Flagged"]}

            -------------------------------
            OBSERVED TRANSACTION SUMMARY
            -------------------------------

            Monthly Cash Deposits:
            {transaction_summary["monthly_cash_deposit"]}

            Cash Deposit Count:
            {transaction_summary["cash_deposit_count"]}

            Average Cash Deposit:
            {transaction_summary["average_cash_deposit"]}

            Maximum Cash Deposit:
            {transaction_summary["maximum_cash_deposit"]}

            Sender Countries:
            {transaction_summary["sender_locations"]}

            Receiver Countries:
            {transaction_summary["receiver_locations"]}

            Payment Types:
            {transaction_summary["payment_types"]}

            -------------------------------
            REQUIRED OUTPUT
            -------------------------------

            Return STRICT JSON ONLY.

            DO NOT include markdown.

            DO NOT include explanations outside JSON.

            JSON FORMAT

            {{

                "business_category": "",

                "cash_intensity": "",

                "expected_monthly_cash_min": 0,

                "expected_monthly_cash_max": 0,

                "expected_avg_transaction": 0,

                "expected_monthly_transaction_count": 0,

                "confidence": 0.0,

                "reasoning": ""

            }}
            """
        )

        return prompt.strip()