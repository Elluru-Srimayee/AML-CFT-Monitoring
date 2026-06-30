"""
azure_client.py
================

Azure OpenAI client wrapper.

Responsibilities
----------------
* Creates Azure OpenAI client
* Sends prompt
* Returns raw JSON response
* Handles retries
* Handles API errors

No AML logic belongs here.
"""

from __future__ import annotations

import json
import time
from typing import Optional

from openai import AzureOpenAI


class AzureAIClient:
    """
    Thin wrapper around Azure OpenAI.

    Example
    -------
    client = AzureAIClient(
        endpoint=...,
        api_key=...,
        deployment=...
    )

    response = client.generate(prompt)
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str = "2024-02-15-preview",
        temperature: float = 0.0,
        max_tokens: int = 800,
        timeout: int = 60,
        max_retries: int = 3,
    ):

        self.deployment = deployment
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries

        self.client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            timeout=timeout,
        )

    # --------------------------------------------------------
    # Public
    # --------------------------------------------------------

    def generate(self, prompt: str) -> dict:
        """
        Send prompt to Azure OpenAI.

        Returns
        -------
        dict
            Parsed JSON response from model.

        Raises
        ------
        RuntimeError
            If all retries fail.
        """

        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):

            try:

                response = self.client.chat.completions.create(

                    model=self.deployment,

                    temperature=self.temperature,

                    max_tokens=self.max_tokens,

                    response_format={"type": "json_object"},

                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a senior Anti-Money Laundering investigator. "
                                "Always return valid JSON."
                            ),
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                )

                content = response.choices[0].message.content

                return json.loads(content)

            except Exception as ex:

                last_error = ex

                if attempt < self.max_retries:
                    time.sleep(2 * attempt)
                    continue

        raise RuntimeError(
            f"Azure OpenAI request failed after "
            f"{self.max_retries} retries."
        ) from last_error