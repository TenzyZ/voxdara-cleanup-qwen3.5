# Voxdara Cleanup Qwen3.5

Model R&D, training, and evaluation for Voxdara's text-cleanup layer. This is **not the Voxdara desktop application**. It cleans text produced by an STT layer: raw transcript text → cleaned transcript text. It is **not a speech model**, does not consume microphone audio, and does not execute dictated commands.

A future separate Voxdara product repository will own the desktop application, including capture, STT, and application integration.

## Frozen integration candidate

Step 126 is the human-accepted candidate for product integration: `ACCEPT STEP 126 FOR PRODUCT INTEGRATION`.

Formal Eval v1.1 status remains `FINAL_CLASSIFICATION_REQUIRES_HUMAN_DECISION`. Product acceptance is a separate human engineering decision; it does not change that classification. Critical failures and genuine regressions cannot be mechanically reconstructed from the frozen review schema without new judgment.

- Base: `Qwen/Qwen3.5-0.8B`, post-trained checkpoint.
- Base revision: `2fc06364715b967f1860aea9cf38778875588b17`.
- Candidate: step 126; BF16 / 16-bit PEFT LoRA; `r=16`, `lora_alpha=16`, `load_in_4bit=false`.
- Adapter: `adapter_model.safetensors`, 25,587,104 bytes; SHA-256 `E4348C9098F62843371BD00247790B428EC3E8332E3C3CE2337DE72BF3138085`.
- Training `max_seq_length=256`; eval/serving `max_seq_length=2048`; generation `max_tokens=256`.

Adapter weights are external, unpublished, and **not in this Git repository**. The repository preserves their hash and provenance; no Git LFS is required for this closeout.

## Frozen Eval v1.1 comparison

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

Semantic review provenance: `AI_ASSISTED_BLIND_SEMANTIC_REVIEW`. This was AI-assisted blind review, not all-human review. All [14 accepted limitations](experiments/train-run-v1/LIMITATIONS.md) are retained; only evidence durability and stale documentation were resolved by closeout.

## Evidence and reproduction

- [Contract](experiments/train-run-v1/contract.json): frozen configuration and canonical serialization hash.
- [Acceptance](experiments/train-run-v1/ACCEPTANCE.md): human decision, formal classification, candidate identity, and frozen hashes.
- [Run evidence](experiments/train-run-v1/runs/voxdara-trainv2-lora-r16a16-e2-run1/): 15 original files, including the interrupted 55-case Base attempt, completed Base/LoRA pair, blind review, identity key, and preserved pre-repair review.
- [Manifest](experiments/train-run-v1/runs/MANIFEST.sha256): checksums for those local evidence files; external adapter metadata is comments only. The manifest excludes itself.
- [Eval v1.1 protocol amendment](eval/EVAL_V1_1.md) and [draft model card](experiments/train-run-v1/MODEL_CARD.md).

Frozen evidence contains historical local Windows paths. Those paths are retained unchanged for provenance. The older `benchmarks/base-qwen3.5-0.8b/` benchmark remains historical evidence; the completed Eval v1.1 pair is the finalized comparable comparison.

Run from the repository root in PowerShell with Python and Git available. These commands validate and score existing files only; they do not perform inference or training and require no model download or credentials.

```powershell
python tools/voxdara_experiment.py validate-contract
python tools/voxdara_experiment.py score --results experiments/train-run-v1/runs/voxdara-trainv2-lora-r16a16-e2-run1/benchmarks/eval-v1.1/lora/results.jsonl
python tools/voxdara_experiment.py score --results experiments/train-run-v1/runs/voxdara-trainv2-lora-r16a16-e2-run1/benchmarks/eval-v1.1/base/results.jsonl
python -m unittest discover -s tests -p "test_voxdara_experiment.py"
python -m unittest discover -s tests -p "test_*.py"
```

Expected canonical contract SHA-256: `1E6A4296A87541E119D6C73B2316CB6D421DFE2AFC85F88D3DF2733AE9886678`. Do not compare this to the raw byte hash of `contract.json`. Scoring reports semantic review as `NOT_VERIFIED` because it scores mechanical constraints only; the frozen semantic review is separate evidence.

Verify the manifest on disk and against committed Git blobs:

```powershell
@'
from pathlib import Path
import hashlib, subprocess
manifest = Path('experiments/train-run-v1/runs/MANIFEST.sha256')
entries = [line.split('  ', 1) for line in manifest.read_text().splitlines()
           if line and not line.startswith('#')]
assert len(entries) == 15
for expected, name in entries:
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest().upper() == expected, name
    blob = subprocess.check_output(['git', 'show', 'HEAD:' + name])
    assert hashlib.sha256(blob).hexdigest().upper() == expected, name
print('15 local evidence files verified on disk and in HEAD')
'@ | python -
```

## License and project attribution

[Apache License 2.0](LICENSE). The pinned upstream Qwen snapshot's LICENSE and README metadata were independently checked locally; LICENSE SHA-256 is `BBEDC3FDA3305820B977265F01B8619D87570A6739DE3A5582C3464840F1E57A`. Upstream attribution: Copyright 2026 Alibaba Cloud.

Independent project; no affiliation with or endorsement by Qwen/Alibaba.

No retraining or new inference is currently authorized. Model publication, desktop product work, and the future `cleanup-step126-eval-v1.1` tag require their separate post-review phases.
