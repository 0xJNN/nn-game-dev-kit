# Studio operating workflow

Current runtime: Unreal/Linux. Setup gates: `UNREAL.md`; free/local agent profiles: `MODELS.md`.
The old Godot pilot is preserved but is no longer the default delivery target.
## 1. Brief and feasibility

Product owner records goal, audience, platforms, references, budget, non-goals, and measurable
acceptance. Spike the riskiest engine/platform/domain dependency before commissioning content.
Engineering simulations need units, assumptions, independent reference cases, and domain review.

## 2. Greybox and vertical slice

Prove the interaction with primitives. Replace only one representative asset/feature with its
final production route. Confirm import, test, package, and normal-launch behavior on target OSes.
Do not start parallel content production before this works.

## 3. Work packages and agent handoffs

Copy `tasks/feature.json.example` to a new `.json` file and replace the placeholders. A contract
defines explicit text inputs, writes, acceptance, argv commands, deadline, timeout, attempts,
budget, and optional shared resource. Commands never use shell expansion; `{python}`, `{root}`,
and `{evidence}` are substituted by the runner.
Use `tasks/unreal-source.json` before engine installation and `tasks/unreal-smoke.json` after
native setup/packaging. Native build/cache directories are excluded from the source audit;
generator-owned content needs an explicit write allowance for preparation tasks.

```sh
python3 studio.py task validate tasks/your-feature.json
python3 studio.py task context tasks/your-feature.json
python3 studio.py task run tasks/your-feature.json
```

Use the context output in the team's existing coding agent/IDE. The context cap is characters,
not an exact tokenizer limit. Oversized inputs are refused, not silently truncated. Pick the
stronger model for design/hard debugging; use cheaper models only after measuring accepted output.
No agent is invoked automatically. OpenCode V2 profiles can be generated on demand, but are
inactive until reviewed and activated. Free-route quotas, zero-price ceilings, and provider
privacy are separate from the studio ledger; see `MODELS.md` before sending source to a cloud model.

For a trusted deterministic package, approve the argv and execute with `--execute`. Do not put
paid agent commands into a zero-cost task: the runner cannot measure arbitrary provider billing.
No mid-run changes to the contract, runner, verification scripts, or acceptance markers.

On completion, hand off only: task/run ID, changed files, evidence paths, unresolved defects,
and verification status. Review in fresh context with the contract and relevant diff. Do not
copy the full implementation transcript into another agent. Reviewer ≠ human acceptance.

## 4. Ownership and bounded execution

- One integrator owns shared scenes/settings and the open editor.
- Background asset tasks get separate outputs; integrate through a reviewed manifest.
- Resource locks coordinate these tools only; they do not lock unrelated editor clients.
- The runner stops at deadline, command timeout, attempt limit, write-boundary violation, or
  completion. It never refills an empty queue or starts another polish cycle.
- Evidence records individual commands, exit codes, bounded logs, attempts, and final status.
- Only a completed command with a known, nonnegative exit code can lead to a retry; a nonzero
  code repeats the full deterministic package within its attempts/deadline. Commands must be idempotent.
- Timeout, log-limit, signal termination, interruption, or an unclassified result stops execution
  without another step/attempt. The report preserves the command/log identity, `stop_reason`, write
  audit, and `reconciliation_required: true`; its status is `outcome_unknown` (or `deadline_exceeded`,
  `interrupted`, or `write_boundary_violated` when applicable). A zero exit code alone is not success.
  If the deadline expires before a command starts, it is not launched and there is no new unknown job.
- Before running again, a human must inspect the run journal and partial outputs, reconcile any
  external job/charge, and explicitly authorize a safe next execution. There is no automatic resume
  or cross-run resubmission guard yet; rerunning the CLI is not reconciliation. Preserve old evidence.

## 5. Release gate

1. Python regression tests pass.
2. Relevant asset checks pass and provenance is reviewed.
3. Gold path passes, with no script/import errors or failed assertions.
4. Native packaged build passes normal-startup smoke on each supported OS.
5. A human inspects fresh visuals, plays the build, and reviews feel/accessibility.
6. Measure frame-time distribution, memory, and stalls on named representative hardware;
   the starter does not yet enforce a performance target.
7. Review third-party rights, privacy/security, distribution requirements, known defects,
   and rollback artifacts. Apply signing/notarization only with authorized credentials.
8. Record human approval and explicit publication authorization. CI cannot grant either.

## 6. Maintenance and learning

Triage issues by user impact; preserve a last-known-working build. Update dependencies on a
dedicated branch with tests, not during a long run. Keep source in Git, large source binaries
in reviewed LFS/object-storage policies, and reproducible outputs out of Git.

For each recurring failure: record cause/evidence → add regression test → update one small
skill → remove obsolete advice. Promote the change into the shared template only after it
works on a second project. Do not make every agent reread the historical log.

## Metrics

Track accepted-feature cost, human correction time, rework, first-pass acceptance, build success,
escaped defects, and model usage categories. `jobs report` separates input/cache-read/cache-write/
output tokens from supplied receipts. Missing usage is unknown, never an invented zero.
There is no claimed cost-saving percentage until comparable projects have measured baselines.
