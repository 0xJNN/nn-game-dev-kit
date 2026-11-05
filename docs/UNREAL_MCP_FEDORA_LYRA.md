# Unreal MCP on Fedora 45 — Lyra hero-FPS setup

Written 2026-11-04 against Epic's current Unreal MCP documentation.

This guide connects an AI client to your running Lyra-based Unreal Editor using **Epic's official Unreal MCP plugin**, then sets up the PCG workflow described in [Working with PCG and LLMs](https://dev.epicgames.com/documentation/unreal-engine/working-with-pcg-and-llms-using-unreal-mcp-in-unreal-engine). The server runs inside Unreal; a separate community Python bridge is not required.

**Status:** setup instructions, not a verified MCP installation. Unreal MCP is experimental. Fedora 45 is the target you supplied; this document does not claim Epic certifies that distribution.

## 1. Identify your engine and actual Lyra project

The repository's [Unreal setup notes](UNREAL.md) record UE **5.8.4** at:

```text
/run/media/d/SEARCHX_WORK/Unreal/engines/5.8.4
```

Those notes describe the Novanode lab and an earlier Fedora observation, not proof of your Lyra project's engine association. Use your actual hero-FPS `.uproject` below; its path has deliberately not been guessed.

In a Fedora terminal, substitute the project path:

```bash
export UE_ROOT='/run/media/d/SEARCHX_WORK/Unreal/engines/5.8.4'
export LYRA_PROJECT='/absolute/path/to/YourHeroFPS/YourHeroFPS.uproject'
export LYRA_ROOT="$(dirname "$LYRA_PROJECT")"

cat /etc/fedora-release
cat "$UE_ROOT/Engine/Build/Build.version"
test -f "$LYRA_PROJECT" && echo 'Project file found'
test -x "$UE_ROOT/Engine/Binaries/Linux/UnrealEditor" && echo 'Editor found'
nvidia-smi
```

Confirm that this engine version already opens your Lyra project successfully. If Unreal proposes converting the project, stop and make a separate migration copy first. MCP setup should not implicitly become an engine migration.

The RTX 3090 is shared with inference services. Check available VRAM before adding a local model workload; leave existing user services running. A GPU-resident local LLM is not required for MCP itself.

No Fedora package installation is normally needed just to enable the in-engine server. If your project requires compilation, use the engine's matching Linux toolchain; do not substitute Fedora's host Clang solely to set up MCP. See [Epic's Linux requirements](https://dev.epicgames.com/documentation/en-us/unreal-engine/linux-development-requirements-for-unreal-engine).

## 2. Save a baseline and open the correct editor

1. Save your current work and review your source-control changes.
2. Record a playable baseline: the intended Lyra Experience loads, the pawn spawns, movement and weapons work, and your current hero abilities work.
3. Reserve one editor owner for this session. Use one AI client issuing editor mutations sequentially.
4. If Lyra is already open in the intended engine, use that instance. Otherwise launch:

   ```bash
   "$UE_ROOT/Engine/Binaries/Linux/UnrealEditor" "$LYRA_PROJECT"
   ```

5. Confirm the project and map in the editor before connecting an agent.

Keep the first MCP exercise in a new test map and an owned content folder such as `/Game/MCP_Sandbox/`. Preserve the working Lyra maps and Experience assets.

## 3. Enable the official plugins

In **Edit → Plugins**:

1. Find and enable **Unreal MCP**. Its internal identifier is `ModelContextProtocol`.
2. Enable **All Toolsets** for Epic's documented general-purpose setup. **Toolset Registry** is enabled as a dependency.
3. For the linked PCG workflow, enable **Procedural Content Generation Framework (PCG)** and **PCGToolset** if they are not already enabled.
4. Save and restart the editor when prompted.

All Toolsets is a convenience bundle. Epic also supports enabling individual toolsets; after the initial setup, retain only those you need. Enabling the server alone does not provide the editor tools.

If a plugin is missing, confirm the installed engine version and plugin availability rather than installing an unrelated plugin with a similar name. For a local descriptor check:

```bash
find "$UE_ROOT/Engine/Plugins" -type f \( \
  -name 'ModelContextProtocol.uplugin' -o \
  -name 'AllToolsets.uplugin' -o \
  -name 'PCGToolset.uplugin' \)
```

## 4. Start a local MCP server

Start manually for the first session. In the editor console, or the command field in **Output Log**, enter:

```text
ModelContextProtocol.StartServer 8000
```

The documented default endpoint is:

```text
http://127.0.0.1:8000/mcp
```

Look for `LogModelContextProtocol` messages in **Output Log** confirming the listener address, port, and path. On Fedora, inspect the actual listener:

```bash
ss -ltnp 'sport = :8000'
```

Expect loopback (`127.0.0.1` or `::1`), not `0.0.0.0`, `*`, or a LAN address. Epic documents that binding also depends on `[HTTPServer.Listeners] DefaultBindAddress`; if the actual socket is public, stop the server and inspect that configuration before proceeding:

```text
ModelContextProtocol.StopServer
```

The plugin has no authentication layer. Keep it on loopback; no `firewall-cmd` port opening, public tunnel, or SELinux disablement is needed for this local setup. If Fedora reports an actual denial, investigate that specific denial rather than changing system-wide protections.

If port 8000 belongs to another service, leave that service alone and choose a free port, for example 8010. Set **Editor Preferences → General → Model Context Protocol → Server Port Number**, then start the server on that port and use the same port in the client configuration.

Once the connection is working, you can enable **Auto Start Server** in that preferences panel. The default URL path is `/mcp`; **Enable Tool Search** should initially remain enabled.

## 5. Connect your AI client

Use a client with **Streamable HTTP** MCP support. Unreal's server is not a `stdio` executable.

### Generate the configuration for your chosen client

In the Unreal console, run just the appropriate command:

| Client | Editor console command |
| --- | --- |
| Cursor | `ModelContextProtocol.GenerateClientConfig Cursor` |
| Claude Code | `ModelContextProtocol.GenerateClientConfig ClaudeCode` |
| VS Code | `ModelContextProtocol.GenerateClientConfig VSCode` |
| Gemini | `ModelContextProtocol.GenerateClientConfig Gemini` |
| Codex | `ModelContextProtocol.GenerateClientConfig Codex` |

Read the Output Log to find the actual generated path. Epic describes the project root for installed builds and workspace-root considerations for source builds. Open your client in that directory and enable/reconnect the generated `unreal-mcp` server using its MCP controls.

For reference, Epic's generated **Claude Code** `.mcp.json` has this shape:

```json
{
  "mcpServers": {
    "unreal-mcp": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

Other clients have their own configuration schemas; do not assume this JSON can be pasted into every client. Use the selected port if you changed it. Review the generated diff: Epic says JSON configurations are merged, whereas its Codex TOML generator refuses to overwrite an existing file. Preserve existing configuration and merge a needed entry deliberately rather than deleting the whole file.

**Repository-specific policy:** [UNREAL.md](UNREAL.md#optional-official-mcp--later-not-silently-enabled) notes that generated OpenCode profiles currently deny MCP servers. A working editor endpoint does not override that policy. If using one of those profiles, its owner must deliberately configure and permit this local integration; generating a configuration for a different client does not configure OpenCode.

### Optional: test without an LLM

If Node.js/npm is already available, Epic recommends the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector
```

This command may download the Inspector package. In its UI, choose **Streamable HTTP**, enter `http://127.0.0.1:8000/mcp` (or your chosen port), and connect. Verify initialization and tool discovery. A browser GET or simple HTTP response alone is not an MCP handshake test.

## 6. Verify a read-only round trip

Select one recognizable actor in your test map, then ask your agent:

> Connect to unreal-mcp. Inspect the available toolsets and report the active project, map, and selected actors using available read-only tools. Do not modify or save anything. If a detail cannot be queried, say so. Make tool calls sequentially.

Check the answer against the editor. The advertised server name is `unreal-mcp`; that name alone does not identify which project is open.

With **Enable Tool Search** on, seeing only these three tools is normal:

- `list_toolsets`: discover toolsets.
- `describe_toolset`: inspect a toolset's actual schemas.
- `call_tool`: invoke one of its tools.

Let the client discover the schemas instead of inventing tool names or parameters. The server serializes tool execution on Unreal's game thread, and Epic explicitly advises against overlapping calls.

## 7. Load the PCG toolset and generation skill

Epic's PCG guide requires loading **`Skill_PCGGraphGeneration`** before graph work. Enabling the PCG plugin is not equivalent to loading that skill into the model's context.

Ask:

> Discover the PCG toolset and inspect its available tools. Locate and load Skill_PCGGraphGeneration using the skill-loading mechanism available in this client/toolset. Confirm which skill content you loaded before proposing graph edits. If it is unavailable, stop and report what is missing.

Epic does not give one universal slash command or skill installation path for all clients. Use the actual discovery results and your client's supported skill-loading mechanism. Shipping toolsets do not advertise MCP Resources or Prompts, so an empty Resources/Prompts list does not prove the integration is broken.

Then:

1. In the Content Browser, enable visibility of engine/plugin content if necessary.
2. Locate **Engine → Plugins → Procedural Content Framework (PCG) → SampleContent**.
3. Select a relevant sample graph and your intended mesh assets manually.
4. Ask the agent to inspect those references before planning.
5. Duplicate a suitable graph into your owned sandbox folder and make small edits.

If the installed build lacks those samples, supply an existing working project graph instead; do not let the model invent undocumented nodes as a substitute.

## 8. First hero-FPS exercise: bounded cosmetic dressing

Use a small decorative scatter in a test area before asking MCP to edit hero abilities or playable combat spaces. Create a test map, choose a few existing meshes, and define the permitted bounds yourself.

Example prompt:

> Work only in /Game/MCP_Sandbox/ and the currently selected test-area actor. Inspect the selected PCG reference graph and meshes first. Propose a duplicate graph that scatters a small, bounded number of cosmetic props with a fixed seed. Keep spawn points, navigation routes, doors, combat sightlines, and objective areas clear. Use non-blocking collision for this cosmetic test. List the assets and actors you intend to modify, then wait for my confirmation. Execute one change at a time, and report the generated count and any errors.

After approving the plan:

1. Generate the small test area and inspect it in the editor.
2. Ask for **Data View/Dataview** when inspecting generated points and attributes; avoid dumping entire datasets into model context.
3. Check density, transforms, collision, bounds, and reproducibility with the fixed seed.
4. Enter Play In Editor and verify movement, weapons, and abilities still behave normally.
5. For your multiplayer path, run the usual multi-client test before promoting changes into a playable map.
6. Review and save only the intended changes.

For Lyra, keep Experience definitions, pawn data, input configuration, Ability Sets, Gameplay Tags, and Game Feature activation outside this first exercise. PCG dressing does not implement hero-FPS gameplay or establish network authority. Any later gameplay-affecting generation needs explicit collision, replication, and client/server validation.

For surface detail, Epic also documents `Skill_PCGInstancingOnMeshActor`; for modular sequences, `Skill_PCGShapeGrammarDefinition`. Load additional skills only when that task needs them. Semantic asset search is documented for UE 5.8 or later, but manually selecting known assets is usually the clearest starting point.

## 9. Troubleshoot by layer

| Symptom | Next check |
| --- | --- |
| Unreal MCP absent from Plugins | Confirm the actual engine build and its `ModelContextProtocol.uplugin`; do not mix binaries from another engine version. |
| Server fails to start | Inspect Output Log and `ss`; check for a port conflict or missing plugin dependency. |
| Client cannot connect | Start the editor/server first; verify the generated file location, client workspace, port, `/mcp` path, and Streamable HTTP transport. Check client MCP permission policy. |
| Only three tools appear | Normal tool-search mode: use `list_toolsets`, then `describe_toolset`. |
| No PCG toolset | Verify PCG/PCGToolset are enabled and dependencies loaded; restart if prompted. |
| Tools stale after changes | Run `ModelContextProtocol.RefreshTools`, then reconnect the client. |
| Wrong project responds | Check which editor owns the port. Use one intended instance, or assign explicit distinct ports. |
| PCG graph is wrong or empty | Confirm the generation skill was loaded; inspect a working reference and use Data View for attributes. |
| Editor busy or request times out | Inspect the editor and logs; reconcile whether the action completed before retrying. A timeout does not prove it failed. |

For more logging, enter:

```text
Log LogModelContextProtocol Verbose
```

## 10. Finish and record the result

Stop the server when finished:

```text
ModelContextProtocol.StopServer
```

Disable **Auto Start Server** if it should remain opt-in. To roll back the trial, review the source-control diff and undo only the trial's changes; preserve pre-existing project and client configuration edits.

Record the engine build, project/map, enabled plugins, endpoint, client, read-only test result, and sandbox playtest result. In this repository, put generated logs and evidence under `.studio/`. Track connection/tool verification separately from human visual/gameplay approval.

For changes made in this repository, run:

```bash
python3 studio.py test
python3 studio.py unreal validate
```

These repository checks do **not** validate an external Lyra project or an MCP session. Validate that project with its own build/tests and the editor steps above. Epic notes the MCP server can also be hosted in cooked builds; do not assume enabling it for development proves it is absent from a shipping configuration.

## Official references

- [Unreal MCP: setup, console commands, transport, tool search, limitations](https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor)
- [Working with PCG and LLMs Using Unreal MCP](https://dev.epicgames.com/documentation/unreal-engine/working-with-pcg-and-llms-using-unreal-mcp-in-unreal-engine)
- [Linux development requirements](https://dev.epicgames.com/documentation/en-us/unreal-engine/linux-development-requirements-for-unreal-engine)
- [Local engine setup and project acceptance gates](UNREAL.md)
