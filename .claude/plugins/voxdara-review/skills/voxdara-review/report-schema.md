# Review output contract

Report scope (root, branch, HEAD, base, index/worktree/untracked/intent-to-add),
checks and evidence provenance first. Candidates must include confidence 0-100,
severity, originating reviewer, exact file/symbol/lines, invariant, reachable
observed behavior, root cause, consequence, evidence and repair/test boundary.
Candidates are not bugs until an independent validator confirms them and the
main session checks structural evidence. No LOW, nits, style, speculation,
unrelated pre-existing bugs, mechanically prevented behavior or finding quota.

For every confirmed finding use this exact schema:

## <ID> <short title>

- Status: CONFIRMED
- Severity: BLOCKER | HIGH | MEDIUM
- Confidence: <0-100; at least 80>
- File: <exact repository-relative path>
- Symbol: <exact symbol, or NOT_APPLICABLE>
- Location: <one-based line/range, or NOT_AVAILABLE with explanation>
- Reviewer: <originating reviewer(s)>
- Invariant: <applicable rule/contract/expected behavior>
- Observed behavior: <what reachable code actually does>
- Root cause: <specific cause>
- Consequence: <concrete impact>
- Evidence:
  - <definition, caller, guard, history, contract or test evidence>
- Serena confirmation:
  - <exact symbol/caller/reference evidence, or NOT_AVAILABLE and fallback evidence>
- Repair boundary:
  - <smallest allowed repair area>
- Do not change:
  - <frozen datasets/contract/historical Base and relevant unrelated surfaces>
- Verification:
  - <meaningful negative-path regression and check/command when known>

BLOCKER invalidates experiment trust, violates authorization, corrupts evidence
or artifacts, or leaks Train/Eval methodology. HIGH is a concrete functional or
reliability bug with meaningful impact. MEDIUM is a real repair-worthy defect
without threatening experiment validity/core execution. Confidence measures
evidence after disproof, not reviewer enthusiasm.

Keep NEEDS_EVIDENCE items in a separate section labeled uncertainties, never in
the bug list or repair handoff. Briefly record rejected candidate IDs and reasons.
Missing reviewer/validator results or material conflicting evidence cannot PASS.

# CODEX REPAIR HANDOFF

Include ONLY the confirmed findings above. For each: finding ID, exact file/symbol,
defect, primary evidence, smallest permitted repair, prohibited changes, required
regression test, and exact verification command/check when known. If none, state
"No validated repairs." Do not authorize execution, training or Git publication.
Do not add uncertain improvements or automatically apply any repair.

# Overall verdict

Emit exactly one verdict token:

- BLOCKED: at least one confirmed BLOCKER.
- NEEDS_HUMAN_REVIEW: materially conflicting/insufficient evidence, incomplete
  independent review, or unresolved HIGH-only disposition.
- PASS: all required reviews completed, no material evidence gaps/conflicts,
  and no confirmed BLOCKER/HIGH remains. MEDIUM findings can coexist with PASS.

The requested policy defines BLOCKED only for BLOCKER and PASS excludes HIGH.
For HIGH without BLOCKER, use NEEDS_HUMAN_REVIEW and explain this policy gap;
never silently PASS or invent a fourth verdict.
