# Active brief — Novanode Unreal Lab 01 / Linux

The previous Godot pilot is retained as a legacy reference. This phase prepares Unreal source
first; native compilation and visual acceptance require an installed editor.

## Goal

Prove a reusable, inexpensive production path with a small interactive 3D lab, not a large game.
Target Linux x86-64 with a first-person camera and contextual E/WASD/mouse controls. macOS is deferred.

## Representative journey

Launch → sealed airlock → open door → explore instrument bays → enable power → run an analytical
reference. Contextual interaction uses an actual camera ray. The room, surface material, lighting,
and HUD should read as one coherent research environment, not isolated demo cubes.

## Acceptance

- The input path works, including a negative test for missing prerequisites.
- Door collision changes in world space and returns when the door closes.
- Movement/input and game feel are verified in the native application, not inferred from source.
- The shared Blender asset route must be imported/tested in Unreal before claiming engine integration.
- The analytical period for L=1 m, g=9.81 m/s² matches 2.00606668 s within 0.00001 s.
- The normal packaged startup is tested, not just editor fixtures.
- Fresh graphical evidence and human playtesting remain required for visual/feel acceptance.
- Current automated source/portable-state checks do not satisfy the native or visual gates above.

## Non-goals

No multiplayer, custom physics engine, live LLM gameplay, generative spending, production save
migration, or validated laboratory simulation in this phase. High-fidelity art follows a native
lighting/layout review; source primitives and Lumen settings alone do not establish that quality.

## Owners

- Product/experience engineer: scope, feel, and acceptance.
- Runtime/systems engineer: behavior, reference formula, tests, and performance.
- Technical-art/pipeline engineer: assets, automation, builds, and evidence.
