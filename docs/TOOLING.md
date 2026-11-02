# Legacy pilot tooling and shared accounting

The Godot/native-Mac setup described below is archived pilot information, not the current CI
target. Current engine setup is `UNREAL.md`; OpenCode V2/free/local model setup is `MODELS.md`.
The ledger protocol remains active and engine-independent. No Unreal MCP is required for this phase.

## Tool pins

- Python 3.11.8+ (including safe tar extraction filters); pipeline uses only the standard library.
- Godot 4.7.2 stable; Linux x86-64 and universal macOS downloads.
- Blender 4.5.15 LTS; Linux portable archive and official macOS disk images.

URLs/checksums are in `tools.lock.json`. `tools fetch` validates the archive against that
reviewed pin before extraction, leaves existing system applications untouched, and caches
under `.studio/`. `GODOT_BIN`/`BLENDER_BIN` override location, not version requirements.
Downloads require network access but no account. The full optional template archive is ~1.3 GB;
only Linux release and macOS templates are retained. No user Godot template directory is changed.
The universal macOS preset enables the Apple Silicon texture format and built-in local ad-hoc
signing. This requires no certificate/account and does not notarize or authorize distribution.

CI caches tools by OS/architecture/lock-file hash. It tests Python on Linux/macOS, builds the
bench with native Blender, runs the gold path, then exports and launches each native build.
The macOS CI helper mounts the verified DMG read-only and detaches it afterward; it does not
install an app. This path needs an actual macOS runner before its status can be verified.

## Optional Blender MCP

`mcp.example.json` is an **inactive**, generic stdio example pinned to `mcp-for-blender==2.2.6`.
Review the server and matching addon, then adapt it to your approved client's config format.
Use an absolute `uvx` path for GUI clients if needed. Safe mode is requested and telemetry is
disabled, but neither configuration is a complete sandbox. Do not run the example installer
or connect an editor automatically. Engine automation currently needs no Godot MCP.

Blender's addon bridge may allow arbitrary Python. Keep it on localhost; give one integrator
ownership of the interactive file. Heavy/repeatable exports stay in background processes.

## SDK strategy

Godot's engine API implements behavior; Blender Python implements content production; MCP is
an optional interactive bridge. Do not confuse these with an agent orchestration SDK.
Use the existing coding agent first. Add a provider SDK only with a demonstrated need,
reliable usage receipts, scoped credentials, budget reservation, and restart/reconciliation tests.
No live SDK integration or paid model runner is implied by this starter.

## Ledger protocol for a future approved adapter

No command below submits a provider request. Example only:

```sh
python3 studio.py jobs reserve --key bench-concept-v1 --task bench-concept --provider example --operation image --max-cost 0.50
python3 studio.py jobs attach bench-concept-v1 --job-id provider-job-123
python3 studio.py jobs get bench-concept-v1
python3 studio.py jobs settle bench-concept-v1 --actual-cost 0.12 --outcome accepted --receipt path/to/receipt.json
python3 studio.py jobs report
```

- Only `action: submit` on a **new** reservation permits the adapter's one submission.
- `resume`: poll the existing provider ID; `reconcile`: submission outcome is ambiguous.
- Never clear a hold merely because a process timed out or the job looks old.
- Reserve before the paid call and persist its ID immediately afterward. A crash between those
  actions still requires provider reconciliation; this is not an exactly-once network protocol.
- Settlements are immutable; actual overruns are recorded honestly and freeze new reservations.
- The same provider/job ID cannot be attached to two accounting keys.
- Cancellation may release unused funds only after an actual provider receipt establishes cost.

Receipt JSON may contain `usage` with nonnegative integer `input_tokens`, `cache_read_tokens`,
`cache_write_tokens`, and `output_tokens`. Store each provider message/job once. The adapter must
normalize provider-specific definitions and avoid overlapping categories. Unknown fields are
not invented. Dollar cost comes from supplied billing evidence, not hardcoded model rates.

The ledger is local accounting, not provider-side enforcement. Users can bypass it, and arbitrary
commands may incur unobservable charges. Configure provider-side caps before adding paid adapters.
Do not claim the ledger tracks this coding conversation's usage—it only tracks jobs explicitly recorded here.
