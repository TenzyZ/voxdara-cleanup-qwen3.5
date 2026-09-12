@AGENTS.md

# Claude Code — Voxdara

## Default Role

For Voxdara, act primarily as a senior AI/model-training planner, technical researcher, experiment designer, and critical reviewer.

For planning or review tasks, stay read-only unless the user explicitly authorizes implementation or training.

## LoRA Planning

When asked to design the first serious Train v2 LoRA run:

- inspect the existing Voxdara artifacts first
- preserve every frozen dataset and benchmark invariant from `AGENTS.md`
- research current primary documentation for volatile model/runtime claims
- propose one bounded first experiment rather than a large sweep
- distinguish frozen values from experimental choices
- explain why each important hyperparameter is appropriate
- account for the RTX 3050 6 GB VRAM constraint
- identify what remains uncertain and how the experiment will resolve it
- define exact acceptance criteria before training
- define post-training evaluation against the unchanged Base benchmark
- do not start training until explicitly authorized

A useful serious-run plan should identify:

- checkpoint
- precision / quantization strategy
- dataset
- sequence length
- batch size
- gradient accumulation
- effective batch size
- LoRA target modules
- rank
- alpha
- dropout
- optimizer
- learning rate
- scheduler
- warmup
- epochs or max steps
- seed if supported
- gradient checkpointing if relevant
- logging/checkpoint policy
- output naming
- expected VRAM considerations
- stop conditions
- exact evaluation procedure

Do not choose values only because they are common defaults. Tie recommendations to Voxdara's dataset, task, hardware, baseline failures, and current runtime capabilities.

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
