# Model shortlist — checked 2026-11-02

Re-reviewed on 2026-11-02: all five immutable file/revision/size/advertised-hash pins match HF
metadata, and 13 free text/tool routes pass the current public-catalog filter. No candidate inference was run.
See [AI_CODING_RESEARCH.md](AI_CODING_RESEARCH.md) for the expanded current architecture/tooling
review, additional candidates, sources, and qualification findings **H1–H7**. Existing pins and
active configuration were not changed by that review.

## Evidence, not a universal ranking

This shortlist uses live OpenRouter metadata, official Hugging Face model cards, and GGUF file
metadata (including exact bytes, revision, and SHA-256). **No candidate has been load-tested or
benchmarked on this workstation by this project yet.** Developer benchmark claims use different
harnesses, thinking budgets, and precisions; they are not an Unreal C++ leaderboard.

The machine has an RTX 3090 / 24 GiB VRAM and approximately 64 GiB RAM. Existing Ollama models,
including Qwen3.8-27B IQ2 variants and Qwen2.5-Coder 14B, were discovered and left unchanged.
Their installed alias/context labels do not establish measured throughput, actual memory use,
function-call reliability, or code quality. No recommendation requires deleting them.

## Local candidates

Sizes below are **decimal GB of weight files**, not total VRAM. KV/recurrent state, compute graphs,
vision encoders, desktop apps, and the editor require additional memory.

| Profile | Pinned candidate | Weights | Intended use |
|---|---|---:|---|
| `qwen38-main` | Qwen3.8-27B UD-Q4_K_M | 16.46 GB | First balanced local-quality candidate; Unreal closed |
| `qwen35-small` | Qwen3.5-9B Q4_K_M | 5.68 GB | Small fixes/scripts while editing, if actual headroom permits |
| `north-code` | North Mini Code 1.0 UD-Q4_K_M | 19.20 GB | Coding-agent specialist experiment; tight VRAM/runtime support gate |
| `nanbeige-experiment` | Nanbeige4.3-33B Q3_K_M | 15.92 GB | New coding-agent challenger; Q3 accuracy/dense-model speed tradeoff |
| `qwen3-coder` | Qwen3-Coder-30B-A3B Instruct Q4_K_M | 18.56 GB | Older coding-specialist baseline, not assumed best in November |

Qwen3.8 is the initial solo-quality candidate because its Q4 file leaves more room than several
larger options. North and Nanbeige are important challengers to benchmark, not confirmed winners.
The existing IQ2 Qwen3.8 is smaller, but aggressive quantization needs an A/B quality test against
Q4 before trusting it for complicated multi-file changes. Do not assume a 256K model label means
256K context is affordable or useful for a local coding agent.

Flint is a strong cloud candidate. The checked `flint-UD-Q4_K_XL.gguf` alone is **25.05 GB**
(~23.33 GiB), practically filling the 3090 before runtime/context overhead. That is not a sensible
full-GPU default. Lower quants/offload may work, but need separate speed/quality tests. Similarly,
Qwen3-Coder-Next and giant DeepSeek/GLM models should not be selected from active parameter counts:
**all expert weights still need storage/residency or explicit offload**.

The 3090 is Ampere. Do not assume native FP4/NVFP4 acceleration from newer GPU recipes. The
initial runtime plan uses GGUF with a reviewed CUDA-capable llama.cpp build. Architecture,
chat-template, reasoning, and function-call support must be tested per model/runtime version.

### Additional research candidates — not installed or added to the CLI lock file

The first shortlist was not exhaustive. Public metadata also confirms Qwen3.8 **GSQ-RCO IQ3_S
(11.77 GB)** and **IQ2_XS (8.42 GB)**, Qwen3.5-4B Q4 (2.74 GB), Devstral Small 2 24B Q4
(14.33 GB), gpt-oss-20b GGUF Q4_K_M (11.62 GB), and GLM-4.7-Flash Q4 (18.31 GB).
These are alternatives to qualify, not proven improvements or valid new `studio.py` profile names.

Newer ternary **Bonsai 2 27B** representations are 5.95/7.21/7.63 GB, but custom/runtime-version
requirements and the publisher's documented tool/cache issues keep them experimental. GSQ-RCO's
same-backbone mixed-precision approach deserves an A/B test before adding a runtime fork.
The inspected NVIDIA Bolt file is **6.18 GB**, despite the repository's `4GB` name; its focus is
device assistants, not demonstrated best repository coding. LiquidAI explicitly advises against
agentic coding for LFM3-1.7B. Do not select a tiny/trending model from tool support alone.
Exact inspected files, metadata and primary references are in the research note and its evidence.

## Shared GPU policy

```sh
python3 studio.py models plan qwen38-main --mode solo
python3 studio.py models plan qwen35-small --mode editor
```

The planner reads current NVIDIA free memory, adds a **3 GiB heuristic runtime allowance** and,
in editor mode, an **8 GiB reserve** for Unreal. These are conservative planning numbers, not
measured peaks. In editor mode that reserve remains extra headroom even if an editor is already
using VRAM. It may reject a load that could fit; it cannot guarantee that an accepted load won't OOM.
No process is stopped, unloaded, or killed to satisfy a plan. Use one inference slot/model at a time.

## Download, serve, and test — explicitly opt in

```sh
python3 studio.py models fetch qwen35-small
python3 studio.py models fetch qwen35-small --execute
python3 studio.py models serve qwen35-small --mode editor
python3 studio.py models serve qwen35-small --mode editor --execute
```

The first command previews the exact immutable HF URL/size/hash. Downloads are opt-in, checked,
and stored under `.studio/models/`, not a global cache.
Reserve disk space for Unreal before downloading large candidates; the model download's disk
guard does not reserve space for a future engine installation.
Serving validates the pinned hash, requires estimated headroom, binds **127.0.0.1:8091**,
uses one slot and **16K context**, and
leaves existing Ollama/other services untouched. Start with text only: these profiles do not
download/load a vision projector or advertise working local screenshot interpretation.

From another terminal, after the server is running:

```sh
python3 studio.py models probe qwen35-small --execute
```

The probe makes two local synthetic requests, checks structured tool arguments and the returned
tool-result round trip, and executes **no generated tool**. It does not benchmark coding quality.
If a runtime cannot parse the model/template, stop and resolve compatibility before giving it
filesystem tools. This project does not silently upgrade your llama.cpp/Ollama installations.
**Qualification caveat (H1):** the current probe is one forced call/result pair, not a full
OpenCode/streaming/automatic/multi-turn test. It does not establish serving model identity or put a
timestamp/run ID in evidence, and failure leaves a previous success report untouched. Accept only
the current invocation's successful result, verify the owned runtime/model/hash, and add freshness
and failure-invalidation regressions before trusting unattended probe reports.

**Small-context caveat (H2):** the 16K local profile has not been tested with full OpenCode schema
overhead and compaction; current V2 documentation describes a minimum 16K reserve alongside
percentage buffers. Verify that interaction on the installed version, not just the synthetic probe.
Retained history, instructions/tools, new input, reasoning/output, and reserve must all fit. Thinking
truncated by the probe's 1K or profile's 4K output limit is not proof of poor coding capability.

## Free OpenRouter candidates

Confirmed in the live public catalog with zero advertised prompt/completion prices and tools:

- **Coding first candidate:** `cohere/north-mini-code:free`.
- **Coding alternative:** `recursive/flint-v1.0:free`.
- **Visual-review candidate:** `nvidia/nemotron-3.5-super-vl:free` (image input advertised).
- **Additional reasoning/review experiments:** `thinkingmachines/inkling:free`,
  `thinkingmachines/inkling-small:free`, `nvidia/nemotron-3.5-lightning:free`, and
  `nvidia/nemotron-3-ultra-550b-a55b:free` were listed; not selected as coding defaults without tests.

Run `models refresh-free` to check public metadata again. The filter finds free text/tool routes;
it is **not** a coding ranking. For example, a model can advertise tools while its card advises
against agentic coding. `openrouter/free` selects models dynamically; avoid it for reproducible
benchmarks. A `:free` route may disappear or have no capacity/privacy-compatible providers.

OpenRouter currently documents **20 requests/minute**, and **50 requests/day** below $10 lifetime
credit purchases or **1,000/day** at/above that threshold. These are requests, not completed tasks;
one agent task can consume many. No purchase is required or authorized by this project.
Stop/checkpoint on rate limits, and switch deliberately to an approved local profile. No paid fallback.
The quota is not reset by selecting another free model. Track retries, compaction, and maintenance
requests too; the studio runner currently has no external OpenCode request limiter or automatic
usage import. Keep warming/background summaries off and start with a small bounded task allowance.

## OpenCode V2 profiles

```sh
python3 studio.py models config --profile free
python3 studio.py models config --profile local --local-model qwen35-small
```

Review `.studio/opencode/free.json` or `local.json`, then **manually copy the chosen profile to
project-root `opencode.json`** only if it does not overwrite your own configuration. Use `/connect`
→ OpenRouter in the UI to supply credentials; never paste keys into chat/config/source. Existing
accounts/global configuration are untouched. Project config reloads automatically; no service
restart is needed. The generated format follows V2 docs, not legacy snippets in some model cards.
Use `/models` to select the intended route for an existing session; a previous session selection
takes precedence over the configured default for new work.

- Free profile restricts providers to OpenRouter, uses explicit `:free` models, and sets provider
  price ceilings to zero. `data_collection: deny` and required-parameter routing fail closed if
  no compatible route exists. Review OpenRouter/account privacy separately before sending IP.
  **This is not a model-ID allowlist or an end-to-end-tested spend/privacy guarantee.** The generated
  draft does not set `provider.zdr`; data-collection filtering is not the same as zero retention.
  Qualify actual request behavior and approve an appropriate retention policy before studio-IP use.
- Local profile restricts providers to the named localhost server; no automatic cloud fallback.
- Shell/edits/external directories ask for permission; subagents, paid image generation, web
  search, and inherited MCP servers are disabled. Permissions are not an OS/network sandbox.
- Context/outputs are capped. No helper swarm or extra warming is configured by these drafts,
  but inherited warming, maintenance agents, plugins, and background compaction need review.
  `watcher.ignore` alone does not keep Unreal caches out of tool reads or model context.
- The 8K cloud output cap is a bounded-worker default, not a quality-optimal benchmark setting.
  Hard reasoning can truncate at that cap; review/increase a task's budget deliberately rather
  than misclassifying truncation as proof that a model cannot code.
- Higher-authority/global configuration can override project settings. Verify the resolved setup.
- OpenCode request usage is **not automatically imported into the studio ledger**. Record receipts
  or add tested instrumentation before claiming per-feature accounting is complete.

Prefer one coding session, a small tool surface, progressive skills/current API references,
targeted repository search, deterministic checks, and a compact handoff. Code Mode/lazy tool
discovery are useful only when the chosen model handles them reliably; adding every MCP server,
a vector database, paid server tools, or another agent framework is not the starting architecture.

## Benchmark before choosing the permanent default

Use the same small approved tasks: repair a portable state test, modify one Unreal actor, diagnose
a real compile failure, and implement one bounded interaction. Measure compile/test success,
tool-call errors, latency, prompt/output tokens, and human correction time. Test actual quantized
weights at the deployed context—not only the model author's BF16 results. Never mark a candidate
"best" from likes, download counts, an uncensored variant name, or one successful tool probe.

Sources: [Qwen3.8](https://huggingface.co/Qwen/Qwen3.8-27B),
[North Mini Code](https://huggingface.co/CohereLabs/North-Mini-Code-1.0),
[Nanbeige4.3](https://huggingface.co/Nanbeige/Nanbeige4.3-33B),
[Flint](https://huggingface.co/RecursiveSI/flint),
[OpenRouter catalog](https://openrouter.ai/api/v1/models),
[rate limits](https://openrouter.ai/docs/api-reference/limits),
[provider routing](https://openrouter.ai/docs/guides/routing/provider-selection),
[OpenCode V2 providers](https://opencode.ai/v2/docs/providers),
[models](https://opencode.ai/v2/docs/models), [policies](https://opencode.ai/v2/docs/policies).
Quant repository revisions/files/hashes: `../models.lock.json`.
