# Backfill Sources

Sources for the agent notes and tags. Phase 4 did the initial backfill;
Phase 5 (revision 2, 2026-11-16) applied the recommended bar, removed
`current` from serving variants, added local-only models to
`top_on_device`, added serving variants to `top_fast`, and rebuilt this
log to the per-set format with comparative reasons. Revision 3
(2026-11-17) narrowed `top_value` to low- and mid-priced models only:
removed Claude 5.5 Sonnet (top-price) and Qwen 3.8 Flash (no AA source).

## Data sources

- **Artificial Analysis** (`https://artificialanalysis.ai/models/<slug>`):
  intelligence index, cost per task, output speed, time to first token.
  Figures are from the Max effort level unless noted.  Fetched 2026-11-16.
  Figures for models added on 2026-11-19 (Gemini 4 Neon, Gemini 4 Carbon,
  Gemini 4 Hydrogen, Qwen 4 Max, Inkling 2 Small) were fetched 2026-11-19,
  with the effort level shown in each row.
- **models.dev API** (`https://models.dev/api.json`): pricing, release
  dates, context lengths, output limits, open-weight status.
  Fetched 2026-11-13.
- **Lab documentation**: model cards, blog posts and API docs from each
  lab.  Used for lineup ordering, parameter counts and architecture
  details (dense vs. MoE, active parameters).
- **Provider documentation**: data retention policies, rate limit tiers,
  routing behaviour and regional constraints for each provider.

## Selection criteria

A model was selected when it met either condition:

1. `featured_rank` is set (13 models), or
2. at least one non-deprecated provider entry has a models.dev
   `release_date` within 12 months of 2026-11-15 (124 additional models),
   or
3. it is local-only (all non-deprecated entries on Ollama or Docker Model
   Runner) and the lab's model card gives a release date within 12 months.

137 models were annotated in Phase 4.  Phase 5 added notes and tags to 2
local-only models (Gemma 4 4B, Gemma 4 2B).

## Current tag assignments

Within each lab, `current` marks the latest model at each price level.
Serving variants (GLM 5.3 Fast, Kimi K3 Fast, MiMo-V2.6-Pro-UltraSpeed)
are never `current`; they carry a `Same weights:` line instead.

| Lab | Current models |
|-----|----------------|
| OpenAI (gpt) | GPT-6.1 Sol Pro, GPT-6.1 Sol, GPT-6.1 Terra Pro, GPT-6.1 Terra, GPT-6 Astra, GPT-6 Luna Pro, GPT-6 Luna |
| Anthropic (claude) | Claude Fable 5.2, Claude Opus 5.5, Claude 5.5 Sonnet, Claude 5.5 Haiku |
| Google (gemini) | Gemini 4 Argon, Gemini 3.8 Flash, Gemini 3.5 Flash Lite |
| Google (gemma) | Gemma 4 31B, Gemma 4 27B, Gemma 4 4B, Gemma 4 2B |
| NVIDIA (nemotron) | Nemotron 3.5 Super VL, Nemotron 3.5 Lightning, Nemotron 3 Ultra |
| Meta (muse) | Muse Wonder 1.0, Muse Spark Open, Muse Spark 1.2, Muse Ember, Muse Glimmer 30B |
| Mistral (mistral) | Mistral Large 4, Mistral Medium 3.5, Mistral Small 4, Ministral 3 14B/8B/3B 2512 |
| DeepSeek (deepseek) | DeepSeek V4.1 Flash 1017, DeepSeek V4 Pro 0813 |
| xAI (grok) | Grok 4.7 |
| Alibaba (qwen) | Qwen 3.8 Max 0902, Qwen 3.8 Max Prime, Qwen 3.8 2.4T A95B, Qwen 3.8 Flash, Qwen 3.8 Omni Flash, Qwen 3.8 27B, Qwen 3.7 Plus, Qwen 3.6 35B A3B, Qwen 3.5 397B, Qwen 3.5 122B, Qwen 3.5 9B |
| ZhipuAI (glm) | GLM 5.3, GLM 5.3 Prime, GLM 5.3 Flash, GLM 5.3 FlashX, GLM 5.3 FlashX Legal |
| Moonshot (kimi) | Kimi K3.1 Pro, Kimi K3 |
| Tencent (hunyuan) | Hunyuan Hy4 |
| MiniMax (minimax) | Minimax M3.1 Flash |
| StepFun (stepfun) | StepFun Step 5 Preview, StepFun Step 3.7 Flash |
| Xiaomi (mimo) | MiMo-V2.6-Pro, MiMo-V2.6-Flash |
| Thinking Machines (thinking_machines) | Inkling, Inkling Small |
| Sakana (sakana) | Fugu Max, Fugu Ultra v2 |
| Liquid (liquid) | LFM 2.5 24B A2B |
| Reflection (reflection) | Beam 1.0 |
| Elorian (elorian) | Glimpse |
| Ling (ling) | Ling 3.1 Flash |
| PrismML (prismml) | Ternary Bonsai 2 9B |
| Ricursive (ricursive) | Ripple 65B Preview |
| Nex (nex) | Nex N2.6 |
| Motif (motif) | Motif 3 |
| KT (kt) | Mi:dm K 3.0 Pro |

Serving variants (not `current`): GLM 5.3 Fast, Kimi K3 Fast,
MiMo-V2.6-Pro-UltraSpeed.

## Set membership

### recommended (12/20)

Models recommended as candidates for new agents.  Each is `current` and
its AA quality is high for its cost compared with models across all labs
at a similar cost.

| Model | AA Index | AA $/task | AA tok/s | AA URL | Reason |
|-------|----------|-----------|----------|--------|--------|
| GPT-6.1 Sol | 55 | $1.27 | 49 | [link](https://artificialanalysis.ai/models/gpt-6-1-sol) | Index 55 at $1.27/task; next closest quality at similar cost is Terra (51 at $0.96) |
| GPT-6.1 Terra | 51 | $0.96 | 72 | [link](https://artificialanalysis.ai/models/gpt-6-1-terra) | Index 51 at $0.96/task; next best at sub-$1 cost is Haiku (36 at $0.41) |
| GPT-6 Astra | 57 | $6.24 | 42 | [link](https://artificialanalysis.ai/models/gpt-6-astra) | Index 57 at $6.24/task; below Gemini 4 Neon (61 at $6.44) at a similar cost, and below Opus/Fable |
| GPT-6 Luna | 28 | $0.15 | 104 | [link](https://artificialanalysis.ai/models/gpt-6-luna) | Index 28 at $0.15/task; comparable to Ember (36 at $0.14) but different ecosystem |
| Claude Fable 5.2 | 65 | $26.54 | 110 | [link](https://artificialanalysis.ai/models/claude-fable-5-2) | Index 65; highest on AA, no model at any cost scores higher |
| Claude Opus 5.5 | 59 | $10.04 | 117 | [link](https://artificialanalysis.ai/models/claude-opus-5-5) | Index 59 at $10.04/task; below Fable (65) and Gemini 4 Neon (61) |
| Claude 5.5 Sonnet | 55 | $10.02 | 151 | [link](https://artificialanalysis.ai/models/claude-sonnet-5-5) | Index 55 at $10.02/task; matches Sol (55) at Sonnet-tier pricing |
| Claude 5.5 Haiku | 36 | $0.41 | 257 | [link](https://artificialanalysis.ai/models/claude-haiku-5-5) | Index 36 at $0.41/task; best quality at budget tier, above Luna (28) and matching Ember (36 at $0.14) |
| Gemini 4 Neon | 61 | $6.44 | 110 | [link](https://artificialanalysis.ai/models/gemini-4-neon) | Index 61 at $6.44/task (Xhigh); above GPT-6 Astra (57 at $6.24) at a similar cost, and above Claude Opus 5.5 (59 at $10.04) at a lower cost |
| Gemini 4 Argon | 50 | $4.97 | 66 | [link](https://artificialanalysis.ai/models/gemini-4-argon) | Index 50 at $4.97/task; below Astra (57 at $6.24) and Gemini 4 Neon (61 at $6.44), but cheaper than both |
| DeepSeek V4.1 Flash 1017 | 33 | $0.60 | 174 | [link](https://artificialanalysis.ai/models/deepseek-v4-1-flash-1017) | Index 33 at $0.60/task; best open-weight flash, above Minimax (29 at $0.49) and GLM Flash (28 at $0.58) |
| Kimi K3.1 Pro | 46 | $3.68 | 30 | [link](https://artificialanalysis.ai/models/kimi-k3-1-pro) | Index 46 at $3.68/task; below Argon (50 at $4.97) in quality but 26% cheaper |

Changes on 2026-11-19 (model sweep, Gemini 4 Neon):
- Added Gemini 4 Neon: AA index 61 at $6.44/task (Xhigh), 110 tok/s. Highest index among models within 1.5x of its cost per task (GPT-6 Astra 57 at $6.24, Gemini 4 Carbon 60 at $7.76, Gemini 4 Argon 50 at $4.97).
- Candidate removals, not applied (a human decides): Claude Opus 5.5 (59 at $10.04/task) and Claude 5.5 Sonnet (55 at $10.02/task). Gemini 4 Neon beats both on index and cost.

Removals in Phase 5:
- Gemini 3.5 Flash Lite: AA index 12 at $0.69/task; GPT-6 Luna gets index 28 at $0.15/task -- beaten on both quality and cost.
- Mistral Large 4: AA index 26 at $2.06/task; GPT-6.1 Terra gets index 51 at $0.96/task -- beaten on both quality and cost.
- Gemini 3.8 Flash: AA index 31 at $7.77/task; Gemini 4 Argon gets index 50 at $4.97/task and GPT-6 Astra gets index 57 at $6.24/task -- beaten on both quality and cost by two models.
- Kimi K3: Deprecated on AA; index 17 (low effort only), blended $2.31/M; Kimi K3.1 Pro (index 46 at $3.68/task) supersedes it as the recommended Moonshot model.
- Gemma 4 31B: AA index 4 (reasoning), non-reasoning has no index; no cost per task on AA. Quality not demonstrably high for cost on AA data.
- GLM 5.3: AA index 32 at $5.01/task; Gemini 4 Argon gets index 50 at $4.97/task -- beaten on both quality and cost.
- DeepSeek V4 Pro 0813: AA index 23 at $1.77/task; GPT-6.1 Terra gets index 51 at $0.96/task -- beaten on both quality and cost.
- Qwen 3.8 Max 0902: AA index 34 at $10.02/task; Claude 5.5 Sonnet gets index 55 at $10.02/task -- beaten on quality at the same cost.

### top_value (8/14)

Best quality for cost, at a low or mid price. A top-price model is never
in this set, however good its value. (Revised 2026-11-17.)

| Model | AA Index | AA $/task | AA tok/s | AA URL | Reason |
|-------|----------|-----------|----------|--------|--------|
| GPT-6.1 Terra | 51 | $0.96 | 72 | [link](https://artificialanalysis.ai/models/gpt-6-1-terra) | Index 51 at $0.96/task; highest index below $1/task, mid-price value pick |
| GPT-6 Luna | 28 | $0.15 | 104 | [link](https://artificialanalysis.ai/models/gpt-6-luna) | Index 28 at $0.15/task; near Ember (36 at $0.14) with $0.01 gap, different ecosystem |
| Claude 5.5 Haiku | 36 | $0.41 | 257 | [link](https://artificialanalysis.ai/models/claude-haiku-5-5) | Index 36 at $0.41/task; matches Ember (36) with wider provider ecosystem |
| Muse Ember | 36 | $0.14 | 442 | [link](https://artificialanalysis.ai/models/muse-ember) | Index 36 at $0.14/task; best value across all models by cost-per-task |
| DeepSeek V4.1 Flash 1017 | 33 | $0.60 | 174 | [link](https://artificialanalysis.ai/models/deepseek-v4-1-flash-1017) | Index 33 at $0.60/task; best open-weight flash value, above GLM 5.3 Flash (28 at $0.58) |
| GLM 5.3 Flash | 28 | $0.58 | 54 | [link](https://artificialanalysis.ai/models/glm-5-3-flash) | Index 28 at $0.10/M blended; ultra-budget per token ($0.58/task due to verbose reasoning) |
| Minimax M3.1 Flash | 29 | $0.49 | 142 | [link](https://artificialanalysis.ai/models/minimax-m3-1-flash) | Index 29 at $0.49/task and $0.10/M blended; open-weight at Ember-tier blended cost |
| MiMo-V2.6-Flash | 27 | $0.13 | 43 | [link](https://artificialanalysis.ai/models/mimo-v2-6-flash) | Index 27 at $0.13/task; cheapest by cost-per-task, below Ember ($0.14) |

Removals in revision 3 (2026-11-17):
- Claude 5.5 Sonnet: AA index 55 at $10.02/task; top-price, excluded by the revised rule.
- Qwen 3.8 Flash: no AA page; no independent source for a value comparison.

Removals in Phase 5:
- Gemini 3.5 Flash Lite: AA index 12 at $0.69/task; Luna (28 at $0.15), Ember (36 at $0.14) and MiMo-Flash (27 at $0.13) all beat it on both index and cost.
- Gemini 3.8 Flash: AA index 31 at $7.77/task; Haiku (36 at $0.41) beats it on both index and cost.
- Ling 3.1 Flash: AA index 30 at $3.19/task (blended $0.19/M); Haiku (36 at $0.41) beats it on both index and cost.

### top_fast (8/14)

Fastest models for latency-sensitive work, by output speed and time to
first token, or a faster hosted version of a strong model.

| Model | AA Index | AA $/task | AA tok/s | AA TTFT | AA URL | Reason |
|-------|----------|-----------|----------|---------|--------|--------|
| GPT-6 Luna | 28 | $0.15 | 104 | 71.94s | [link](https://artificialanalysis.ai/models/gpt-6-luna) | 104 tok/s at index 28; fastest OpenAI model, above Gemini 3.8 Flash (116 tok/s) in quality-to-speed |
| Claude 5.5 Haiku | 36 | $0.41 | 257 | 182.37s | [link](https://artificialanalysis.ai/models/claude-haiku-5-5) | 257 tok/s; fastest Anthropic model, 2.5x Luna's speed despite higher TTFT |
| Gemini 3.8 Flash | 31 | $7.77 | 116 | 19.79s | [link](https://artificialanalysis.ai/models/gemini-3-8-flash) | 116 tok/s, 19.79s TTFT; lowest TTFT among mid-index models, below Lite (4.82s) |
| Gemini 3.5 Flash Lite | 12 | $0.69 | 312 | 4.82s | [link](https://artificialanalysis.ai/models/gemini-3-5-flash-lite) | 312 tok/s, 4.82s TTFT; second fastest overall after Ember (442 tok/s), lowest TTFT in set |
| Nemotron 3.5 Lightning | 6 | $0.31 | 271 | 9.78s | [link](https://artificialanalysis.ai/models/nemotron-3-5-lightning) | 271 tok/s, 9.78s TTFT; third fastest, 3B active MoE optimised for speed |
| Muse Ember | 36 | $0.14 | 442 | 4.91s | [link](https://artificialanalysis.ai/models/muse-ember) | 442 tok/s, 4.91s TTFT; fastest model on AA by output speed, 1.4x faster than Lite (312) |
| GLM 5.3 Fast | -- | -- | -- | -- | Same weights as [GLM 5.3](https://artificialanalysis.ai/models/glm-5-3) | Not the fastest overall, but the faster way to run GLM 5.3 (top_open); speed-optimised Fireworks serving |
| MiMo-V2.6-Pro-UltraSpeed | -- | -- | -- | -- | Same weights as [MiMo-V2.6-Pro](https://artificialanalysis.ai/models/mimo-v2-6-pro) | Not the fastest overall, but the faster way to run MiMo-V2.6-Pro (top_open); speed-optimised OpenRouter serving |

Additions in Phase 5: GLM 5.3 Fast and MiMo-V2.6-Pro-UltraSpeed as
serving variants whose standard models are in `top_open`.

### top_on_device (13/14)

Models that run on consumer laptops or phones.  Selected when the lab's
model card gives a release date within 12 months (after 2025-11-16).

| Model | Size | AA Index | AA $/task | AA tok/s | AA URL | Reason |
|-------|------|----------|-----------|----------|--------|--------|
| Nemotron 3.5 Lightning | 30B MoE, 3B active | 6 | $0.31 | 271 | [link](https://artificialanalysis.ai/models/nemotron-3-5-lightning) | 3B active; fastest on-device MoE at 271 tok/s, above Qwen 3.6 35B A3B |
| Muse Glimmer 30B | 30B dense | -- | -- | -- | No AA page | Largest Meta on-device model; fits consumer GPUs with quantization |
| Ministral 3 14B 2512 | 14B dense | -- | -- | -- | No AA page | Largest Mistral on-device; above 8B and 3B in quality |
| Ministral 3 8B 2512 | 8B dense | -- | -- | -- | No AA page | Mid-tier Mistral on-device; above 3B, below 14B |
| Ministral 3 3B 2512 | 3B dense | -- | -- | -- | No AA page | Smallest Mistral on-device; runs on phones |
| Gemma 4 27B | 27B MoE, 4B active | -- | -- | -- | No AA page | Google open-weight MoE; 4B active parameters, high throughput at moderate memory |
| Gemma 4 4B | 4B dense | -- | -- | -- | No AA page | Google on-device; runs on tablets and laptops, above Gemma 4 2B in quality |
| Gemma 4 2B | 2B dense | -- | -- | -- | No AA page | Smallest Gemma 4; runs on phones, released April 2026 |
| Qwen 3.8 27B | 27B dense | -- | -- | -- | No AA page | Newest Qwen on-device at 27B; supersedes Qwen 3.6 27B |
| Qwen 3.6 35B A3B | 35B MoE, 3B active | -- | -- | -- | No AA page | 3B active; comparable to Nemotron Lightning in footprint, Alibaba ecosystem |
| Qwen 3.5 9B | 9B dense | -- | -- | -- | No AA page | Small Qwen with reasoning; above Ministral 8B in size |
| LFM 2.5 24B A2B | 24B MoE, 2B active | -- | -- | -- | No AA page | Smallest active footprint (2B); below Nemotron Lightning (3B active) |
| Ternary Bonsai 2 9B | 9B ternary | -- | -- | -- | No AA page | Ternary quantization; ~3x memory reduction vs. standard 9B |

Additions in Phase 5: Gemma 4 4B, Gemma 4 2B, Gemma 4 27B.

Removals in Phase 5:
- Qwen 3 4B: released May 14, 2025; outside the 12-month window (must be after 2025-11-16).
- Qwen 3 30B A3B 2507: Qwen 3 series released May 14, 2025; outside the 12-month window.

Note: Gemma 4 12B exists on the AA leaderboard but is not in Kiln's
model list; adding new models is out of scope for this phase.  Most
on-device models are local-only (Ollama/Docker Model Runner) and have no
AA page.

### top_open (13/14)

Best open-weight models across a range of sizes.

| Model | AA Index | AA $/task | AA tok/s | AA URL | Reason |
|-------|----------|-----------|----------|--------|--------|
| Nemotron 3 Ultra | -- | -- | -- | No AA page | NVIDIA open-weight flagship; largest open model from NVIDIA |
| Muse Spark Open | 25 | -- | -- | [link](https://artificialanalysis.ai/models/muse-spark-open) | Index 25; Meta open-weight reasoning at 42B active, above Mistral Large 4 (26 at $2.06) |
| Mistral Large 4 | 26 | $2.06 | 82 | [link](https://artificialanalysis.ai/models/mistral-large-4) | Index 26 at $2.06/task; European open-weight flagship, above median (23) for open models |
| Gemma 4 31B | 4 (reasoning) | -- | 36 | [link](https://artificialanalysis.ai/models/gemma-4-31b) | Google open-weight; competitive on Arena despite low AA reasoning index |
| Gemma 4 27B | -- | -- | -- | No AA page | Google open-weight MoE; 4B active, high throughput alternative to 31B dense |
| DeepSeek V4.1 Flash 1017 | 33 | $0.60 | 174 | [link](https://artificialanalysis.ai/models/deepseek-v4-1-flash-1017) | Index 33 at $0.60/task; highest index among open flash models, above Minimax (29 at $0.49) |
| DeepSeek V4 Pro 0813 | 23 | $1.77 | 93 | [link](https://artificialanalysis.ai/models/deepseek-v4-pro) | Index 23 at $1.77/task; open-weight reasoning, at median for open models |
| Qwen 3.8 2.4T A95B | -- | -- | -- | No AA page | Alibaba's largest open MoE at 2.4T parameters; no other open model at this scale |
| Qwen 3.8 27B | -- | -- | -- | No AA page | Open-weight 27B dense from Alibaba; newest Qwen at this size |
| GLM 5.3 | 32 | $5.01 | 87 | [link](https://artificialanalysis.ai/models/glm-5-3) | Index 32 at $5.01/task; ZhipuAI open-weight flagship, above Mistral Large 4 (26) and DS V4 Pro (23) |
| Kimi K3 | -- | -- | 48 | [link](https://artificialanalysis.ai/models/kimi-k3) | Moonshot open-weight flagship at 2.8T; deprecated on AA but competitive on Arena |
| Minimax M3.1 Flash | 29 | $0.49 | 142 | [link](https://artificialanalysis.ai/models/minimax-m3-1-flash) | Index 29 at $0.49/task; open-weight flash, above DS V4 Pro (23) at lower cost |
| MiMo-V2.6-Pro | 30 | $0.26 | 53 | [link](https://artificialanalysis.ai/models/mimo-v2-6-pro) | Index 30 at $0.26/task; Xiaomi open-weight, best open-model value after MiMo-Flash |

### top_writing (9/14)

Best at prose: tone, style and following a writing brief.

| Model | AA Index | AA $/task | AA tok/s | AA URL | Reason |
|-------|----------|-----------|----------|--------|--------|
| GPT-6.1 Sol Pro | -- | -- | -- | No AA page | Extended reasoning for complex writing briefs; above Sol (55) with longer thinking |
| GPT-6.1 Sol | 55 | $1.27 | 49 | [link](https://artificialanalysis.ai/models/gpt-6-1-sol) | Index 55; strong prose quality, above Terra (51) in creative tasks |
| GPT-6.1 Terra | 51 | $0.96 | 72 | [link](https://artificialanalysis.ai/models/gpt-6-1-terra) | Index 51 at $0.96/task; good prose at mid-tier cost, above Argon (50) |
| GPT-6 Astra | 57 | $6.24 | 42 | [link](https://artificialanalysis.ai/models/gpt-6-astra) | Index 57; strong editorial writing, below Fable (65) and Opus (59) |
| Claude Fable 5.2 | 65 | $26.54 | 110 | [link](https://artificialanalysis.ai/models/claude-fable-5-2) | Index 65; highest on AA, natural and nuanced prose, above all others |
| Claude Opus 5.5 | 59 | $10.04 | 117 | [link](https://artificialanalysis.ai/models/claude-opus-5-5) | Index 59; careful instruction following, above Astra (57) in writing tasks |
| Claude 5.5 Sonnet | 55 | $10.02 | 151 | [link](https://artificialanalysis.ai/models/claude-sonnet-5-5) | Index 55; good prose at Sonnet tier, above Argon (50) in writing |
| Gemini 4 Argon | 50 | $4.97 | 66 | [link](https://artificialanalysis.ai/models/gemini-4-argon) | Index 50 at $4.97/task; strong instruction following, above Wonder (44) |
| Muse Wonder 1.0 | 44 | -- | -- | [link](https://artificialanalysis.ai/models/muse-wonder) | Index 44; tone matching and creative writing, above Mistral Large 4 (26) |

Removal in Phase 5:
- Mistral Large 4: AA index 26 at $2.06/task; writing set members have
  indices 44-65 -- does not earn its place among the best prose models.

## Model note sources

The source behind the `Description:` and `Lineup:` lines of models added
after the Phase 4 backfill, and behind any other note line.

| Model | Source |
|-------|--------|
| Gemini 4 Neon | deepmind.google/models/model-cards/gemini-4-neon/ ("adapted from Gemini 4 Carbon", "balances depth and efficiency") |

## Serving variant notes

Serving variants carry `Same weights:` lines on both sides. They are
never `current`. Sources:

| Variant | Standard | Source |
|---------|----------|--------|
| GLM 5.3 Fast | GLM 5.3 | Fireworks routers/ slug; same GLM 5.3 weights with speed-optimised serving |
| Kimi K3 Fast | Kimi K3 | Fireworks routers/ slug; same K3 weights with speed-optimised serving |
| MiMo-V2.6-Pro-UltraSpeed | MiMo-V2.6-Pro | OpenRouter ultraspeed slug; same V2.6 Pro weights |

## Local-only model notes

Notes for local-only models are sourced from each lab's model card or
documentation:

| Model | Source |
|-------|--------|
| Gemma 4 4B | ai.google.dev/gemma (Gemma 4 model card) |
| Gemma 4 2B | ai.google.dev/gemma (Gemma 4 model card) |

## Provider notes

Provider notes were written from each provider's documentation:

| Provider | Source |
|----------|--------|
| OpenAI | openai.com/policies/terms-of-use |
| Groq | groq.com/trust |
| Amazon Bedrock | docs.aws.amazon.com/bedrock/ |
| Ollama | ollama.com/docs |
| OpenRouter | openrouter.ai/docs |
| Fireworks AI | fireworks.ai/security |
| Anthropic | anthropic.com/policies |
| Gemini API | ai.google.dev/gemini-api/terms |
| Azure OpenAI | learn.microsoft.com/en-us/azure/ai-services/openai/ |
| Hugging Face | huggingface.co/docs/inference-providers |
| Vertex | cloud.google.com/vertex-ai/docs |
| Together AI | together.ai/trust |
| SiliconFlow | siliconflow.cn |
| Cerebras | cerebras.ai |
| Docker Model Runner | docs.docker.com/desktop/features/model-runner/ |
| Featherless AI | featherless.ai |
| Cloudflare | developers.cloudflare.com/workers-ai/ |
| TypeSafe | typesafe.ai |

## Hugging Face models_dev_id

Set `models_dev_id="huggingface"` after confirming that models.dev's
`huggingface` entry (API base: `router.huggingface.co/v1`, docs:
`huggingface.co/docs/inference-providers`) is the Hugging Face Inference
Providers service that Kiln calls.
