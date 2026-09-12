# Voxdara Base Model Benchmark

## Model

Qwen/Qwen3.5-0.8B

## Dataset

Eval v1

SHA-256: 116443FC3A6332DDB3D0250B60F02B524C745AE1836B4174D9E700783278814A

Cases: 60

## Inference Settings

```text
temperature: 0
top_p: 0.8
top_k: 20
min_p: 0
presence_penalty: 0
repetition_penalty: 1.0
max_tokens: 256
fresh context per case: yes
```

## Deterministic Results

Exact expected-output matches: 3 / 60
Constraint passes: 31 / 60
API errors: 0
Average latency: 1.362 seconds

## By Category

- code_switching: 0/8 exact, 4/8 constraint-pass
- command_preservation: 0/3 exact, 3/3 constraint-pass
- minimal_change: 3/10 exact, 7/10 constraint-pass
- question_preservation: 0/3 exact, 2/3 constraint-pass
- romanized_hindi: 0/7 exact, 5/7 constraint-pass
- romanized_nepali: 0/8 exact, 8/8 constraint-pass
- self_correction: 0/15 exact, 1/15 constraint-pass
- technical_preservation: 0/6 exact, 1/6 constraint-pass

## Important

Exact match and must_preserve/must_not_contain checks are deterministic mechanical metrics.

They do not by themselves prove semantic correctness, intent preservation, or acceptable cleanup.
Human/semantic scoring is still required before treating this as the final quality score.

Generated: 2026-09-12T18:50:10.349369+00:00
