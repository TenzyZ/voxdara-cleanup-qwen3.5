# Voxdara Train v1

## Status

FROZEN

## Dataset

File: training/data/voxdara-cleanup-train-v1.jsonl
Rows: 500
Format: JSONL

## SHA-256

7CFAFF40E46DD23097C2BFC6AF74B3EC126C58EFEF37A29E149E834BE37E0E37

## Frozen At

2026-09-12T21:40:41+04:00

## Cleanup Model

Qwen/Qwen3.5-0.8B

## Validation State

Train rows: 500
JSON parsing: PASS
Train schema: PASS
Canonical system prompt: PASS
Duplicate Train inputs: none
Exact Train-Eval leakage: none

Eval v1 rows: 60
Eval v1 SHA-256: 116443FC3A6332DDB3D0250B60F02B524C745AE1836B4174D9E700783278814A

## Freeze Rule

Train v1 is frozen.

Do not edit, add, remove, or rewrite Train v1 examples.
Any intentional dataset change must become Train v2 with a new validation cycle and SHA-256.

Frozen Eval v1 examples must never be added to training data.

## Limitation

This freeze establishes dataset identity and mechanical validation.
It does not prove semantic quality, absence of near-duplicate paraphrases, or model performance.
