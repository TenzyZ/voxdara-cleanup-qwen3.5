# Step-126 acceptance record

Human product decision: ACCEPT STEP 126 FOR PRODUCT INTEGRATION

Formal Eval v1.1 status: FINAL_CLASSIFICATION_REQUIRES_HUMAN_DECISION

Product integration acceptance is a human engineering decision freezing Voxdara's first cleanup-model candidate for downstream integration. Formal Eval v1.1 did not mechanically yield PASS. Critical failures and genuine regressions cannot be mechanically derived from the frozen review schema without new judgment. The contract's own unclassified rule therefore requires human decision; this closeout does not make a new evaluation judgment.

Every mechanically derivable PASS metric was measured. This does not change the formal classification. Semantic acceptable counts are 49/60 overall, 12/15 self-correction, 3/6 technical preservation, 18/23 language aggregate, and 10/10 minimal change. Pairwise LoRA wins are 54; p95 latency is 1.565 s (approximately 0.153 times Base). These are frozen-review derivations, not new semantic ratings.

## Frozen candidate

- Base: `Qwen/Qwen3.5-0.8B`, post-trained checkpoint.
- Base revision: `2fc06364715b967f1860aea9cf38778875588b17`.
- Candidate: step 126; BF16 / 16-bit PEFT LoRA; `r=16`, `lora_alpha=16`, `load_in_4bit=false`.
- Adapter: `adapter_model.safetensors`, 25,587,104 bytes; SHA-256 `E4348C9098F62843371BD00247790B428EC3E8332E3C3CE2337DE72BF3138085`.
- Training `max_seq_length=256`; eval/serving `max_seq_length=2048`; generation `max_tokens=256`.

## Frozen artifacts

| Artifact | SHA-256 |
|---|---|
| Eval v1 (60 cases) | `116443FC3A6332DDB3D0250B60F02B524C745AE1836B4174D9E700783278814A` |
| Train v2 (500 rows) | `4FD564314574228EFC1539BA55EB5019CBDA474F192F78C4134AE3F97060CFAF` |
| Canonical contract | `1E6A4296A87541E119D6C73B2316CB6D421DFE2AFC85F88D3DF2733AE9886678` |
| Frozen repaired review | `ABA0B564DFCF8B767E08A1B87902C85E2676A35EC672A0482529448983A0B441` |
| Preserved pre-repair review | `CE4120028396195895D9709BF2BB6010944C6A08865FEA2B8C90A6260C027DB7` |

The canonical contract hash uses its declared compact sorted-key UTF-8 serialization, not raw file bytes. See [contract.json](contract.json) and [MANIFEST.sha256](runs/MANIFEST.sha256).

## Evaluation and review provenance

Review provenance: `AI_ASSISTED_BLIND_SEMANTIC_REVIEW`; this was not all-human review and did not fulfill the originally specified human-only review procedure. The human product decision is separate from that review.

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

The bounded CMD-001 repair and its pre-repair review remain preserved under `runs/voxdara-trainv2-lora-r16a16-e2-run1/blind-review-v1.1/review/`. No ratings were changed during closeout. See [LIMITATIONS.md](LIMITATIONS.md).

Adapter weights remain external and unpublished. Future post-merge tag: `cleanup-step126-eval-v1.1`; no tag is created by this record.
