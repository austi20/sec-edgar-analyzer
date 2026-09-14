"""Local-LLM narrative layer (Ollama), grounded in computed numbers only.

The model never invents a figure. It narrates values the deterministic pipeline
already produced, and every number in its output is verified against the input
table before the summary is cached.
"""

from __future__ import annotations

import re
from pathlib import Path

SUMMARY_DIR = Path(__file__).resolve().parents[1] / "data" / "summaries"
MODEL = "llama3.2:3b"
OLLAMA_URL = "http://localhost:11434/api/generate"

PROMPT = """You are summarizing a company's financial ratios for an analyst.

Use ONLY the figures in the table below. If a figure is not in the table, write
"not available". Do not estimate, round beyond what is shown, or introduce any
number that does not appear here.

{table}

Write 120 words covering: the trend over the period, how the company stands
against its peer set, and the single biggest risk visible in these numbers.
"""


def generate_summary(table_text: str, model: str = MODEL) -> str:
    raise NotImplementedError


def extract_numbers(text: str) -> list[str]:
    return re.findall(r"-?\d[\d,]*\.?\d*", text)


def verify_numbers(summary: str, table_text: str) -> bool:
    """Assert every number in the summary appears in the input table."""
    raise NotImplementedError


def cached_summary(ticker: str, table_text: str) -> str:
    """Cache to data/summaries/ keyed by a hash of the input.

    The deployed app reads these, so it never needs Ollama or a GPU at runtime.
    """
    raise NotImplementedError
