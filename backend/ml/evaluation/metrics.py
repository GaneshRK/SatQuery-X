"""Task-agnostic evaluation metrics used by SatQuery-X evaluators."""
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable


def normalize_answer(text: str) -> str:
    text = str(text).lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def token_f1(prediction: str, reference: str) -> float:
    pred = normalize_answer(prediction).split()
    gold = normalize_answer(reference).split()
    if not pred or not gold:
        return float(pred == gold)
    common = sum((Counter(pred) & Counter(gold)).values())
    if common == 0:
        return 0.0
    precision = common / len(pred)
    recall = common / len(gold)
    return 2 * precision * recall / (precision + recall)


def mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None
