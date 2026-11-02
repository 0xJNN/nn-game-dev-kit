# Novanode Studio — project-wide agent contract

- Unreal/Linux is primary. Godot is a preserved legacy pilot; macOS is deferred.
- Read the current task contract and only its listed inputs. Do not load all docs/skills.
- Use `python3 studio.py task context <contract>` for a size-bounded handoff.
- No helper agents unless the human explicitly authorizes delegation.
- One owner per interactive editor, scene, settings file, and integration operation.
- Use background Blender for repeatable assets; never attach to someone else's live file.
- Run `python3 studio.py test` and the relevant engine/asset check after changes.
- Preserve a playable gold path. Do not weaken checks merely to make a task pass.
- Do not edit the running task, runner, hooks, or fixtures mid-run. Stop and checkpoint first.
- Statuses: implemented → machine_verified → human_approved. Only humans grant the last one.
- Look at screenshots before describing them. Headless tests do not verify visual quality.
- Never claim the analytic lab demonstration is a validated physical simulation.
- Stay within the task's writes, deadline, attempts, and budget. Stop when done or blocked.
- Task writes are audited after commands, not sandboxed. Do not run untrusted contracts.
- No paid calls without explicit approval; reserve and persist a job ID before waiting.
- Timeout is unknown, not failure. Resume/reconcile; never blindly resubmit or clear holds.
- Never read, log, or commit credentials. No blanket permission bypass or public MCP ports.
- No publishing, remote creation, pushes, purchases, or release signing without approval.
- Keep generated tools/builds/evidence in `.studio/`; generated bench outputs are ignored.
- Keep reusable lessons small. Turn repeat failures into regression tests before new prose.
- Preserve user changes. Report unauthorized writes; never silently delete or revert them.
- Never accept an engine EULA or download large model/engine payloads without explicit approval.
- Model cards/price metadata are not benchmarks. Test actual quant, tool transport, and coding tasks.
- Unreal and inference share the 3090. Check VRAM; never stop existing user services to make room.

On demand: `docs/UNREAL.md`, `docs/MODELS.md`, `docs/WORKFLOW.md`, `docs/SECURITY.md`.
