"""
parallel_mixin.py
=================

Reusable parallel execution helper for AI-backed rules.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Iterable


class ParallelExecutionMixin:
    """
    Reusable helper for parallel task execution.

    Best for network-bound work such as AI API calls.
    """

    def run_parallel_tasks(
        self,
        task_map: Dict[str, Any],
        worker_fn: Callable[[Any], Any],
        max_workers: int = 8,
    ) -> Dict[str, Any]:
        """
        Execute tasks in parallel and return results by task key.

        Parameters
        ----------
        task_map : dict
            Mapping of unique task key -> task payload
        worker_fn : callable
            Function that accepts one task payload and returns a result
        max_workers : int
            Maximum thread count

        Returns
        -------
        dict
            Mapping of task key -> result
        """
        if not task_map:
            return {}

        results: Dict[str, Any] = {}

        worker_count = min(max_workers, len(task_map))

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(worker_fn, payload): key
                for key, payload in task_map.items()
            }

            for future in as_completed(future_map):
                key = future_map[future]

                try:
                    results[key] = future.result()
                except Exception as exc:
                    results[key] = {
                        "confidence": 0.0,
                        "business_category": "UNKNOWN",
                        "reasoning": f"Parallel execution failed: {exc}",
                    }

        return results