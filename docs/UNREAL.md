# Unreal / Linux setup and acceptance gates

## Preparation status

The user chose **project preparation first**, with engine installation deferred. The source
targets UE **5.8** based on current Epic documentation; no installed editor or native build has
validated that target yet. Do not label source validation as an engine compile/render pass.
Linux is the active target. No macOS work is required for this phase.

## Installation boundary

Get the Linux editor through [Epic's official Linux page](https://www.unrealengine.com/en-US/linux)
using your own account and current license terms. This repository neither downloads Epic's
engine nor accepts its EULA. Review game vs non-game/visualization licensing before commercial use.
Plan space for the editor, derived data, shader caches, intermediate builds, and packaged output.
Approximately 75 GiB was free during research; no old models/tools were deleted to make space.

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

The source includes a larger interior, modular bench/equipment details, light panels, local
interaction traces, a sliding collision gate, power/reference consoles, and first-person controls.
It is still built from primitives. A richer source layout is not a claim of production art.
The shared Blender/GLB pilot is preserved separately; import into Unreal is a follow-up native gate.

Rendering defaults select Vulkan/SM6, software Lumen, mesh distance fields, and virtual shadows.
Hardware ray tracing is off for initial iteration. Measure and tune these on the actual scene;
they are not a performance guarantee. Avoid loading a large local model while compiling shaders
or using the editor's GPU rendering pipeline.

## Native gates — not yet run here

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
