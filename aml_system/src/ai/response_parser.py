"""
response_parser.py
==================

Parses and validates Azure OpenAI JSON responses.

Responsibilities
----------------
* Validate mandatory fields
* Validate numeric values
* Apply defaults
* Return a strongly typed dictionary

This module ensures downstream AML rules always receive
clean, predictable data regardless of LLM output quality.
"""

from __future__ import annotations

from typing import Any, Dict


class ResponseParser:
    """
    Validates Business Context Agent responses.
    """

    REQUIRED_FIELDS = {

        "business_category",

        "cash_intensity",

        "expected_monthly_cash_min",

        "expected_monthly_cash_max",

        "expected_avg_transaction",

        "expected_monthly_transaction_count",

        "confidence",

        "reasoning",

    }

    # ---------------------------------------------------------

    @classmethod
    def parse(cls, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate Azure response.

        Parameters
        ----------
        response

        Returns
        -------
        dict

        Raises
        ------
        ValueError
        """

        cls._validate_required_fields(response)

        parsed = {

            "business_category":
                str(response["business_category"]).strip(),

            "cash_intensity":
                str(response["cash_intensity"]).strip(),

            "expected_monthly_cash_min":
                cls._to_float(
                    response["expected_monthly_cash_min"]
                ),

            "expected_monthly_cash_max":
                cls._to_float(
                    response["expected_monthly_cash_max"]
                ),

            "expected_avg_transaction":
                cls._to_float(
                    response["expected_avg_transaction"]
                ),

            "expected_monthly_transaction_count":
                int(
                    response["expected_monthly_transaction_count"]
                ),

            "confidence":
                cls._validate_confidence(
                    response["confidence"]
                ),

            "reasoning":
                str(response["reasoning"]).strip(),
        }

        cls._validate_ranges(parsed)

        return parsed

    # ---------------------------------------------------------

    @classmethod
    def _validate_required_fields(cls, response):

        missing = cls.REQUIRED_FIELDS - response.keys()

        if missing:

            raise ValueError(

                f"Missing fields from Azure response: {missing}"

            )

    # ---------------------------------------------------------

    @staticmethod
    def _to_float(value):

        try:

            return float(value)

        except Exception:

            raise ValueError(

                f"Expected numeric value but received {value}"

            )

    # ---------------------------------------------------------

    @staticmethod
    def _validate_confidence(value):

        value = float(value)

        if value < 0:

            value = 0.0

        if value > 1:

            value = 1.0

        return value

    # ---------------------------------------------------------

    @staticmethod
    def _validate_ranges(data):

        if (

            data["expected_monthly_cash_min"]

            >

            data["expected_monthly_cash_max"]

        ):

            raise ValueError(

                "Monthly cash minimum exceeds maximum."

            )

        if data["expected_avg_transaction"] < 0:

            raise ValueError(

                "Average transaction cannot be negative."

            )

        if data["expected_monthly_transaction_count"] < 0:

            raise ValueError(

                "Transaction count cannot be negative."

            )