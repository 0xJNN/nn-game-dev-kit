---
name: bounded-production
description: Executes a reviewed Novanode work package with bounded context, attempts, time, and evidence. Use when explicitly assigned a studio task contract.
disable-model-invocation: true
---

# Bounded production

1. Read `AGENTS.md` and the assigned contract. Confirm the human approved the goal.
2. Run `python3 studio.py task context tasks/<task>.json`. Load no unrelated history.
3. Review every argv and write boundary; the runner is not a sandbox.
4. For implementation, change only assigned paths. Do not launch helpers by default.
5. Use deterministic scripts for exports, inspection, and checks instead of reasoning loops.
6. Preview with `python3 studio.py task run tasks/<task>.json`.
7. Execute the reviewed package with `--execute`. Stop on acceptance or limits.
8. Return run ID, evidence paths, modified files, known gaps, and `human_approval: pending`.

Example: `tasks/unreal-source.json` verifies source/portable logic without claiming an engine pass.
If blocked, record the blocker; do not create more work or raise your own budget.
