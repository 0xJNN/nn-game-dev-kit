# AI coding architecture and tooling review — 2026-11-02

Scope: the execution roadmap, its implemented Python adapters/tests, current OpenCode V2 docs,
OpenRouter's public catalog/routing docs, official model cards, and public GGUF metadata.
**No candidate-model inference, weight/engine download, account change, or active configuration change occurred.**
Published model scores are author claims, not Novanode measurements. Architecture recommendations
below are proposals unless explicitly identified as existing behavior.
The separate coding-agent conversation is not included in a zero-cost claim or automatically
accounted for by the studio ledger.
This is a human reference, not a file to inject wholesale into every coding prompt: select the
relevant section or use the shorter `MODELS.md` summary within the bounded context budget.

## 1. Decision summary

- Keep **one bounded coding session**, a small tool surface, deterministic tests, and human review.
  Do not add an agent swarm, another orchestration framework, or autonomous retry loop by default.
- With Unreal open, first evaluate the explicit **North Mini Code / Flint `:free` routes**. Use
  local Qwen3.5-9B only after measuring editor headroom and qualifying the actual OpenCode transport.
- With Unreal closed, **Qwen3.8-27B Q4 remains the initial quality baseline**, not a proven winner.
  Compare against the existing IQ2 installation before deciding a new download is worthwhile.
- Add **Qwen3.8 GSQ-RCO mixed-precision GGUFs** to the research queue: their smaller files could
  change the shared-GPU tradeoff. Do not confuse a paper/card's coding score with reliable tool loops.
- Keep **ternary Bonsai 2** experimental: promising compression, but its own known-issues page
  reports malformed calls, cache/history problems, and runtime-specific compatibility requirements.
- Close the qualification/provenance gaps in section 6 before promoting profiles to trusted defaults.
  The 23-step [execution roadmap](EXECUTION_ROADMAP.md) remains the operational order.

## 2. Current evidence and hardware

Read-only host check on 2026-11-02: RTX 3090, **24 GiB VRAM**, approximately **1.16 GiB in use**;
**62.09 GiB RAM**; **73.43 GiB free project-filesystem space**. This is a momentary reading,
not capacity reserved for an editor or model. `UE_ROOT` is unset; native Unreal remains unverified.

Installed version strings: **OpenCode 2.2.5**, **Ollama 0.31.2**, and **llama-server 0.8.0,
commit `8642541`**. Version output does not prove this binary has the needed CUDA kernels,
architecture/template support, or good throughput. No Ollama model was loaded at inspection time;
no service was stopped. Host OS is **Fedora 44**, with host Clang **22.1.8**. Epic's UE 5.8 release
notes specify a Clang **20.1.8** toolchain and reference Ubuntu/Rocky/RHEL configurations: use the
engine's reviewed toolchain, not an assumption that newer host Clang/Fedora is already validated.

The five immutable GGUF pins in `models.lock.json` were rechecked against HF revision metadata:
**all five filenames, byte counts, revisions, and advertised SHA-256 values match**. This does
not verify downloaded contents, because no weights were downloaded in this review.

Evidence snapshots: `.studio/research/2026-11-02-roadmap-review/`, including
`host-readonly.json`, `pin-recheck-summary.json`, `additional-quants-summary.json`, public catalog
snapshots, and model cards/configs. These ignored files need a separate safe retention policy.

## 3. Recommended architecture and modern techniques

```text
Human brief + explicit approvals
  → one small task contract + relevant file/symbol map
  → OpenCode V2, one coding session
      → manually chosen approved OpenRouter :free route OR localhost model
      → targeted search/read + scoped edits + reviewed CLI commands
  → fast regression tests → native Unreal/asset gates
  → human input/visual review → evidence + compact checkpoint
```

The studio runner currently executes/audits deterministic commands. It does **not** automatically
launch OpenCode, enforce OpenCode's request quota, account for its inference, or sandbox its edits.
Providing a task contract as a prompt is useful guidance, not a new enforcement boundary.

| Technique | Appropriate use here | Qualification/caution |
|---|---|---|
| Plan → implement → verify → review | Separate logical phases; one feature/change per bounded session | Separate phases do not require separate agents; human approval remains independent |
| Context engineering / just-in-time retrieval | Small file/symbol map, `glob`/`grep`, targeted reads, actual compiler errors, current API docs | Do not stuff all engine headers, the entire roadmap, or all logs into every prompt |
| Progressive skills | Load only the asset, build, or verification workflow needed | Existing `.cursor/skills` requires the explicit configured source; review trusted skill content |
| Small tool surface / Code Mode | Use OpenCode's built-in tools first; compose/filter independent read-only work in Code Mode when useful | V2 MCP tools default to Code Mode, but MCP remains disabled in generated profiles; small models must demonstrate reliable composition |
| Structured handoffs | Carry goal, relevant files, changes, test evidence, blockers, approvals, next action across sessions | Handoffs and compaction are lossy; preserve exact diffs/errors in files and verify important state |
| Compaction | Start a fresh bounded task before history becomes unwieldy; test compaction recovery | Do not assume 16K local settings work with every V2 compaction default; see H2 |
| Stable prompt prefixes / caching | Stable instructions/tool schemas and one explicit model per task; measure cache usage if exposed | Free endpoints may not cache; caching does not increase daily request quotas or guarantee latency |
| Model routing by task and GPU state | Cloud while editing; small local for bounded work; larger local when editor is closed | Manual switches only initially; preserve a handoff and revalidate model/context/privacy settings |
| Constrained structured tools | Validate argument schemas and allowlisted operations before execution | Valid JSON is not a safe action; test auto selection, tool results, errors, streaming, and repeated turns |
| External evaluation | Existing tests plus native runtime, fresh screenshots, explicit art/functionality rubrics | A model praising its own output is not acceptance; image review is not validated physics |
| Work isolation | Reviewed checkpoints/copies for candidates; one owner of each interactive editor/integration | Worktrees need an appropriate Git checkpoint first; no reset/discard of user work or implicit delegation |
| Repository retrieval upgrades | Consider symbol/LSP or embedding retrieval only if ordinary search measurably misses relevant code | No vector database, embedding service, or extra agent framework is needed to start |

This follows the useful parts of 2025–2026 harness/context research without importing its paid,
multi-agent execution assumptions. Anthropic's March 2026 harness study also documents the cost
of extra evaluators and recommends removing scaffolding that is not measurably useful [S1–S2].

### Quota-conscious OpenCode settings to review, not an activated profile

The following is a **proposed merge fragment**, not a replacement for the existing provider,
price, privacy, and permission rules:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "warming": false,
  "experimental": {"background_compaction": false},
  "agents": {"build": {"steps": 8}}
}
```

V2 documents `steps` as a model-step allowance that resets on new user input. It is **not** a
hard daily provider-request cap: retries, summaries, and other maintenance can add requests.
Warming sends real requests; the documented default schedule can use seven during a 30-minute
idle period. Background summaries can spend requests even when the result is never used [S3–S5].
The generated profiles do not explicitly override inherited warming/background-compaction settings.
Review resolved configuration and account limits, not only the draft JSON.

## 4. Free OpenRouter: current choices and constraints

The public catalog returned **451 model entries**; **13** passed the project's conservative
`:free` + text output + advertised tools + all-advertised-prices-zero filter. That filter is not
a quality ranking and does not establish a privacy-compatible provider is currently serving.

| Route after the `openrouter/` prefix | Advertised context | Evaluation role |
|---|---:|---|
| `cohere/north-mini-code:free` | 256,000 | Prepared first coding specialist; actual requests still untested |
| `recursive/flint-v1.0:free` | 262,144 | Recent coding specialist; compare on the same bounded tasks |
| `nvidia/nemotron-3.5-super-vl:free` | 1,000,000 | Image-review candidate; do not send images to a text-only route |
| `nvidia/nemotron-3.5-lightning:free` | 1,000,000 | Additional agent/tool challenger, not a selected default |
| `thinkingmachines/inkling:free` / `thinkingmachines/inkling-small:free` | 1,048,576 | Additional general reasoning/tool candidates; large local weights are not a 3090 recommendation |

The filter also returned Gemma 4 variants, Xing4.0, Dots3-Note, LFM2.5, and other Nemotron variants.
Tool advertisement alone does not justify using every one as a coding agent. Use the timestamped
catalog snapshot rather than a permanently hardcoded claim about free availability [S6–S7].

Operational rules:

1. Keep explicit model IDs for benchmarks; `openrouter/free` randomly selects an eligible model.
   Record returned model/provider identifiers where available; a cloud slug is not immutable weights.
2. Current documented free limits are **20 requests/minute**, **50/day** below $10 lifetime credit
   purchases, and **1,000/day** at/above that threshold. Confirm the actual account allowance in
   the provider UI; do not read or publish API keys. Changing free model slugs does not create a
   separate daily allowance. No credit purchase is required or approved here.
3. Budget requests as well as tokens. For example, a 50-request allowance minus 10 held in reserve
   leaves 40; a task consuming 8 requests would allow only five such tasks, not 50 agent tasks.
   This is planning arithmetic, not measured throughput or a built-in limiter.
4. Preserve explicit free IDs, zero-price ceilings, and `require_parameters`. Test outgoing request
   bodies with a credential-free mock/approved redacted observation before claiming end-to-end enforcement.
   The profile's provider restriction is **not an allowlist of only its three declared model IDs**.
5. `data_collection: deny` is **not synonymous with zero retention**. ZDR has its own
   `provider.zdr` filter, and account/provider policies must be reviewed separately. Require approved
   policy for studio IP; if no suitable free route exists, stay local or use non-sensitive examples.
   Never relax privacy solely to obtain capacity. Generated profiles do not currently set `zdr`.
6. Model-level `tools` support does not prove every endpoint supports named `tool_choice`, reasoning,
   structured outputs, or all OpenCode parameters. Let incompatible routes fail rather than dropping protections.
7. Keep web/search/advisor/subagent server tools off by default. Their availability, backend data
   flow, inner model calls, charges, and API compatibility need separate review; an outer `:free`
   model and a local subagent deny do not prove every server-side tool is free or authorized.

OpenRouter documents sticky routing and `session_id` as caching aids. Observe what the native
OpenCode transport actually sends before adding integration code; do not hardcode one shared
session ID, assume every free endpoint caches, or weaken privacy/price constraints for cache hits [S8].

## 5. RTX 3090: model architectures, quantization, and deployment

### Keep the existing pins as the first reproducible baseline

The pinned candidates remain Qwen3.8-27B Q4 (16.46 GB), Qwen3.5-9B Q4 (5.68 GB), North Mini
Code Q4 (19.20 GB), Nanbeige4.3-33B Q3 (15.92 GB), and older Qwen3-Coder-30B-A3B Q4
(18.56 GB). These are **file sizes**, not total GPU allocations; see [MODELS.md](MODELS.md).

- **Qwen3.8-27B / Qwen3.5-9B:** configs show dense hybrid models with three linear-attention
  layers for each full-attention layer. Recurrent state and the remaining KV cache still cost memory;
  generic full-attention estimates are not exact, and 75% linear attention does not mean 75% less VRAM.
- **North / Flint:** sparse MoE can reduce active compute, not resident weight requirements.
  North is 30B-A3B; Flint is approximately 39.8B total / 2.5B active. Flint's checked Q4 file is
  25.05 GB before runtime memory, so cloud is the initial route; lower quants/offload are separate experiments.
- **Nanbeige4.3-33B:** dense Llama-style architecture, strong author-reported agentic results,
  but a Q3 deployment on a 3090 is not the author's full-precision benchmark or long-output configuration.
- Huge Flash/Next/GLM/DeepSeek models do not become 24 GiB full-GPU models merely because their
  active parameter count is small. Host-RAM/CPU offload is possible in some configurations, but
  must be measured and should not silently replace the full-GPU baseline.

### Newly checked alternatives — research only, not new CLI profiles

None of these was added to `models.lock.json`, downloaded, or benchmarked. Their metadata,
including available hashes/revisions, is retained in `additional-quants-summary.json`.

| Candidate / exact inspected representation | Weight bytes expressed as GB | Why investigate / why not promote yet |
|---|---:|---|
| Qwen3.8 GSQ-RCO IQ3_S | 11.77 | Per-tensor precision allocation under a size budget; promising same-backbone alternative to Q4; agent-loop quality still unknown |
| Qwen3.8 GSQ-RCO IQ2_XS | 8.42 | More editor headroom, but more aggressive compression; not equivalent to the already installed IQ2 variant |
| Ternary Bonsai 2 27B PTQ1_0 / PQ2_0 / Q2_0 | 5.95 / 7.21 / 7.63 | New ternary/rotated representation; fork/version requirements and published tool/cache issues make this experimental |
| NVIDIA Nemotron 3.5 Bolt E4B Q4_K_M | **6.18** | Small assistant/tool-use candidate, not demonstrated best for repository coding; the inspected file is not 4 GB despite the repository's `4GB` name; OpenMDW-1.1 license review |
| Qwen3.5-4B Q4_K_M | 2.74 | Lower-memory small-task candidate if 9B competes with editor peaks; not an automatic code-quality upgrade |
| Devstral Small 2 24B Q4_K_M | 14.33 | Older Apache-2.0 agentic-coding baseline omitted from the first shortlist; qualify its Mistral template/runtime |
| gpt-oss-20b GGUF Q4_K_M | 11.62 | Older Apache-2.0 tool/reasoning baseline; correct Harmony transport is essential |
| GLM-4.7-Flash Q4_K_M | 18.31 | Older MIT-licensed MoE baseline; adds less headroom than the smaller alternatives, and preserved thinking is model-specific |

**GSQ/RCO:** the release describes optimized per-tensor scalar quantization plus precision allocation
under an exact size budget. Its advertised “task-lossless” result concerns specific evaluated tasks,
not guaranteed Unreal edits, tool reliability, or every workload. The card says the files use standard
GGUF; verify the deployed runtime and compare actual long-context tool traces [S9].

**Ternary/Bonsai:** PTQ1_0/PQ2_0 require Prism's runtime fork; the publisher says Q2_0 needs
mainline b11556 or a compatible later implementation. Its warning is unusually important: older
stock builds can load that file yet produce incorrect output. Known issues include malformed tool
calls, reasoning/history cache misses, long reasoning, and special sampling/runtime requirements.
Do not extrapolate the card's 4090/A100 results to this 3090, run its installer scripts, or overwrite
the installed runtime. A separate reviewed runtime and qualification task would be required [S10].

**Very small does not mean a better coder:** LiquidAI's current LFM3-1.7B card explicitly says
it is **not recommended for agentic coding or complex multi-step reasoning**. Bolt focuses on
device/voice assistants. Newly uploaded 3D/coder fine-tunes and “uncensored” labels are not evidence
of robust C++ editing. Keep these out of permanent defaults until tested [S11–S12].

### Deployment/tuning order

1. Keep one reviewed localhost runtime and one model/slot. llama.cpp is the prepared GGUF path;
   Ollama remains a convenient existing-model baseline, not something to replace automatically.
   vLLM/SGLang are alternatives only when a demonstrated architecture/throughput need justifies them.
   If a proxy is configured, verify loopback bypass for both the CLI and background service;
   a localhost URL alone does not establish private network behavior. Do not dump environment
   variables or proxy URLs, which may contain credentials. Review service-environment changes
   with the owner rather than restarting an existing service to apply them [S5].
2. Verify CUDA offload, exact model hash, architecture, chat template, reasoning behavior, and
   tool parsing on the actual build. `--jinja` enables the mechanism, not guaranteed model skill.
3. Measure full memory at a bounded context with the actual OpenCode instructions/tool schemas,
   not only a tiny prompt. Context must hold input, schemas/history, output/reasoning, and reserve.
4. Retain the current single-slot 16K serving baseline only if H2's OpenCode test passes; a reviewed
   8K/16K/32K ladder is an experiment, not a new preset. Recheck VRAM before each approved load.
5. The prepared command uses Flash Attention and Q8 K/V cache. Compatibility is architecture/build
   specific; llama.cpp requires FA for quantized V cache and warns aggressive Q4 KV can impair tools.
   Do not trade tool correctness for a larger advertised context without an A/B test [S13].
6. Only after correctness, compare MTP, draft-model/DFlash, or n-gram speculation where supported.
   Record acceptance rate, prefill/decode speed, actual task latency, and added memory. A second
   draft model may worsen shared-GPU headroom. No speculative decoding is configured by this project.
7. The 3090 is Ampere: do not infer native FP4/NVFP4 speed from Blackwell recipes. Packed-weight
   storage, kernel support, and native tensor arithmetic are different capabilities.

## 6. Audit findings and required qualification gates

These are **open implementation/qualification findings**, not fixes implemented by this documentation review.

| ID | Finding / source | Required action and roadmap position |
|---|---|---|
| H1 | `pipeline/models.py::probe` checks one forced call then one result, not automatic selection, streaming, multi-tool turns, errors, or OpenCode itself. An offline mock confirmed an unrelated response model is accepted and a failed subsequent probe leaves the old success file; reports lack timestamp/run ID | Before step 14 acceptance: use only the current command's successful outcome, verify owned server/model/hash and report freshness; add provenance/failure invalidation regressions and a full transport matrix before trusting unattended results |
| H2 | Local profile uses 16K context, 3K retained history, 4K output, and a percentage compaction buffer. Current V2 docs also describe a minimum 16K reserve; its interaction with a 16K window has not been tested. Probe output is only 1K; thinking models may truncate | Before local profile promotion: measure fixed schema/input overhead, streaming and compaction at the real limit; qualify a supported reserve/context/output configuration. Do not call a truncated response a coding-quality failure |
| H3 | Profile tests assert dictionaries, not actual OpenCode/provider request enforcement. Provider restriction is not a model allowlist; `data_collection: deny` is not ZDR. Warming/background settings are omitted and may be inherited | Step 11: inspect resolved configuration and a credential-free mock/approved redacted request; validate price/privacy routing and intended model; review inherited plugins/maintenance before studio-IP use |
| H4 | No automatic OpenCode request counter or usage import. Runner attempt/USD fields do not govern external model turns; summary/retry/warming calls add usage | Steps 11/16: set a small task allowance, keep warming/background summaries off, track requests manually, then add tested instrumentation if needed |
| H5 | `pipeline/unreal.py::run` labels any timeout/non-completion “failed”; package acceptance checks a launcher exists, not a source/build identity manifest | Steps 05/09: inspect logs/process state after timeout and reconcile before retry; record revision/build identity. Add timeout/provenance hardening before unattended native CI |
| H6 | `prepare_project.py` returns immediately for an already marked material/map; changing generator source does not update those assets automatically | Steps 06/12: use a reviewed versioned regeneration/migration plan for recipe changes; never delete existing content or claim it refreshed merely because `prepare` succeeded |
| H7 | `watcher.ignore` is a watcher setting, not a context/security exclusion. Read-deny rules do not sandbox shell/search/plugins; project policy can be overridden by higher authority | Step 11 and every tool grant: scope searches, inspect inherited trust, approve narrow commands, keep credentials out of context, and use actual isolation for untrusted execution |

The H1 reproduction used mocked completions only: `probe-audit-reproduction.json`. It is not a
model benchmark. Preserve these cases as regression tests in the later authorized hardening task;
do not alter a currently executing task/runner/fixture to make a run pass.

For model selection, use fresh private studio tasks plus independent tests and human review,
not one public leaderboard percentage. OpenAI's February 2026 audit documents both flawed tests
and contamination in SWE-bench Verified; even SWE-bench Pro/Terminal-Bench results need the exact
benchmark version, harness, inference budget, precision, and scoring method recorded [S14].

## 7. What changes now versus later

**Now:** documentation corrections, public-metadata verification, read-only host inspection,
offline probe-audit reproduction, source validation, and regression checks. Existing model pins,
provider configuration, tool installations, and staged user work stay untouched.

**Before first cloud activation (step 11):** qualify resolved settings/privacy/request accounting
and one short tool-using task. **Before local promotion (step 14):** qualify runtime identity,
streaming/automatic/multi-turn tools and actual small-context compaction. **Before default selection
(steps 15–16):** compare the same bounded coding tasks and record failures/review time.

The next operational step is still **storage/toolchain readiness → authorized Unreal setup**.
New quantization research is not a reason to download every candidate or postpone native verification.

## Primary sources

All checked on **2026-11-02**; publication dates differ. Official docs describe supported
behavior, publisher cards report claims, and the local evidence records only what was actually checked.

- **S1 — Harness research:** [Anthropic, March 24, 2026](https://www.anthropic.com/research/harness-design-long-running-apps);
  [earlier bounded-session work](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents).
- **S2 — Progressive tool use:** [Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp).
- **S3 — OpenCode V2 core:** [agents/steps](https://opencode.ai/v2/docs/agents), [skills](https://opencode.ai/v2/docs/skills),
  [tools/Code Mode](https://opencode.ai/v2/docs/tools), [MCP](https://opencode.ai/v2/docs/mcp-servers).
- **S4 — Context:** [OpenCode compaction](https://opencode.ai/v2/docs/compaction).
- **S5 — Trust and overhead:** [warming](https://opencode.ai/v2/docs/warming),
  [permissions](https://opencode.ai/v2/docs/permissions), [policies/version requirements](https://opencode.ai/v2/docs/policies),
  [network/proxy behavior](https://opencode.ai/v2/docs/network).
- **S6 — Live catalog:** [OpenRouter models API](https://openrouter.ai/api/v1/models),
  [limits](https://openrouter.ai/docs/api_reference/limits), [free router](https://openrouter.ai/docs/guides/routing/routers/free-router).
- **S7 — Route/privacy:** [provider selection](https://openrouter.ai/docs/guides/routing/provider-selection).
- **S8 — Caching:** [prompt caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching),
  [latency/performance](https://openrouter.ai/docs/guides/best-practices/latency-and-performance).
- **S9 — Mixed precision:** [GSQ-RCO Qwen release](https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF),
  [GSQ v2, May 15, 2026](https://arxiv.org/abs/2604.18556v2),
  [RCO v3, September 27, 2026](https://arxiv.org/abs/2605.00649v3); paper abstracts checked as well as the card.
- **S10 — Ternary:** [Bonsai 2 release](https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf),
  [publisher's known issues](https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf/blob/main/KNOWN_ISSUES.md).
- **S11 — Small models:** [LFM3-1.7B](https://huggingface.co/LiquidAI/LFM3-1.7B),
  [Nemotron Bolt](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB).
- **S12 — Coding backbones/baselines:** [Qwen3.8](https://huggingface.co/Qwen/Qwen3.8-27B),
  [Qwen3.5](https://huggingface.co/Qwen/Qwen3.5-9B), [North](https://huggingface.co/CohereLabs/North-Mini-Code-1.0),
  [Flint](https://huggingface.co/RecursiveSI/flint), [Nanbeige](https://huggingface.co/Nanbeige/Nanbeige4.3-33B),
  [Devstral](https://huggingface.co/mistralai/Devstral-Small-2-24B-Instruct-2512),
  [gpt-oss](https://huggingface.co/openai/gpt-oss-20b), [GLM-4.7-Flash](https://huggingface.co/zai-org/GLM-4.7-Flash).
- **S13 — Runtime:** [llama.cpp function calling and KV warning](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md),
  [server reference](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).
- **S14 — Benchmark limits:** [OpenAI, February 23, 2026](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/).
- **S15 — Engine toolchain:** [UE 5.8 release notes](https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-5-8-release-notes).
