# Paladins-inspired starter — recommendation, not an installed game

Checked 2026-11-03. Keep the existing NovanodeLab intact; it is not a multiplayer shooter framework.
The installed UE 5.8.4 editor is available, but no hero-shooter sample was downloaded or launched.

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
   in chat. The official listing was opened in the owner's browser; entitlement is not confirmed.
2. Select an official Lyra artifact compatible with UE **5.8**. Confirm its actual version, size,
   destination and terms before downloading; do not use an arbitrary public mirror.
3. Keep it as a separate project and prove the unchanged sample first. Prefer new game-feature
   plugins/experiences over rewriting Lyra core or merging it into NovanodeLab.
4. Review AI-use rights before giving any sample content to AI tools. The Fab listing currently
   displays **“Allows usage with AI: No”**; Epic's [content agreement](https://www.unrealengine.com/eula/content)
   restricts NoAI content as generative-AI inputs. Clarify the applicable artifact/license rather
   than assuming that “free” means unrestricted AI use or redistribution. No such content was
   downloaded or provided to a model during this research.

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
