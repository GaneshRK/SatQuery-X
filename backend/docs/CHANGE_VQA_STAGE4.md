# Stage 4 — Real Bi-temporal Change VQA

## Runtime

`ChangeVQAModel` first checks `CHANGE_VQA_CHECKPOINT`. If configured, it runs the actual supervised checkpoint over the supplied T1/T2 pair and question. If unavailable, it falls back to the existing grounded evidence reasoner.

## Training contract

Each record contains:
- `image_t1`: before image
- `image_t2`: after image
- `question`: real change question
- `answer`: real reference answer

No questions, answers, benchmark metrics, confidence values, or masks are fabricated.

## Architecture choice

The current supervised implementation uses BLIP VQA + LoRA and creates a single temporal canvas labelled T1/BEFORE and T2/AFTER. This is a practical supervised baseline, not a claim that BLIP is a native two-image architecture. A later model-specific CDVQA architecture can replace the runtime while keeping the same manifest and orchestration contract.

## Relationship to Change Detection

Change Detection produces the measured change mask/statistics. Change VQA is responsible for answering the natural-language question. The neural Change VQA model receives the image pair directly; the grounded fallback consumes upstream change evidence. It does not independently invent quantitative measurements.
