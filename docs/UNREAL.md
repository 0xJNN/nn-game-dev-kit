# Unreal / Linux setup and acceptance gates

## Preparation status

**2026-11-03:** an existing **UE 5.8.4** installation was found at
`/run/media/d/SEARCHX_WORK/Unreal/engines/5.8.4`. Its bundled v26/Clang **20.1.8** toolchain built
the actual lab editor module. Owned map/material preparation and all three native state tests
passed; all **77** Python/portable C++ regressions passed. The graphical editor initialized on the
RTX 3090, and the owner confirmed its window is visible. This is not gameplay, art/performance,
packaged startup, or broad human acceptance. Linux remains primary; macOS remains deferred.

Machine-local helpers created for this installation:

```sh
source .studio/unreal.env
python3 .studio/launch_unreal.py
```

Do not launch another instance if the editor is already open. Press **Play** to construct the lab
at runtime. Close the editor normally before exclusive build/preparation/native-test/package work.
For a fresh checkout without these ignored helpers, set `UE_ROOT` explicitly to the path above.

Evidence: `.studio/runs/unreal-rect-light-compat-395edc980ade/` records the successful native build
and asset generation; `.studio/runs/unreal-json-bom-compat-2b8c20b30fb8/` records fresh accepted
native tests and regressions; `.studio/runs/unreal-graphical-preflight-900537e94114/` records final
regressions/source/whitespace checks. Earlier audit stops are preserved in their run journals.
Editor visibility was confirmed by the owner; no screenshot review or physical-input pass is claimed.

Native integration required the documented rect-light component API and UTF-8-BOM-compatible JSON
decoding. With owner approval, the irrelevant AndroidFileServer plugin was disabled and its
auto-generated source settings removed. A regression checks that policy. Unreal also normalized
`DefaultInput.ini`; all six authored axes, both actions/modifiers, and explicit mouse flags were
checked unchanged. Audits stopped unexpected writes before these scoped fixes; checks were not
disabled. Keep generated asset write allowances explicit in future preparation contracts.

## Installation boundary

Get the Linux editor through [Epic's official Linux page](https://www.unrealengine.com/en-US/linux)
using your own account and current license terms. This repository neither downloads Epic's
engine nor accepts its EULA. Review game vs non-game/visualization licensing before commercial use.
Plan space for the editor, derived data, shader caches, intermediate builds, and packaged output.
The 2026-11-03 check found about 75 GiB free on the project drive and 409 GiB on SEARCHX_WORK.
These are observations, not a reservation or guarantee for another installation. No old
models/tools were deleted, existing services stopped, or licenses accepted during this setup.

Set the **installation root**, not the executable path:

```sh
export UE_ROOT=/your/UE_5.8
python3 studio.py unreal doctor
```

Expected files: `Engine/Binaries/Linux/UnrealEditor`, `Engine/Build/Build.version`,
`Engine/Build/BatchFiles/Linux/Build.sh`, and `Engine/Build/BatchFiles/RunUAT.sh`.
Major/minor mismatches are refused. Do not modify `studio.toml` and the project association
blindly to suppress the check: review APIs/build settings for that engine version first.
Use Epic's supported Linux environment/toolchain; the portable host C++ test is not proof
that Unreal's bundled compiler, SDK, distro, or Vulkan setup is ready.

Read-only review on 2026-11-02 found Fedora 44 with host Clang 22.1.8, 73.43 GiB free on the
project filesystem, and no `UE_ROOT` configured. UE 5.8 release notes specify Clang 20.1.8 and
reference Ubuntu/Rocky/RHEL configurations. This is a toolchain compatibility gate, not an instruction
to replace the host compiler, install Ubuntu, or assume native Fedora verification has passed.
The subsequent 2026-11-03 build used the installed engine's bundled Clang successfully; host Clang
was left unchanged. That scopes evidence to this project/build, not blanket distro certification.

## Preview, build, prepare, play

```sh
python3 studio.py unreal validate
python3 studio.py unreal build
python3 studio.py unreal build --execute
python3 studio.py unreal prepare --execute
python3 studio.py unreal run --execute
```

`build` invokes UBT's native Linux editor-module build. `prepare` invokes the editor Python
commandlet in unattended/NullRHI mode. It creates a parameterized surface material and a blank
map under `Content/Generated/`; the C++ game mode constructs the room when play begins.
`unreal editor --execute` opens the editor; press Play to see the runtime room. The empty editor
map before Play is expected, not a saved art scene. No asset pack, plugin account, or marketplace
content is downloaded. Existing unmarked assets are refused, not overwritten.
Already marked assets are reused without rebuilding. If the generator recipe changes later,
plan a reviewed versioned regeneration/migration; rerunning `prepare` alone does not update them.

The source includes a larger interior, modular bench/equipment details, light panels, local
interaction traces, a sliding collision gate, power/reference consoles, and first-person controls.
It is still built from primitives. A richer source layout is not a claim of production art.
The shared Blender/GLB pilot is preserved separately; import into Unreal is a follow-up native gate.

Rendering defaults select Vulkan/SM6, software Lumen, mesh distance fields, and virtual shadows.
Hardware ray tracing is off for initial iteration. Measure and tune these on the actual scene;
they are not a performance guarantee. Avoid loading a large local model while compiling shaders
or using the editor's GPU rendering pipeline.

## Native gates — state tests passed; packaging and runtime smoke pending

The three native state tests passed on 2026-11-03. Close the running editor before repeating these
commands. Linux packaging and packaged runtime smoke have not yet been run on this installation.

```sh
python3 studio.py unreal test --execute
python3 studio.py unreal package --execute
python3 studio.py unreal smoke --execute
```

- `test`: all three `Novanode.State.*` Unreal automation tests must appear and pass. Empty,
  skipped, duplicated, incomplete, or failed reports do not pass the parser.
- `package`: native Linux Development `BuildCookRun`; output `.studio/builds/unreal/Linux/`.
- `smoke`: launches that packaged application with NullRHI and checks fresh JSON evidence for
  the custom material, prerequisite rejection, actual door ray/collision changes, and period result.
- Runtime smoke does **not** synthesize hardware keyboard input or inspect images. Real E/WASD/
  mouse operation, visuals, accessibility, sound, frame-time/memory, and game feel need separate tests.

The portable test compiles the exact engine-independent `LabState.h` with the host C++ compiler.
It proves state/formula behavior only, not the Unreal actors, module, UHT, shaders, or packaging.

Review findings H5/H6 in [AI_CODING_RESEARCH.md](AI_CODING_RESEARCH.md) are only partly addressed:
the wrapper now reports interrupted commands as unknown, with reconciliation guidance. Durable
reconciliation and package/source build-identity provenance remain open; package acceptance still
only checks launcher existence. Inspect owned process/log state before retrying and retain exact
source/engine/artifact identity. Generator recipe migration/reuse concerns in H6 remain open too.

## CI and evidence

Public/ordinary CI runs Linux source checks without an Unreal install. `unreal-linux.yml` is a
manual workflow on an authorized self-hosted `novanode-unreal` Linux runner with `UE_ROOT` set.
It must never execute arbitrary fork/PR code on that runner. Build/test logs and fresh reports
live in `.studio/evidence/`; generated Unreal caches stay in ignored project directories.
Bounded task contracts remain trusted argv, not a sandbox. Never expose an Unreal Python/MCP
code-execution bridge publicly. Engine-native scripting/automation is sufficient for this phase.

## Optional official MCP — later, not silently enabled

UE 5.8 ships an **experimental** Unreal MCP plugin, identifier `ModelContextProtocol`. Evaluate
that native integration before adopting a community editor bridge. It can expose actor, lighting,
material, inspection, and automation tools over HTTP. This project does not enable it or assume
its Linux/authentication behavior is tested. Review binding/authentication, project identity,
permissions, and tool-discovery/context cost on the installed editor first. Generated OpenCode
profiles currently deny MCP servers; a deliberate narrow policy/config change is required.

Official references: [UE 5.8 release](https://www.unrealengine.com/news/unreal-engine-5-8-is-now-available),
[Unreal MCP](https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor),
[Linux requirements](https://dev.epicgames.com/documentation/en-us/unreal-engine/linux-development-requirements-for-unreal-engine),
[Python editor scripting](https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python),
[automation tests](https://dev.epicgames.com/documentation/en-us/unreal-engine/run-automation-tests-in-unreal-engine).
