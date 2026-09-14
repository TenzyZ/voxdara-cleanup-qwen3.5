# Voxdara — Evaluation Protocol v1.1 Amendment

## Overview

This document specifies the Evaluation Protocol v1.1 amendment for the Voxdara cleanup model evaluation harness.

Eval v1.1 amends only execution pipeline control semantics and blind-review ingestion. It introduces no changes to evaluation test cases, expected outputs, canonical prompts, base model checkpoint, trained LoRA adapter weights, generation parameters, or acceptance criteria thresholds.

## Rationale & Background

During the initial fresh evaluation attempt of the untouched Base model (`Qwen/Qwen3.5-0.8B`) on the frozen 60-case Eval v1 suite (`eval/voxdara-cleanup-eval-v1.jsonl`), three test cases exhausted the frozen `max_tokens=256` limit and terminated with `finish_reason="length"`:

- **`MIN-003`** (input: `"ma aile ghar ma chu"`): The base model converted the Romanized Nepali transcript into repetitive Devanagari Hindi text (`"मैंने आपके लिए एक सुसंगत और संक्षिप्त रूप दिया है:..."`), repeating loop cycles until reaching 256 tokens.
- **`CS-002`** (input: `"ma aile free chu so we can start the test"`): The base model outputted a grammatical lecture in Devanagari Hindi explaining the utterance, repeating loops until reaching 256 tokens.
- **`CS-003`** (input: `"aap ye config check karo and let me know if anything fails"`): The base model assumed an interactive assistant persona in Devanagari Hindi (`"नमस्ते, मैं आपकी संपादक (dictation cleanup engine) हूँ..."`), refused to perform a config check (`"**मैं अभी नहीं कर सकता।**"`), and repeated refusal statements until reaching 256 tokens.

These outputs represent genuine model behavioral failures (Devanagari conversion, assistant meta-commentary, refusal, and repetitive token generation). They are not transport or API operational failures.

Under the initial Eval v1.0 harness implementation:
1. Completed benchmarks with any model truncations returned exit code `1`, causing sequential evaluation pipelines to halt before evaluating subsequent arms.
2. The blind-pack preparation function (`compatible_results()`) enforced `finish_reason == "stop"`, rejecting any benchmark set with truncations as an operational failure (`REVIEW_INPUT_OPERATIONAL_FAILURE`) and blocking blind human A/B review.
3. Destination paths were hardcoded, preventing rerun without colliding with or overwriting existing evidence.

The initial Base evaluation attempt was halted after 55 cases upon observing these truncations.

## Preservation of Existing Evidence

The interrupted Base evaluation attempt remains fully preserved:
- Location: `experiments/train-run-v1/runs/voxdara-trainv2-lora-r16a16-e2-run1/benchmarks/base/`
- Evidence files: `provenance.json` (SHA-256 `CCDC270A...`) and `results.jsonl` (55 cases, SHA-256 `7A6C1B23...`).
- This evidence is not deleted, overwritten, or resumed.

## Protocol Changes in Eval v1.1

Eval v1.1 modifies only harness pipeline control and review ingestion semantics:

1. **Benchmark CLI Exit Semantics**:
   - `python tools/voxdara_experiment.py benchmark` returns exit code `0` upon successfully completing all 60 cases, even if model truncations occur.
   - Non-zero exit codes are strictly reserved for genuine API, HTTP, transport, or schema errors (`api_errors > 0`).
   - Truncations remain recorded in `summary.json`, counted in `aggregate()`, and subject to acceptance thresholds.

2. **Blind-Review Compatibility**:
   - `compatible_results()` accepts model outputs where `error is None`, `output` is a valid string, and `finish_reason` is in `["stop", "length"]`.
   - Truncated outputs are preserved verbatim in `review.jsonl` (as `A_output` or `B_output`) so human reviewers can observe and score the actual model behavior during blind A/B review.
   - Any case with `error is not None` or an unsupported/missing `finish_reason` continues to fail closed with `REVIEW_INPUT_OPERATIONAL_FAILURE`.

3. **Explicit Destination Routing**:
   - The `--destination` parameter on `benchmark` and `blind-pack` commands enables directing new evaluation outputs to dedicated, repository-contained directories.
   - Standard destination paths for Eval v1.1:
     - Base benchmark: `experiments/train-run-v1/runs/voxdara-trainv2-lora-r16a16-e2-run1/benchmarks/eval-v1.1/base`
     - LoRA benchmark: `experiments/train-run-v1/runs/voxdara-trainv2-lora-r16a16-e2-run1/benchmarks/eval-v1.1/lora`
     - Blind review pack: `experiments/train-run-v1/runs/voxdara-trainv2-lora-r16a16-e2-run1/blind-review-v1.1`
   - Destination collision protection (`OUTPUT_ALREADY_EXISTS`) remains strictly enforced.

## Frozen Invariants (Unchanged)

Every core experimental invariant remains unchanged:

- **Train Run v1 Contract**: `experiments/train-run-v1/contract.json` (SHA-256 `1E6A4296A87541E119D6C73B2316CB6D421DFE2AFC85F88D3DF2733AE9886678`).
- **Eval Dataset**: `eval/voxdara-cleanup-eval-v1.jsonl` (60 cases, SHA-256 `116443FC3A6332DDB3D0250B60F02B524C745AE1836B4174D9E700783278814A`).
- **Training Dataset**: `training/data/voxdara-cleanup-train-v2.jsonl` (500 rows, SHA-256 `4FD564314574228EFC1539BA55EB5019CBDA474F192F78C4134AE3F97060CFAF`).
- **Canonical Prompt**: 481 UTF-8 bytes (SHA-256 `6BA7FD9E1EA544BA4E8BD3F5E5B974CE118EBA7B8925449E3B4399D6F1564D6D`).
- **Base Model**: `Qwen/Qwen3.5-0.8B` (revision `2fc06364715b967f1860aea9cf38778875588b17`).
- **LoRA Candidate**: Step 126 final adapter (SHA-256 `E4348C9098F62843371BD00247790B428EC3E8332E3C3CE2337DE72BF3138085`).
- **Generation Parameters**:
  - `temperature`: `0`
  - `top_p`: `0.8`
  - `top_k`: `20`
  - `min_p`: `0`
  - `presence_penalty`: `0`
  - `repetition_penalty`: `1.0`
  - `max_tokens`: `256`
  - `enable_thinking`: `false`
- **Acceptance Criteria**:
  - `PASS`: `truncations_eq: 0`, `api_errors_eq: 0`, `outputs_eq: 60`, `boundary_constraints_min: 39`, `blind_paired_wins_min: 12`, etc.
  - `FAIL_any`: `truncations_min: 1`, `api_errors_min: 1`, `critical_failures_min: 1`, etc.

## Evaluation Status

Base Eval v1.1 completed (60 cases). LoRA Eval v1.1 completed (60 cases). Blind semantic review completed with provenance `AI_ASSISTED_BLIND_SEMANTIC_REVIEW`.

The repaired review is frozen at SHA-256 `ABA0B564DFCF8B767E08A1B87902C85E2676A35EC672A0482529448983A0B441`; the pre-repair review remains preserved.

Formal classification: `FINAL_CLASSIFICATION_REQUIRES_HUMAN_DECISION`.

The separate human product acceptance is recorded in [ACCEPTANCE.md](../experiments/train-run-v1/ACCEPTANCE.md).
