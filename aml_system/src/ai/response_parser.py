"""
response_parser.py
==================

Parses and validates Azure OpenAI JSON responses.

Responsibilities
----------------
* Validate mandatory fields
* Validate numeric values
* Apply defaults where appropriate
* Return a strongly typed, normalized dictionary

Notes
-----
This version migrates the response contract from monthly cash
expectation to per-transaction cash expectation.

Preferred output schema:
- expected_cash_per_transaction_min
- expected_cash_per_transaction_max
- expected_avg_cash_transaction
- expected_cash_transaction_count_pattern

Backward compatibility:
- Legacy monthly fields are still accepted as input
- Output is always normalized to the new per-transaction schema
"""

from __future__ import annotations

from typing import Any, Dict, Set


class ResponseParser:
    """
    Validates and normalizes Business Context Agent responses.
    """

    NEW_REQUIRED_FIELDS: Set[str] = {
        "business_category",
        "cash_intensity",
        "expected_cash_per_transaction_min",
        "expected_cash_per_transaction_max",
        "expected_avg_cash_transaction",
        "expected_cash_transaction_count_pattern",
        "confidence",
        "reasoning",
    }

    LEGACY_REQUIRED_FIELDS: Set[str] = {
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
        Validate and normalize Azure response.

        Supported input formats
        -----------------------
        1. New schema
        2. Legacy monthly schema

        Returns
        -------
        dict
            Normalized output using the new field names.

        Raises
        ------
        ValueError
            If response is invalid or required fields are missing.
        """
        if not isinstance(response, dict):
            raise ValueError("Azure response must be a dictionary.")

        if cls._is_new_schema(response):
            parsed = cls._parse_new_schema(response)
        elif cls._is_legacy_schema(response):
            parsed = cls._parse_legacy_schema(response)
        else:
            cls._raise_missing_fields_error(response)

        cls._validate_ranges(parsed)

        return parsed

    # ---------------------------------------------------------

    @classmethod
    def _is_new_schema(cls, response: Dict[str, Any]) -> bool:
        """
        Check whether the response matches the new schema.
        """
        return cls.NEW_REQUIRED_FIELDS.issubset(response.keys())

    # ---------------------------------------------------------

    @classmethod
    def _is_legacy_schema(cls, response: Dict[str, Any]) -> bool:
        """
        Check whether the response matches the legacy schema.
        """
        return cls.LEGACY_REQUIRED_FIELDS.issubset(response.keys())

    # ---------------------------------------------------------

    @classmethod
    def _parse_new_schema(cls, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse the preferred per-transaction schema.
        """
        parsed = {
            "business_category": cls._to_clean_string(
                response.get("business_category")
            ),
            "cash_intensity": cls._to_clean_string(
                response.get("cash_intensity")
            ),
            "expected_cash_per_transaction_min": cls._to_float(
                response.get("expected_cash_per_transaction_min")
            ),
            "expected_cash_per_transaction_max": cls._to_float(
                response.get("expected_cash_per_transaction_max")
            ),
            "expected_avg_cash_transaction": cls._to_float(
                response.get("expected_avg_cash_transaction")
            ),
            "expected_cash_transaction_count_pattern": cls._to_clean_string(
                response.get("expected_cash_transaction_count_pattern")
            ),
            "confidence": cls._validate_confidence(
                response.get("confidence")
            ),
            "reasoning": cls._to_clean_string(
                response.get("reasoning")
            ),
        }

        return parsed

    # ---------------------------------------------------------

    @classmethod
    def _parse_legacy_schema(cls, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse the old monthly schema and normalize it to the new schema.

        Important:
        - Monthly values are mapped into the new structure for compatibility.
        - This is only a transition mechanism.
        - PromptBuilder should be updated so the model eventually returns
          the new per-transaction schema directly.
        """
        monthly_count = cls._to_int(response.get("expected_monthly_transaction_count"))

        parsed = {
            "business_category": cls._to_clean_string(
                response.get("business_category")
            ),
            "cash_intensity": cls._to_clean_string(
                response.get("cash_intensity")
            ),
            "expected_cash_per_transaction_min": cls._to_float(
                response.get("expected_monthly_cash_min")
            ),
            "expected_cash_per_transaction_max": cls._to_float(
                response.get("expected_monthly_cash_max")
            ),
            "expected_avg_cash_transaction": cls._to_float(
                response.get("expected_avg_transaction")
            ),
            "expected_cash_transaction_count_pattern": str(monthly_count),
            "confidence": cls._validate_confidence(
                response.get("confidence")
            ),
            "reasoning": cls._to_clean_string(
                response.get("reasoning")
            ),
        }

        return parsed

    # ---------------------------------------------------------

    @classmethod
    def _raise_missing_fields_error(cls, response: Dict[str, Any]) -> None:
        """
        Raise a clear validation error when neither supported schema matches.
        """
        missing_new = sorted(cls.NEW_REQUIRED_FIELDS - response.keys())
        missing_legacy = sorted(cls.LEGACY_REQUIRED_FIELDS - response.keys())

        raise ValueError(
            "Azure response does not match a supported schema. "
            f"Missing new-schema fields: {missing_new}. "
            f"Missing legacy-schema fields: {missing_legacy}."
        )

    # ---------------------------------------------------------

    @staticmethod
    def _to_clean_string(value: Any) -> str:
        """
        Convert a value to a clean string.
        """
        if value is None:
            return ""
        return str(value).strip()

    # ---------------------------------------------------------

    @staticmethod
    def _to_float(value: Any) -> float:
        """
        Convert value to float and reject invalid values.
        """
        try:
            return float(value)
        except Exception as exc:
            raise ValueError(
                f"Expected numeric value but received {value}"
            ) from exc

    # ---------------------------------------------------------

    @staticmethod
    def _to_int(value: Any) -> int:
        """
        Convert value to integer and reject invalid values.
        """
        try:
            return int(value)
        except Exception as exc:
            raise ValueError(
                f"Expected integer value but received {value}"
            ) from exc

    # ---------------------------------------------------------

    @staticmethod
    def _validate_confidence(value: Any) -> float:
        """
        Clamp confidence into the valid range [0.0, 1.0].
        """
        try:
            confidence = float(value)
        except Exception as exc:
            raise ValueError(
                f"Expected confidence to be numeric but received {value}"
            ) from exc

        if confidence < 0:
            confidence = 0.0

        if confidence > 1:
            confidence = 1.0

        return confidence

    # ---------------------------------------------------------

    @staticmethod
    def _validate_ranges(data: Dict[str, Any]) -> None:
        """
        Validate logical numeric ranges in the normalized output.
        """
        if (
            data["expected_cash_per_transaction_min"]
            >
            data["expected_cash_per_transaction_max"]
        ):
            raise ValueError(
                "Per-transaction cash minimum exceeds maximum."
            )

        if data["expected_avg_cash_transaction"] < 0:
            raise ValueError(
                "Expected average cash transaction cannot be negative."
            )

        if data["expected_cash_per_transaction_min"] < 0:
            raise ValueError(
                "Expected per-transaction cash minimum cannot be negative."
            )

        if data["expected_cash_per_transaction_max"] < 0:
            raise ValueError(
                "Expected per-transaction cash maximum cannot be negative."
            )