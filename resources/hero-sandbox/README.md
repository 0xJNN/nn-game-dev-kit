# Hero resources: item-by-item trust, not marketplace-by-marketplace trust

Registry: [`catalog.json`](catalog.json). Reviewed 2026-11-04. Binary downloads and native assets
stay in ignored `.studio/`; this repository contains recipes, provenance, and checksum pins only.
No paid tier, login, license acceptance, or external AI upload is automated.

| Source/item | Intended use | Current boundary |
| --- | --- | --- |
| [Quaternius / itch.io: UAL2 Standard](https://quaternius.itch.io/universal-animation-library-2) | Sword swings, combo variants, sword dash on a humanoid rig | CC0; free subset, **not all 130+ advertised clips**. Local 18,735,003-byte ZIP pinned. In-place GLB selected; root-motion variant retained separately. |
| [Poly Pizza: Quaternius Claymore](https://poly.pizza/m/BBhN1O6TOL) | Two-handed sword mesh | CC0 item; local 54,980-byte GLB pinned. [Site ToS](https://poly.pizza/docs/tos) restricts extraction for ML/AI training. Engine-local import only; no mesh/image data is supplied to AI. |
| [Quaternius: Ultimate RPG Pack](https://quaternius.com/packs/ultimaterpg.html) | Dagger and other fantasy props | CC0 page reviewed; selected public Drive FBX route returned HTML and was rejected. No import or alternate mirror. |
| [Kenney: RPG Audio](https://kenney.nl/assets/rpg-audio) | Attack/impact sound layers | CC0 item page, but website also signals `noai`, `noimageai`, `tdm-reservation=1`. Candidate only pending scope clarification. |
| [Kenney: Mini Dungeon](https://kenney.nl/assets/mini-dungeon) | Provisional fantasy characters/weapons | Candidate; exact archive, rig/clip inventory and AI policy need review. |
| [OpenGameArt: Fireball Effect - 2](https://opengameart.org/content/fireball-effect-2) | Possible flipbook input for a future effect | Search metadata says CC0; direct site access returned 403. Artifact unverified, not downloaded. Not a ready-made Niagara spell. |
| [Adobe Mixamo](https://www.mixamo.com/) | Future search for casting/slash/stab animations | Account/terms/per-item selection and retargeting remain human gates; not CC0, not acquired. |
| [Fab / existing Lyra](https://www.fab.com/listings/93faede1-4434-47c0-85f1-bf27c0820ad0) | Existing game foundation | Existing human acquisition only. No blanket clearance for other free Fab packs. Earlier NoAI listing boundary is preserved. |

CC0 credit retained voluntarily: models/animations by **Quaternius**; UAL2 author also credits
**Gonzalo Furnier** for animation collaboration. The acquired UAL2 archive includes `License.txt`
and `README.txt`, both explicitly declaring CC0 1.0. A pin detects changed bytes; it does not prove
authorship or replace the license evidence. “No generative AI was used” describes asset creation;
it is not the same thing as a contractual prohibition on AI input.

## Commands

```sh
python3 -m pipeline.resources validate
python3 -m pipeline.resources list
python3 -m pipeline.resources fetch quaternius-ual2-standard       # preview only
python3 -m pipeline.resources fetch quaternius-ual2-standard --execute
python3 -m pipeline.resources fetch quaternius-claymore-poly-pizza --execute
```

Existing acquisition directories are never overwritten. Reconcile the existing receipt/hash instead
of downloading again. Newly acquired bytes must match the committed checksum pins. Ephemeral CDN
URLs are used in memory, not logged or committed. There is no payment fallback.

## Promotion gates

1. **Candidate:** actual creator/item URL, intended role, free-tier scope and formats.
2. **License-reviewed:** evidence, commercial use/redistribution restrictions, attribution, AI policy.
3. **Acquired:** exact artifact, bounded download, checksum, preserved license; no executable imports.
4. **Machine-imported:** Unreal actually creates the right asset types; report scale, rig, clips,
   root motion, sockets/material dependencies and source identity. A static-prop validator is not
   an animation validator; the existing GLB inspector is deliberately not weakened for these files.
5. **Gameplay-verified:** real attack/montage integration, authority/cooldown/hit rules, network tests.
6. **Human-approved:** viewed/heard at game camera distance, acceptable contacts, readability,
   accessibility and performance. Neither a successful download nor a headless test grants this.

The ZIP guard rejects traversal, symlinks, collisions, excessive expansion and unexpected writes;
it extracts media only, not Python, executables, add-ons or `.blend` files. It is not a sandbox or a
complete hostile-media security validator. Never execute code shipped with an art pack.
