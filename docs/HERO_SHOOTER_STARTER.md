# Paladins-inspired starter — Lyra downloaded; Linux build blocked

Checked 2026-11-03. Keep the existing NovanodeLab intact; it is not a multiplayer shooter framework.
Official Lyra **5.8** is downloaded; its native Linux build failed and the sample has not launched.

## Current verification and diagnosis

- Original: `/home/d/EpicVault/Lyra_5.8/data/Lyra.uproject`. Separate working copy:
  `.studio/lyra/projects/LyraStarterGame/Lyra.uproject`. Source, content, plugins, and config are
  present; the download is approximately **4.9 GiB**. Windows binaries are not Linux binaries.
- The project targets **5.8**; the installed engine is **5.8.4**. Its bundled **Clang 20.1.8 / v26**
  matches [Epic's UE 5.8 Linux toolchain requirements](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-5-8-release-notes).
- One native build failed with exit code **6**. All six compiler errors are unreachable-code
  warnings promoted to errors in the **CommonUser** plugin: four redundant `break` statements
  following returns in `CommonUserBasicPresence.cpp`, and two loop-related diagnostics in
  `CommonSessionSubsystem.cpp`. The loop cases require intended-behavior review; do not assume
  they are harmless or change iteration semantics merely to compile.
- All **818** baseline source/config/descriptor hashes remain unchanged in both copies. No
  compiler checks were relaxed. Neither the project nor CommonUser's descriptor explicitly
  excludes Linux, but that is not a successful Linux build or a support guarantee.
- This identifies a localized build blocker, not six demonstrated gameplay bugs or a general
  game-quality verdict. Runtime gameplay, networking, rendering, packaging, and performance
  remain untested. The repository's **77** regressions are separate from Lyra coverage.

Evidence: `.studio/runs/lyra-native-bootstrap-efc5fa3a5f57/`,
`.studio/evidence/lyra-linux-diagnosis-metadata-2026-11-03.json`, and
`.studio/evidence/lyra-control-flow-metadata-2026-11-03.json`. Only version/platform metadata,
hashes, compiler-warning categories, and functional statement categories were returned to model
context; raw sample source/assets were not. No authoritative public fix for this exact build
was established. Next: license-safe review and a targeted CommonUser source repair in the working
copy, then a bounded rebuild and startup check—not a redownload or blanket warning suppression.

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
