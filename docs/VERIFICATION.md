# Verification record

## Unreal/Linux migration preparation — 2026-11-02 UTC

- 70 Python regression tests passed, including compilation/execution of the exact portable
  `LabState.h` logic with the host C++ compiler. This does not compile Unreal actors or run UHT.
- Ruff static analysis passed. The bounded `unreal-source` contract passed.
- Public OpenRouter metadata confirmed 13 zero-priced text/tool routes at research time;
  North Mini Code, Flint, and Nemotron 3.5 Super VL were among them. Metadata is not inference QA.
- Official HF cards and quant file sizes/revisions/SHA-256 values were checked. Candidate pins
  are in `models.lock.json`; actual deployed quant quality/performance remains unmeasured.
- Legacy Godot regression still passed all 14 checks after migration; this is not Unreal evidence.
- User chose source preparation first. No Unreal editor is installed, no model weights were
  downloaded, and no model inference, provider authentication, or Epic EULA acceptance occurred.

Pending: native Unreal compilation/assets/runtime/rendering, real input/playtesting, Blender→Unreal
import, local model load/tool probes, matched coding benchmarks, and any external release approval.
New run evidence is under `.studio/runs/unreal-source-*/` and `.studio/evidence/python-tests-migration.log`.

## Archived initial Godot verification — 2026-11-02 UTC

Host: Linux x86-64, Python 3.14.8, Godot 4.7.2 stable, Blender 4.5.15 LTS.

| Gate | Observed result |
|---|---|
| Python regression suite | 48 tests passed |
| Ruff 0.14.3 static analysis | Passed |
| Background Blender export + binary asset inspection | Passed; 60 triangles, meter-scale bottom-center bench |
| Bounded lab task | Passed; all 14 named input/collision/movement/save-load checks |
| Clean source-only copy, no project import cache | Asset and lab tasks both passed |
| Linux packaged normal-startup smoke | Passed, including the imported bench |
| Universal macOS cross-export from Linux | Built with local ad-hoc signature; **not native-runtime verified** |
| Graphical gameplay capture | Captured and inspected by the implementing agent; **not human-approved** |
| Native macOS CI | Configured, not run |

Local evidence: `.studio/evidence/verification-summary.json`, `python-tests.log`, `lab.png`,
per-task `.studio/runs/` reports, and `.studio/builds/<platform>/` artifacts/logs.
These are ignored build outputs; rerun the documented commands to regenerate them.

No paid generation/model jobs were submitted by this pipeline. This does not measure or claim
zero cost for the separate coding-agent conversation. No system application installation,
remote creation, push, developer-identity signing, or notarization was performed.

Still required: human playtest/art acceptance, native macOS execution, representative performance
measurements, and a real second project before calling this a production-proven studio template.
