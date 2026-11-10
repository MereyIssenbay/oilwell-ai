# Phase 7 ML consistency review

Reviewer: assigned `ml_engineer`. Scope is deterministic replay inference, not model reselection or a new performance benchmark. The selected model remains rejected for monitoring. Only registered train/validation sources were read; no test source was decoded or scored, no parameters were fitted, and no artifact was changed.

## Test evidence

`tests/ml/test_replay_consistency.py` uses the actual locally saved Phase 5 model and registered original sensor frames. It compares against integrity-checked saved validation predictions with the previously established absolute score tolerance `1e-14`, relative tolerance zero, and exact binary decisions. Different batch shapes may change floating-point arithmetic slightly; bitwise score equality across batch shapes is not required.

Command: `.venv/Scripts/python.exe -m pytest tests/ml/test_replay_consistency.py -q -p no:cacheprovider --tb=short`.

Final observed result: **11 passed in 7.75 seconds**, with no failures or skips. An earlier six-check run passed before the replay service was available.

The checks cover all three validation source first-window scores, unchanged past predictions after future value/missingness perturbations, exact causal source-specific Runtime input slices, rejection of `class`/`state` as sensor inputs, short-history abstention, and absence of a normal prediction when retained sensor evidence is completely missing. Fixture teardown verifies that model bundle files, inference implementation, selection, and the one-shot test journal retain their original hashes.

Three actual-model replay-service runs at configured speeds 0.1, 1 and 20 compare **all 21** demo-window scores and decisions per run against saved validation, assert original ordering of all 260 telemetry records, preserve source timestamps, verify historical-playback envelopes, and reconcile two episode openings separated by one resolution. These deterministic tests call the worker's one-row advancement with scheduling bypassed; they establish speed-independent inference, not measured wall-clock scheduling accuracy. Persistence is an explicitly injected fixture store. Real PostgreSQL and HTTP/SSE lifecycle checks are owned by backend/QA/root.

An unaligned replay start at position 5603 proves that position 5659 cannot be inferred with only 57 session observations, while position 5662 cannot reset the frozen global stride. The first emitted prediction is at 5669 with the exact original window 5610–5669. Subsequent windows end at 5679 and 5689, contain no pre-start or future observations, and remain sensor-only. A 59-row replay emits telemetry but no prediction or alert.

## Reproducible retrospective demonstration

Choose validation source `3w:3b7750afe480cb1d04361795d4a5cded832ae3a05d5ef30f533d440c81bfb4cf`, published well ID `WELL-00011`. Original label-only inspection, separate from serving/inference, confirms these inclusive runs:

| Positions | Original class | Interpretation |
| --- | --- | --- |
| 0–3599 | null | Unknown; must not be treated as normal |
| 3600–5758 | 0 | Documented normal |
| 5759–7271 | 102 | Transient for family 2, spurious closure of DHSV |

Replay inclusive positions **5600–5859** (260 original one-second observations). Source timestamps remain naive; transport assumes UTC without asserting verified source timezone. This interval starts `2014-05-30T10:05:23` and ends `2014-05-30T10:09:42`. The frozen 60-row/10-stride alignment yields prediction endpoints 5659, 5669, …, 5859 after replay-local warmup.

Saved validation results predict an initial positive at position 5659 (`10:06:22`) while ground truth is normal. Ground truth changes to transient 102 at 5759 (`10:08:02`); the detector remains positive across that boundary. Decisions become negative at 5809 (`10:08:52`) through 5839 (`10:09:22`) despite the transient label, then positive again at 5849 (`10:09:32`). Actual replay-service predictions and episode transitions matched these saved results at all three configured speeds. Root separately reconciles the HTTP/PostgreSQL demo output before publication.

This example deliberately exposes a false alarm and missed abnormal interval. It cannot establish physical causality, precise operational event onset, reliable detection delay, or accepted monitoring quality. The first positive episode is left-censored by replay warmup: there is no preceding usable negative prediction within this session.

## Boundaries

Wall-clock playback speed may affect processing time only. Source timestamps, model score, frozen threshold, feature windows and episode decisions must remain invariant. No pre-start observations should populate replay-local warmup, and no future observations or labels may enter inference. Ground truth belongs only to a retrospective, explicitly separate evaluation artifact.

The cohort was exposed during EDA and validation informed model/threshold selection. These checks validate software consistency; they do not restore independent generalization evidence or change the failed model-quality conclusion.

No model-consistency blocker was found. Shared contracts, documentation and release acceptance remain with the orchestrator; no cross-owner code edits were made.
