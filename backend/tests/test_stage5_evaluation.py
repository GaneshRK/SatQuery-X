"""Stage 5 tests: evaluation must be data-driven and must refuse placeholders."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml.evaluation.evaluate_benchmarks import run_benchmark_eval
from ml.evaluation.metrics import normalize_answer, token_f1


def test_metrics_are_real_functions():
    assert normalize_answer("Yes!") == "yes"
    assert token_f1("red building", "red building") == 1.0
    assert token_f1("red", "blue") == 0.0


def test_missing_manifest_is_rejected(tmp_path: Path):
    ckpt = tmp_path / "checkpoint"
    ckpt.mkdir()
    with pytest.raises(ValueError):
        run_benchmark_eval("RS_VQA", str(ckpt), "RSVQA", manifest=None)


def test_missing_checkpoint_is_rejected(tmp_path: Path):
    manifest = tmp_path / "test.jsonl"
    manifest.write_text(json.dumps({"image": "x", "question": "q", "answer": "a"}) + "\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        run_benchmark_eval("RS_VQA", str(tmp_path / "missing"), "RSVQA", manifest=str(manifest))


def test_unsupported_benchmark_is_rejected(tmp_path: Path):
    ckpt = tmp_path / "checkpoint"; ckpt.mkdir()
    manifest = tmp_path / "test.jsonl"; manifest.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        run_benchmark_eval("RS_CAPTION", str(ckpt), "some-benchmark", manifest=str(manifest))
