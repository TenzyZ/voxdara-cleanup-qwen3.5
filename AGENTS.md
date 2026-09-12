# Voxdara — Agent Instructions

## Mission

Voxdara is a local-first Windows desktop dictation system.

The product loop is:

hotkey
→ microphone capture
→ local STT
→ raw transcript
→ optional cleanup LLM
→ final text
→ active application

The current work is ONLY the local cleanup model.

The cleanup model is:

raw transcript text
→ cleanup LLM
→ cleaned transcript

It is text-to-text. It is not STT and not a speech-language model.

Optimize for:

- preserving the speaker's actual intent
- reliable self-correction handling
- English, Romanized Nepali, Romanized Hindi, and code-switching
- preservation of names, numbers, commands, paths, URLs, code, model IDs, and technical vocabulary
- low cleanup latency
- local-first privacy
- measurable improvement over the frozen base-model benchmark

Do not expand the current work into STT, capture, desktop UI, provider routing, accounts, cloud infrastructure, or unrelated product features.

## Evidence First

Inspect relevant project files before making claims about repository state, datasets, model settings, benchmark results, dependencies, APIs, or runtime behavior.

When present, use these as project references:

- `PROJECT.md` — product and architecture contract
- `Prompt_Engineering_Reference.md` — read before prompt-engineering work
- `Senior_AI_Coding_Agent_Engineering_Reference.md` — read for coding-agent or harness engineering work
- `eval/EVAL_V1.md`
- `eval/voxdara-cleanup-eval-v1.jsonl`
- `training/TRAIN_V2.md`
- `training/TRAIN_V2_AUDIT.txt`
- `training/data/voxdara-cleanup-train-v2.jsonl`
- `benchmarks/base-qwen3.5-0.8b/results.jsonl`
- `benchmarks/base-qwen3.5-0.8b/SUMMARY.md`

If documentation, hashes, files, runtime output, or user-provided evidence conflict, report the conflict. Do not silently rewrite an artifact to make the evidence agree.

## Frozen Evaluation Artifact

Frozen Eval v1:

`eval/voxdara-cleanup-eval-v1.jsonl`

Cases:

`60`

SHA-256:

`116443FC3A6332DDB3D0250B60F02B524C745AE1836B4174D9E700783278814A`

Rules:

- never modify Eval v1
- never train on Eval v1
- never regenerate it after seeing model failures
- never change expected answers to improve a score
- always verify its hash before a formal benchmark

## Frozen Training Artifact

Current training dataset:

`training/data/voxdara-cleanup-train-v2.jsonl`

Rows:

`500`

SHA-256:

`4FD564314574228EFC1539BA55EB5019CBDA474F192F78C4134AE3F97060CFAF`

Rules:

- Train v2 is frozen
- do not modify it during the current experiment
- do not substitute Train v1
- do not automatically create Train v3
- preserve Train v1 and Train v2 as provenance artifacts

## Base Model

Current model:

`Qwen/Qwen3.5-0.8B`

Use the post-trained / instruction-capable checkpoint.

Do not automatically switch to:

- `Qwen/Qwen3.5-0.8B-Base`
- QLoRA / 4-bit
- continued pretraining
- full fine-tuning
- a custom tokenizer
- another model family

Any such change requires evidence and explicit user approval.

## Frozen Benchmark Contract

Base and post-LoRA evaluation must use the same inference contract:

- model family: `Qwen/Qwen3.5-0.8B`
- canonical Voxdara cleanup system prompt
- temperature: `0`
- top_p: `0.8`
- top_k: `20`
- min_p: `0`
- presence_penalty: `0`
- repetition_penalty: `1.0`
- max_tokens: `256`
- one Eval case per request
- fresh context for every case
- no conversational history between cases

Do not change benchmark settings between Base and LoRA evaluation.

## Verified Base Benchmark

The untouched post-trained model has completed the frozen 60-case baseline.

Recorded result:

- cases: `60`
- exact matches: `3/60`
- mechanical constraint passes: `31/60`
- API errors: `0`
- average latency: `1.362s`

Mechanical constraint pass is NOT semantic correctness.

Human review found important failures that mechanical checks sometimes missed, including:

- failure to resolve spoken self-corrections
- answering dictated questions instead of cleaning them
- assistant-style responses and refusals
- Romanized language alteration or conversion
- technical-token corruption
- command/content deletion
- unwanted translation or rewriting

The first trained candidate must be compared against this exact baseline.

## Current Objective

Design the first serious Voxdara Train v2 LoRA experiment.

Do not start GPU training merely because a plan has been produced.

The currently accepted direction is:

- model: `Qwen/Qwen3.5-0.8B`
- training data: frozen Train v2
- method: BF16 / 16-bit LoRA SFT

Previously successful smoke-run values provide an experimental starting point, not a frozen serious-run configuration:

- context: around `2048`
- batch size: `1`
- gradient accumulation: `4`
- LoRA rank: `16`
- LoRA alpha: `16`
- LoRA dropout: `0`
- learning rate: around `2e-4`
- epoch search range: approximately `1–3`

Do not repeat the old 10-epoch smoke run as the serious configuration.

The serious configuration must be justified from evidence, hardware feasibility, dataset size, and current runtime behavior.

## Experiment Discipline

Prefer the smallest experiment that answers the current question.

Where practical:

- change one meaningful experimental variable at a time
- record the exact model/checkpoint
- record dataset hash
- record training configuration
- record seeds when available
- record runtime/library versions
- record training duration
- record peak RAM/VRAM when available
- preserve loss history
- preserve produced adapter separately
- never overwrite the frozen base benchmark
- use clearly named experiment output directories

Training loss alone is not evidence of product quality.

After training, run the exact frozen Eval v1 benchmark again using the same inference settings as the base benchmark.

Compare at minimum:

- exact-match behavior
- deterministic constraints
- semantic intent preservation
- self-correction quality
- question/command preservation
- Romanized-language preservation
- technical-token preservation
- hallucinated additions
- meaning-changing deletions
- latency
- failure rate

Human semantic review remains required.

## Hardware and Runtime

Known hardware/runtime:

- Windows
- NVIDIA GeForce RTX 3050 Laptop GPU
- 6 GB VRAM
- Unsloth Desktop

A previous 16-bit LoRA smoke run completed successfully.

Do not assume a proposed serious configuration fits VRAM merely because the smoke run worked. Estimate and verify.

For volatile claims about Unsloth, Qwen, CUDA, PyTorch, PEFT, bitsandbytes, model repositories, licenses, or runtime support, research current primary sources before recommending settings.

Clearly distinguish:

- confirmed fact
- inference
- recommendation
- experiment

## Secrets and Privacy

Never expose, echo, log, commit, or hardcode:

- Unsloth API tokens
- provider API keys
- other credentials

Use environment variables or protected runtime input for secrets.

Local Voxdara mode must not silently transmit audio, transcripts, clipboard contents, active-window contents, datasets, or credentials to external services.

## Scope and Change Control

For planning, review, research, and experiment-design requests, remain read-only unless the user explicitly authorizes changes.

Never modify frozen datasets or benchmark evidence as part of implementation.

Avoid unrelated refactors or infrastructure work.

Do not initialize Git, create branches, commit, push, open PRs, or merge unless the user explicitly requests that workflow.

If Git is already present and development begins, follow the project rule:

one phase
→ one branch
→ one scoped objective
→ one pull request
→ reproducible verification
→ human approval before merge

Before modifying files:

1. inspect the actual project state
2. identify the smallest required change
3. state assumptions
4. define verification
5. make only the authorized change

## Failure Handling

When something fails, identify the failing layer before changing architecture:

- dataset
- validator
- benchmark harness
- model
- training configuration
- inference configuration
- runtime/environment
- API

Form one hypothesis, apply the smallest fix, and retest.

Do not rewrite working architecture to solve a localized problem.

## Stop Conditions

Stop and report instead of guessing when:

- a frozen hash does not match
- a required artifact is missing
- model/checkpoint identity is ambiguous
- benchmark settings cannot be verified
- a command could destroy or overwrite evidence
- credentials would need to be exposed
- the requested action exceeds the approved phase
- evidence is insufficient to justify a training decision

## Reporting

For substantial work, report:

- evidence inspected
- confirmed state
- assumptions
- recommendation or change
- exact configuration or files affected
- verification performed
- results
- remaining risks or unresolved decisions

Do not claim success from agent narration. Use observable evidence.
