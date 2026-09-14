---
base_model: Qwen/Qwen3.5-0.8B
base_model_relation: adapter
library_name: peft
license: apache-2.0
pipeline_tag: text-generation
language:
- en
- ne
- hi
tags:
- lora
- text-cleanup
- dictation
---

# Voxdara Cleanup Qwen3.5 — draft model card

DRAFT for a future separately authorized Hugging Face publication. No model repository or weights have been published by this closeout. The language metadata describes the intended English, Romanized Nepali, Romanized Hindi, and code-switching cleanup task; it is not a claim of general language capability.

## Model relationship and intended use

This is a PEFT/LoRA adapter for text cleanup after an STT layer: raw transcript text → cleaned transcript text. It is not a speech model, accepts no audio input, and is not a command-execution model. Dictated questions and commands are content to preserve. The future Voxdara desktop application is outside this repository.

- Base: `Qwen/Qwen3.5-0.8B`, post-trained checkpoint.
- Base revision: `2fc06364715b967f1860aea9cf38778875588b17`.
- Candidate: step 126; BF16 / 16-bit PEFT LoRA; `r=16`, `lora_alpha=16`, `load_in_4bit=false`.
- Adapter: `adapter_model.safetensors`, 25,587,104 bytes; SHA-256 `E4348C9098F62843371BD00247790B428EC3E8332E3C3CE2337DE72BF3138085`.
- Training `max_seq_length=256`; eval/serving `max_seq_length=2048`; generation `max_tokens=256`.

The frozen contract targets only `model.language_model.layers.*` with complete module suffixes `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`: 96 modules and 6,389,760 trainable parameters. Vision and MTP targets are excluded; DeltaNet projection targets are not enabled. See [contract.json](contract.json).

## Training and evaluation

Training used frozen Train v2 (500 rows), two epochs, and step 126. Training loss is not product-quality evidence. Frozen Eval v1 contains 60 cases and was not training/selection data. Evaluation used one case per request, fresh context, the canonical cleanup prompt, thinking disabled, temperature 0, top_p 0.8, top_k 20, min_p 0, presence_penalty 0, repetition_penalty 1.0, and max_tokens 256.

Formal Eval v1.1 status: `FINAL_CLASSIFICATION_REQUIRES_HUMAN_DECISION`.

Human product decision: `ACCEPT STEP 126 FOR PRODUCT INTEGRATION`.

Review provenance: `AI_ASSISTED_BLIND_SEMANTIC_REVIEW`, not all-human review.

| Metric | Base Eval v1.1 | Step-126 LoRA Eval v1.1 |
|---|---:|---:|
| Cases | 60 | 60 |
| Exact matches | 4 | 43 |
| Legacy constraint passes | 23 | 53 |
| Boundary constraint passes | 23 | 54 |
| Legacy false negatives | 0 | 1 |
| Truncations | 2 | 0 |
| API errors | 0 | 0 |
| Mean latency (s) | 2.273 | 1.131 |
| p95 latency (s) | 10.234 | 1.565 |
| Semantic acceptable | 4 | 49 |
| Semantic minor defect | 19 | 7 |
| Semantic unacceptable | 37 | 4 |
| Pairwise wins | 1 | 54 |

Pairwise ties: 5. Mechanical constraints do not establish semantic correctness.

Critical failures and genuine regressions cannot be mechanically derived from the frozen review schema without new judgment. The contract's unclassified rule requires human decision. Product acceptance does not change the formal evaluation classification.

## Limitations and evidence

All 14 accepted limitations, including the two repository-closeout resolutions, are recorded in [LIMITATIONS.md](LIMITATIONS.md). Remaining model and review limitations stay active. Use [ACCEPTANCE.md](ACCEPTANCE.md) for frozen hashes and [MANIFEST.sha256](runs/MANIFEST.sha256) for the 15 preserved evidence files. Historical Windows paths remain as provenance.

## License and attribution

Apache-2.0 was verified from the local upstream snapshot at the pinned base revision: its README metadata declares `license: apache-2.0` and its LICENSE contains Apache License 2.0 and Copyright 2026 Alibaba Cloud. Upstream LICENSE SHA-256: `BBEDC3FDA3305820B977265F01B8619D87570A6739DE3A5582C3464840F1E57A`.

This is an independent project, with no affiliation with or endorsement by Qwen/Alibaba.

Future tagged source revision: **PENDING — populate only after review, merge, synchronized main, and creation of `cleanup-step126-eval-v1.1`.**
