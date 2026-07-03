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

Notes
-----
This version updates the AI contract from monthly cash expectation
to per-transaction cash expectation.

Primary expected AI output:
- expected_cash_per_transaction_max

The model is asked to estimate what the maximum normal single cash
transaction should be for the customer's declared profile.
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
        Create prompt for the Cash Intensive Business Rule.

        Parameters
        ----------
        customer : dict
            Customer profile.

        transaction_summary : dict
            Aggregated statistics for the customer's observed cash transactions.

        Returns
        -------
        str
            Deterministic prompt text for Azure OpenAI.
        """

        prompt = dedent(
            f"""
            You are a Certified Anti-Money Laundering Investigator.

            Your task is NOT to determine whether money laundering occurred.

            Your task is ONLY to estimate what NORMAL cash transaction behaviour
            should look like for this customer based on their declared occupation,
            income level, risk profile, and location.

            Focus specifically on the expected maximum amount for a SINGLE normal
            cash transaction for this type of customer.

            Do not make an AML decision.
            Do not decide whether the customer is suspicious.
            Do not recommend account action.
            Only estimate expected business cash behaviour.

            -------------------------------
            CUSTOMER PROFILE
            -------------------------------

            Occupation:
            {customer.get("Occupation", "")}

            Annual Income:
            {customer.get("Total Income Per Annum", 0)}

            Address:
            {customer.get("Complete Address", "Unknown")}

            Current Risk Category:
            {customer.get("Risk_Category", "UNKNOWN")}

            Previous AML Flag:
            {customer.get("Is_Flagged", False)}

            -------------------------------
            OBSERVED CASH TRANSACTION SUMMARY
            -------------------------------

            Total Cash Deposits:
            {transaction_summary.get("total_cash_deposit", transaction_summary.get("monthly_cash_deposit", 0))}

            Cash Deposit Count:
            {transaction_summary.get("cash_deposit_count", 0)}

            Average Cash Deposit:
            {transaction_summary.get("average_cash_deposit", 0)}

            Maximum Cash Deposit:
            {transaction_summary.get("maximum_cash_deposit", 0)}

            Sender Countries:
            {transaction_summary.get("sender_locations", "")}

            Receiver Countries:
            {transaction_summary.get("receiver_locations", "")}

            Payment Types:
            {transaction_summary.get("payment_types", "")}

            -------------------------------
            INSTRUCTIONS
            -------------------------------

            Estimate the expected business context for this customer.

            Your output must estimate the maximum normal amount for a SINGLE
            cash transaction for this customer profile.

            Use the observed transaction summary only as supporting context.
            Do not simply repeat the observed maximum cash deposit.
            Use business reasoning based on occupation, income, and geography.

            If the occupation normally involves cash handling, the maximum may be higher.
            If the occupation normally does not involve cash handling, the maximum should be lower.

            Confidence must be between 0.0 and 1.0.

            -------------------------------
            REQUIRED OUTPUT
            -------------------------------

            Return STRICT JSON ONLY.

            DO NOT include markdown.
            DO NOT include explanations outside JSON.
            DO NOT include comments.
            DO NOT include extra keys.

            JSON FORMAT

            {{
                "business_category": "",
                "cash_intensity": "",
                "expected_cash_per_transaction_min": 0,
                "expected_cash_per_transaction_max": 0,
                "expected_avg_cash_transaction": 0,
                "expected_cash_transaction_count_pattern": "",
                "confidence": 0.0,
                "reasoning": ""
            }}
            """
        )

        return prompt.strip()