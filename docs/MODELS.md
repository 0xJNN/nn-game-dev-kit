# Model shortlist — checked 2026-11-02

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

## Free OpenRouter candidates

Confirmed in the live public catalog with zero advertised prompt/completion prices and tools:

- **Coding first candidate:** `cohere/north-mini-code:free`.
- **Coding alternative:** `recursive/flint-v1.0:free`.
- **Visual-review candidate:** `nvidia/nemotron-3.5-super-vl:free` (image input advertised).
- **Additional reasoning/review experiments:** `thinkingmachines/inkling:free` and
  `nvidia/nemotron-3-ultra-550b-a55b:free` were listed; not selected as coding defaults without tests.

Run `models refresh-free` to check public metadata again. The filter finds free text/tool routes;
it is **not** a coding ranking. For example, a model can advertise tools while its card advises
against agentic coding. `openrouter/free` selects models dynamically; avoid it for reproducible
benchmarks. A `:free` route may disappear or have no capacity/privacy-compatible providers.

OpenRouter currently documents **20 requests/minute**, and **50 requests/day** below $10 lifetime
credit purchases or **1,000/day** at/above that threshold. These are requests, not completed tasks;
one agent task can consume many. No purchase is required or authorized by this project.
Stop/checkpoint on rate limits, and switch deliberately to an approved local profile. No paid fallback.

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
- Local profile restricts providers to the named localhost server; no automatic cloud fallback.
- Shell/edits/external directories ask for permission; subagents, paid image generation, web
  search, and inherited MCP servers are disabled. Permissions are not an OS/network sandbox.
- Context/outputs are capped; no warming, helper swarm, or giant Unreal cache files in context.
- The 8K cloud output cap is a bounded-worker default, not a quality-optimal benchmark setting.
  Hard reasoning can truncate at that cap; review/increase a task's budget deliberately rather
  than misclassifying truncation as proof that a model cannot code.
- Higher-authority/global configuration can override project settings. Verify the resolved setup.
- OpenCode request usage is **not automatically imported into the studio ledger**. Record receipts
  or add tested instrumentation before claiming per-feature accounting is complete.

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
