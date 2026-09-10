# SatQuery-X — Evidence-First Frontend

This frontend is redesigned for a project demonstration where the evaluator needs to see **how the system processes a satellite query and how the final outcome is supported**.

## What changed

- Earth-observation glass UI with a lighter cinematic satellite/earth visual language.
- Cleaner analyst workstation navigation and glass panels.
- Query workflow remains connected to the existing Django API.
- Analysis results now include an **Outcome Quality & Correctness Evidence** panel.
- The panel separates:
  - Input/data quality
  - Model confidence
  - Geometry quality
  - Evidence coverage
  - Result confidence
- The UI explicitly distinguishes a composite **Outcome Quality Score** from true **accuracy**.
- Ground-truth accuracy is shown only when the backend provides a labeled benchmark metric. This prevents the presentation from claiming an unsupported accuracy percentage.
- Existing map, temporal observations, execution trace, evidence, reports, uploads and satellite search flows are retained.
- Fixed existing TypeScript issues found during validation (`EvidenceOutput` contract fields and missing `ShieldCheck` import).

## Local run

From the `frontend` directory:

```powershell
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

The Django backend should be available at:

```text
http://127.0.0.1:8000
```

Keep Redis/Memurai and the Celery worker running for background processing:

```powershell
celery -A config worker --loglevel=info --pool=solo
```

## Presentation flow

1. Open the landing page and explain the problem and solution.
2. Open **AI Assistant**.
3. Enter a real satellite query, e.g. `What is changing around Coimbatore over time?`.
4. Show the processing/activity trace while the backend executes the workflow.
5. Show T1/T2 observation evidence and the map.
6. Show **Outcome Quality & Correctness Evidence**.
7. Explain that the score is an evidence-quality/composite signal, while accuracy requires ground-truth labels.
8. Open the execution trace/evidence/report when asked how the answer can be verified.

## Validation performed on this package

TypeScript validation was run successfully with:

```text
node node_modules/typescript/bin/tsc --noEmit
```

A full production Next.js build could not be completed in the packaging environment because Next.js attempted to download its Linux SWC binary and external package-network access was unavailable. The source package is intended to be installed/built on the user's Windows development machine with `npm install`.
