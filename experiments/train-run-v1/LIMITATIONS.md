# Step-126 accepted limitations

These are the 14 accepted limitations. Only items 12 and 13 are resolved by repository closeout; the remaining items stay active.

1. **Active:** Partial self-corrections may omit carried-forward content.
2. **Active:** Spoken `backslash` → `\` is not learned.
3. **Active:** Spoken `dash` → `-` is not learned reliably.
4. **Active:** Inferred filename underscores are imperfect.
5. **Active:** Numeric/currency normalization is inconsistent.
6. **Active:** Technical preservation is the weakest category at 3/6, exactly at the contract PASS floor.
7. **Active:** SC-003 is the one observed directional regression against Base.
8. **Active:** Mechanical constraints do not establish semantic correctness.
9. **Active:** Review was AI-assisted, not the originally specified human-only review.
10. **Active:** Critical-failure and genuine-regression requirements cannot be mechanically reconstructed from the frozen review schema.
11. **Active:** CMD-001 required a bounded post-review repair and the pre-repair evidence must remain.
12. **Resolved by this closeout:** Eval v1.1 evidence durability was inadequate because run evidence was untracked. All 15 existing evidence files are now committed byte-for-byte, with [MANIFEST.sha256](runs/MANIFEST.sha256).
13. **Resolved by this closeout:** `eval/EVAL_V1_1.md` contained stale pre-run status wording. Its Evaluation Status section now records the completed runs and frozen review, with the unchanged formal classification.
14. **Active:** Blindness relied partly on procedural discipline because identity data was co-located with review data.

See [ACCEPTANCE.md](ACCEPTANCE.md) for the separate human product decision and formal evaluation status.
