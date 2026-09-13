# Voxdara Train v2

## Status

FROZEN

## Dataset

File:

training/data/voxdara-cleanup-train-v2.jsonl

Rows:

500

## SHA-256

4FD564314574228EFC1539BA55EB5019CBDA474F192F78C4134AE3F97060CFAF

## Frozen At

2026-09-12T18:11:44.180293+00:00

## Source Dataset

Train v1 SHA-256:

7CFAFF40E46DD23097C2BFC6AF74B3EC126C58EFEF37A29E149E834BE37E0E37

## Frozen Eval

Eval v1 SHA-256:

116443FC3A6332DDB3D0250B60F02B524C745AE1836B4174D9E700783278814A

## Changed Rows From Train v1

102, 169, 306, 308, 325, 384, 385, 418

## Validation

Train rows: 500
JSON/schema: PASS
Canonical system prompt: PASS
Exact duplicate Train inputs: none
Exact Train-Eval leakage: none
Train-Eval semantic review candidates: none
Output-sanity issues: none

Train-Train similarity candidates remain informational and are recorded in:

training/TRAIN_V2_AUDIT.txt

## Freeze Rule

Train v2 is frozen.

Do not modify, add, remove, or rewrite examples in Train v2.

Any later intentional dataset change must become Train v3 with a new validation cycle and SHA-256.

Frozen Eval v1 must never be used as training data.

## Live PEFT Adapter Gate v1

The 103 checkpoint-index suffix matches comprise 96 intended language projections
and seven MTP projections. The verified Studio Transformers 5.3.0 runtime does not
instantiate those MTP modules: both installed Unsloth-regex and raw PEFT-list
resolution produce 96 live LoRA layers and 6,389,760 trainable parameters.

Preflight now checks both live resolutions against the exact seven authorized
language projection paths, with zero MTP, vision, foreign, or non-LoRA trainable
matches. This protects against silent Transformers, Unsloth, or PEFT changes.

Approved Option A permits local meta-device adapter construction for evidence
only, despite contract v1's inspection-policy prose prohibiting model/adapter
construction. `contract.json` remains byte-identical with its approved canonical
hash. No checkpoint weights are loaded, no adapter is saved, and no Trainer or
training occurs. Preflight PASS is evidence only; training remains unauthorized.
