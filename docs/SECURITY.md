# Trust and operational boundaries

## Unreal and model setup

Unreal is installed/authorized by a human; no Epic EULA is accepted by automation. Engine/model
downloads are not implicit setup steps. Local serving is localhost-only and opt-in; it must not
unload or stop existing services. GPU estimates do not isolate VRAM or guarantee no OOM.
Generated OpenCode V2 examples are inactive. A cloud `:free` price is not a privacy guarantee;
review provider/account policies and do not send proprietary material without authorization.
Local OpenCode profiles are text-only until a vision encoder/projector is explicitly tested.
The studio ledger does not automatically account for external OpenCode requests.

## The runner is not a sandbox

`--execute` runs reviewed argv as the current user. No shell is used, common credential
environment variables are not inherited, deadlines/log limits are monitored, and owned process
groups are terminated. But commands still can read home-directory credentials, access the network,
modify files outside the checkout, or spawn detached processes. A container/OS sandbox and
provider-side caps are necessary before accepting untrusted tasks or unattended paid adapters.

Allowed writes are audited **after** a command and cannot undo side effects. The audit hashes
source files and symlink identities, excluding `.git/`, `.studio/`, `.godot/`, `.venv/`,
`__pycache__/`, `artifacts/`, and Unreal `Binaries/Intermediate/Saved/DerivedDataCache` directories.
It is not a real-time monitor. Violations are reported without
deleting or reverting work. Do not edit source concurrently with a running package.

CLI commands outside `task run` use the normal environment. The task process environment is
reduced, not secret-proof. Keep approved secrets out of logs and receipts. SQLite and receipt
files are local private state; do not expose them through a public web UI or artifact upload.

## Editors and assets

Use one integrator per live editor and explicit project identity. Cooperative file locks do not
prevent other clients from modifying the project. The Blender batch route uses factory startup
and disables automatic execution of scripts embedded in files. Only reviewed scripts are run.
Do not import untrusted blend files, addons, or generated code into your normal workstation.

MCP bridges stay local. Review plugin source, telemetry, licenses, versions, and arbitrary-code
capabilities. A network tunnel must be authenticated; never expose editor ports publicly.

## Billing and publishing

No paid adapter is enabled. Opt-in free cloud profiles use zero-price ceilings and no other
provider fallback, but project settings can be overridden by higher-authority OpenCode config.
A ledger reservation does not authorize a purchase. Require explicit
human approval and provider-level spending caps before any paid submission. Unknown jobs retain
their holds; do not reset/delete a ledger to bypass caps. An overrun requires human reconciliation.

No signing credentials, accounts, remote repositories, or publishing workflows are configured.
macOS is deferred; only archived Godot artifacts used local ad-hoc signing (no developer identity).
CI uploads only allowlisted internal evidence/build
directories, not the ledger, receipts, or download cache. Review logs before enabling CI for
sensitive projects. Signing, storefront submission, and external distribution are separate gates.

Tool pins protect against unexpected archive changes, not against a malicious original vendor.
The optional MCP package pin does not freeze all transitive dependencies; audit/lock those before
production deployment. The starter GLB inspector is not a security validator for hostile files.
