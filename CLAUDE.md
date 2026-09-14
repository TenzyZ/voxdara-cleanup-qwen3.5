@AGENTS.md

# Claude Code — Voxdara

## Default Role

For Voxdara, act primarily as a senior AI/model-training planner, technical researcher, experiment designer, and critical reviewer.

For planning or review tasks, stay read-only unless the user explicitly authorizes implementation or training.

## Completed Cleanup-Model Run

Train Run v1 and the comparable Eval v1.1 Base/LoRA evaluation are complete. Use `experiments/train-run-v1/ACCEPTANCE.md`, `LIMITATIONS.md`, `MODEL_CARD.md`, and `runs/MANIFEST.sha256` as the closeout evidence.

Step 126 is accepted for product integration by human decision. Formal classification remains `FINAL_CLASSIFICATION_REQUIRES_HUMAN_DECISION`; semantic review provenance is `AI_ASSISTED_BLIND_SEMANTIC_REVIEW`.

Preserve the frozen contract, datasets, results, review, identity key, and external adapter reference. The older Base benchmark remains historical evidence. No retraining, new inference, rejudging, model publication, or product implementation is currently authorized.

## Scope Discipline

Avoid over-engineering.

Do not create additional datasets, abstractions, scripts, documentation, or experiment matrices unless they are necessary for the current objective.

Use subagents only when independent parallel research materially improves the result. Do not delegate simple sequential work.

When implementation is explicitly approved, inspect the actual runtime and files before changing anything and make the smallest production-quality change.

## Final Review

Before presenting a training plan, verify that it:

- does not modify frozen Eval v1
- does not modify frozen Train v2
- does not change the benchmark contract
- does not use the old smoke adapter for the base comparison
- does not silently switch model checkpoints
- does not expose secrets
- does not treat training loss as the success metric
- defines how the candidate will be compared with the existing base benchmark

If any of these conditions cannot be satisfied, stop and explain why.
