# Paladins-inspired starter — Lyra played on Linux; original Hero Lab extension

Checked 2026-11-03. Keep the existing NovanodeLab intact; it is not a multiplayer shooter framework.
Official Lyra **5.8** now builds on Linux with the existing **Unreal 5.8.4** and passes a full
offline headless editor startup/normal-exit check. The human subsequently confirmed the window
and successfully played, but reported lag. That report is separate from headless startup and is
not a performance or multiplayer-correctness approval.

## Original hero sandbox — 2026-11-04

See [HERO_SANDBOX.md](HERO_SANDBOX.md) for the new opt-in plugin, small test map, mage projectile,
three-hit sword prototype, dash, and the exact verification gaps. Reusable source lives under
`projects/hero-sandbox/`; free-resource provenance/pins under `resources/hero-sandbox/`. Quaternius
UAL2 Standard and a CC0 claymore were actually acquired/imported locally, not merely recommended.
Player animation retargeting, visual/audio review, multiplayer and FPS gates remain separate.
No existing sample source, descriptor or config was edited for the extension; all 818 baseline
hashes and the vault were preserved. Use the new audited `manage.py gold`/`editor` commands in that
document: the earlier launcher intentionally refuses additions outside its original exact inventory.

## Graphical/performance observations — 2026-11-03

Two graphical sessions used the same command and unchanged graphics. Logged initialization changed
from **1181.842 s** to **14.827 s**, last reported compiled shaders **8,819 → 45**, and last cumulative
PSO-creation hitch counter **650 → 50**. This is consistent with warmed caches, not an applied graphics
optimization or a controlled same-scene FPS benchmark. PSO counters do not count distinct stalled
frames. No FPS/Frame/Game/Draw/GPU capture was available. Both raw sessions are archived separately
under `.studio/checkpoints/`; comparison:
`.studio/evidence/lyra-warm-session-comparison-2026-11-03.json`.

Both processes exited 0; only the first had the expected normal-exit marker. Do not transfer the
controlled headless lifecycle qualification to the second graphical shutdown. Sustained gameplay
performance, rendering quality and human performance approval remain unverified.

## Current verification and diagnosis

- Original: `/home/d/EpicVault/Lyra_5.8/data/Lyra.uproject`. Separate working copy:
  `.studio/lyra/projects/LyraStarterGame/Lyra.uproject`. Source, content, plugins, and config are
  present; the download is approximately **4.9 GiB**. Windows binaries are not Linux binaries.
- The project targets **5.8**; the installed engine is **5.8.4**. Its bundled **Clang 20.1.8 / v26**
  matches [Epic's UE 5.8 Linux toolchain requirements](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-5-8-release-notes).
- The initial native build failed with exit code **6** on six **CommonUser** unreachable-code
  diagnostics. A local deterministic repair changed only `CommonUserBasicPresence.cpp` and
  `CommonSessionSubsystem.cpp` in the separate working copy: four dead breaks were removed,
  a first-return range loop became guarded first-element handling, and a literal-zero disabled
  branch became `if constexpr`. Existing first-element behavior and disabled code remain intact;
  this does not establish that those semantics are the desired multiplayer behavior.
- The strict native rebuild passed without relaxing compiler checks; both native project modules
  were verified. All **818** original vault source/config/descriptor hashes remain unchanged.
  The working-copy hashes match exactly the intended two-file repair boundary.
- All **9** synthetic repair regressions, **10** synthetic editor-lifecycle regressions, and
  **77** repository regressions pass. These do not constitute Lyra gameplay coverage.
- The first headless startup reached initialization but timed out without verified normal exit.
  Its process was reconciled as gone, with no logged fatal/error and no source changes. This is
  preserved as interrupted evidence, not classified as a build failure or proven engine crash.
- A separate check using Epic's documented full-editor `ExecutePythonScript` lifecycle passed:
  initialization and an owned readiness marker, normal shutdown, exit **0**, zero logged errors
  or fatals, and unchanged original/repaired source hashes. Required installed scripting plugins
  were enabled only for that command-line session; no persistent project settings changed.
- The human later confirmed graphical visibility and gameplay with reported lag. Rendering quality,
  broad gameplay correctness, networking, packaging, sustained performance, and final human approval
  remain unverified. Graphical process/window observation is recorded separately from startup.

Evidence:

- `.studio/runs/lyra-native-bootstrap-efc5fa3a5f57/` — original failed build, preserved.
- `.studio/runs/lyra-commonuser-linux-fix-d6bb17d94586/` — strict native rebuild and repair tests.
- `.studio/evidence/lyra-startup-timeout-reconciliation-2026-11-03.json` — interrupted startup.
- `.studio/runs/lyra-controlled-startup-a180ce322441/` — successful full editor lifecycle check.
- `.studio/evidence/lyra-interactive-editor-2026-11-03.json` — graphical launch record when started.

Only version/platform metadata, hashes, functional categories, and test results were returned to
model context; raw sample source/assets and raw engine diagnostics were not. Local mechanical
repair does not settle the code-versus-content AI-input license boundary below.

## Open the repaired local project

**Historical baseline command:** the exact-inventory launcher below remains unchanged and will
refuse the new hero plugin. For the current extended working copy, use the guarded commands in
[HERO_SANDBOX.md](HERO_SANDBOX.md), including `manage.py gold` for the original menu/modes.

```sh
python3 .studio/launch_lyra.py
```

The guarded launcher requires verified startup, unchanged source hashes, native modules, a
graphical session, no competing editor, and at least **8 GiB** free VRAM. It keeps integration/editor
ownership until normal exit. Do not run it again while an editor is active or interrupt existing
user services to free GPU memory. The first graphical session uses command-line-only offline,
`NoIni`, and file-server-disable settings; settings changes are intentionally not saved.
Confirm the window with the human, then test Play separately. Close the editor normally before
other integration operations. No graphical screenshot or unobserved gameplay is approved here.

## Recommended foundation: Epic Lyra Starter Game

[Lyra documentation](https://dev.epicgames.com/documentation/en-us/unreal-engine/lyra-sample-game-in-unreal-engine)
· [Official free sample](https://www.fab.com/listings/93faede1-4434-47c0-85f1-bf27c0820ad0)
· [Epic learning path](https://dev.epicgames.com/community/learning/paths/Z4/lyra-starter-game)

Lyra provides networked shooter experiences, team deathmatch/control-point modes, weapons, bots,
UI/input/animation examples, a customized Gameplay Ability System (GAS), and modular Game Feature
Plugins. Reuse those systems rather than rebuilding a basic networked shooter stack.

It is a third-person sample, not a finished Paladins clone. First-person presentation, champion
selection, distinct abilities/ultimates, talents/cards/loadouts, balance, progression, matchmaking
operations, and production anti-cheat remain product work. Use original characters, names, maps,
art and audio; genre inspiration does not authorize copying Paladins intellectual property.

## Acquisition and license gate

1. Sign in to Epic/Fab personally and review the actual offered license. Do not send credentials
   in chat. The owner completed authentication and sample acquisition privately in Epic Asset
   Manager; account secrets and acceptance records were not inspected.
2. Select an official Lyra artifact compatible with UE **5.8**. Confirm its actual version, size,
   destination and terms before downloading; do not use an arbitrary public mirror. The local
   sample's 5.8 association and source/content presence are now verified as recorded above.
3. Keep it as a separate project and prove the unchanged sample first. Prefer new game-feature
   plugins/experiences over rewriting Lyra core or merging it into NovanodeLab.
4. Review AI-use rights before giving any sample content to AI tools. The Fab listing currently
   displays **“Allows usage with AI: No”**; Epic's [content agreement](https://www.unrealengine.com/eula/content)
   restricts NoAI content as generative-AI inputs. Clarify the applicable artifact/license rather
   than assuming that “free” means unrestricted AI use or redistribution. The initial research
   preceded acquisition; the later local compile used the downloaded files without returning
   source/assets to a model. The applicable code-versus-content license boundary still needs
   clarification before a source-level AI review. Do not substitute a public mirror to evade it.

[Epic's source announcement](https://forums.unrealengine.com/t/lyra-starter-game-source-code-now-on-github/767395)
locates Lyra code inside `EpicGames/UnrealEngine/Samples/Games/Lyra`; viewing that official source
requires linked, authorized Epic/GitHub accounts. Source alone does not supply all sample content.
[Fab in Unreal](https://dev.epicgames.com/documentation/en-us/unreal-engine/fab-window-in-unreal-engine)
documents the in-editor workflow; do not assume a sample's download flow works on Linux before testing it.

## Useful supporting references

| Resource | Use | Compatibility caveat |
| --- | --- | --- |
| [GASDocumentation](https://github.com/tranek/GASDocumentation) | Abilities, attributes, effects, costs/cooldowns and prediction concepts | README targets UE 5.3; MIT code license; not qualified on 5.8 here |
| [GASShooter](https://github.com/tranek/GASShooter) | Multiplayer FPS/TPS weapon/ability patterns | README targets UE 4.27; MIT code license; a port, not the recommended starting project |

Both repository LICENSE files were checked. Engine and asset terms still require their own review;
neither project was cloned or compiled here. Marketplace purchases are not implicitly authorized.

## First small playable slice

1. Prove an unchanged control-point match with two local clients.
2. Add one original champion/pawn configuration and a primary weapon using the existing stack.
3. Add a movement ability and one combat/utility ability with authoritative effects/cooldowns.
4. Verify damage, death/respawn, UI feedback, replication, and a Linux packaged build.
5. Then consider a second champion and ultimate/loadout systems—not an entire roster first.

Use local multiplayer qualification before deciding on hosted services. EOS accounts, public ports,
production hosting and anti-cheat deployment are separate choices, not automatic setup actions.
