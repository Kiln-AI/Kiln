# Backfill Sources

Sources for the agent notes and tags added in Phase 4.

## Data sources

- **models.dev API** (`https://models.dev/api.json`): pricing, release dates,
  context lengths, output limits, open-weight status.  Fetched 2026-11-13.
- **Lab documentation**: model cards, blog posts and API docs from each lab.
  Used for lineup ordering, parameter counts and architecture details
  (dense vs. MoE, active parameters).
- **Provider documentation**: data retention policies, rate limit tiers,
  routing behaviour and regional constraints for each provider.

## Selection criteria

A model was selected when it met either condition:

1. `featured_rank` is set (13 models), or
2. at least one non-deprecated provider entry has a models.dev `release_date`
   within 12 months of 2026-11-15 (124 additional models).

137 models were annotated with agent notes.  71 of those received the
`current` tag (the latest offering at each price level within each lab).

## Current tag assignments

Within each lab, `current` marks the latest model at each price level.
Models without `current` have a "Superseded by:" line naming the
replacement.

| Lab | Current models |
|-----|----------------|
| OpenAI (gpt) | GPT-6.1 Sol Pro, GPT-6.1 Sol, GPT-6.1 Terra Pro, GPT-6.1 Terra, GPT-6 Astra, GPT-6 Luna Pro, GPT-6 Luna |
| Anthropic (claude) | Claude Fable 5.2, Claude Opus 5.5, Claude 5.5 Sonnet, Claude 5.5 Haiku |
| Google (gemini) | Gemini 4 Argon, Gemini 3.8 Flash, Gemini 3.5 Flash Lite |
| Google (gemma) | Gemma 4 31B, Gemma 4 27B |
| NVIDIA (nemotron) | Nemotron 3.5 Super VL, Nemotron 3.5 Lightning, Nemotron 3 Ultra |
| Meta (muse) | Muse Wonder 1.0, Muse Spark Open, Muse Spark 1.2, Muse Ember, Muse Glimmer 30B |
| Mistral (mistral) | Mistral Large 4, Mistral Medium 3.5, Mistral Small 4, Ministral 3 14B/8B/3B 2512 |
| DeepSeek (deepseek) | DeepSeek V4.1 Flash 1017, DeepSeek V4 Pro 0813 |
| xAI (grok) | Grok 4.7 |
| Alibaba (qwen) | Qwen 3.8 Max 0902, Qwen 3.8 Max Prime, Qwen 3.8 2.4T A95B, Qwen 3.8 Flash, Qwen 3.8 Omni Flash, Qwen 3.8 27B, Qwen 3.7 Plus, Qwen 3.6 35B A3B, Qwen 3.5 397B, Qwen 3.5 122B, Qwen 3.5 9B |
| ZhipuAI (glm) | GLM 5.3, GLM 5.3 Fast, GLM 5.3 Prime, GLM 5.3 Flash, GLM 5.3 FlashX, GLM 5.3 FlashX Legal |
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

## Set membership

### recommended (18/20)

Models we recommend as candidates for new agents.  Each is `current` and
available on at least two providers or has a flagship featured rank.

| Model | Reason |
|-------|--------|
| GPT-6.1 Sol | OpenAI flagship; strong multi-turn tool use |
| GPT-6.1 Terra | OpenAI mid-tier; good speed-to-quality ratio |
| GPT-6 Astra | Previous-gen flagship; still strong |
| GPT-6 Luna | Fast; good for high-volume work |
| Claude Fable 5.2 | Anthropic's most capable model |
| Claude Opus 5.5 | Strong reasoning and long-horizon agentic work |
| Claude 5.5 Sonnet | Balanced speed and intelligence at mid-tier |
| Claude 5.5 Haiku | Fast with good quality; many providers |
| Gemini 4 Argon | Google flagship; strong multimodal reasoning |
| Gemini 3.8 Flash | Fast, widely available |
| Gemini 3.5 Flash Lite | Google's lightest model with good quality |
| Mistral Large 4 | Open-weight flagship; strong coding |
| Gemma 4 31B | Open-weight; strong for its size |
| DeepSeek V4.1 Flash 1017 | Strong open-weight flash model |
| DeepSeek V4 Pro 0813 | Strong reasoning; open weights |
| Qwen 3.8 Max 0902 | Alibaba flagship; strong general quality |
| GLM 5.3 | ZhipuAI flagship; open weights |
| Kimi K3 | Moonshot flagship; strong open-weight reasoning |

Grok 4.7 was removed from `recommended`: AA reports intelligence index 35
(below the median of 41 for its tier), output at $6.00/M tok, and
$7.77/task. Its general quality does not support a recommendation.

### top_value (13/14)

Best quality for the cost, based on models.dev pricing.

| Model | Cost (output $/M tok) | Reason |
|-------|-----------------------|--------|
| GPT-6.1 Terra | $2.00 | Mid-tier quality at a moderate price |
| GPT-6 Luna | $0.50 | Good quality at a very low price |
| Claude 5.5 Sonnet | $3.00 | Strong quality; competitive for its tier |
| Claude 5.5 Haiku | $0.50 | Excellent quality-to-cost ratio |
| Gemini 3.8 Flash | $0.30 | Very low price with strong capabilities |
| Gemini 3.5 Flash Lite | $0.15 | Lowest price with good usability |
| Muse Ember | $0.50 | Fast with decent quality |
| DeepSeek V4.1 Flash 1017 | $0.50 | Near-frontier quality at flash pricing |
| Qwen 3.8 Flash | $0.47 | Solid quality at a low price |
| GLM 5.3 Flash | $0.08 | Very low price with usable quality |
| Minimax M3.1 Flash | $0.30 | Open-weight model at flash pricing |
| MiMo-V2.6-Flash | $0.28 | Open-weight model; strong benchmarks |
| Ling 3.1 Flash | $0.14 | Very low price with decent quality |

Grok 4.7 was removed from `top_value`: AA reports output at $6.00/M tok
(the $2.00 figure is input price), intelligence index 35 (below-median 41),
and $7.77/task (notably slow at 25.7 min/task vs 13.3 median).

### top_fast (6/14)

Models with consistently fast output speed and low time to first token.

| Model | Reason |
|-------|--------|
| GPT-6 Luna | OpenAI's fastest model; optimised for throughput |
| Claude 5.5 Haiku | Anthropic's fastest; low latency on all providers |
| Gemini 3.8 Flash | Google's fast model; very low TTFT |
| Gemini 3.5 Flash Lite | Extremely fast; minimal model |
| Nemotron 3.5 Lightning | NVIDIA speed-optimised; 3B active parameters |
| Muse Ember | Meta's fast-tier model; low latency |

### top_on_device (10/14)

Models that run on consumer laptops or phones (roughly <= 35B dense
parameters, or MoE with few active parameters).

| Model | Size | Reason |
|-------|------|--------|
| Nemotron 3.5 Lightning | 30B MoE, 3B active | Small active parameters; fast inference |
| Muse Glimmer 30B | 30B dense | Fits on consumer GPUs |
| Ministral 3 14B 2512 | 14B dense | Designed for on-device |
| Ministral 3 8B 2512 | 8B dense | Designed for on-device |
| Ministral 3 3B 2512 | 3B dense | Smallest Mistral; phone-ready |
| Qwen 3.8 27B | 27B dense | Fits on consumer GPUs |
| Qwen 3.6 35B A3B | 35B MoE, 3B active | Very small active footprint |
| Qwen 3.5 9B | 9B dense | Small and capable |
| LFM 2.5 24B A2B | 24B MoE, 2B active | Tiny active footprint |
| Ternary Bonsai 2 9B | 9B ternary | Ternary quantization; efficient on-device |

### top_open (13/14)

Best open-weight models across a range of sizes.

| Model | Reason |
|-------|--------|
| Nemotron 3 Ultra | NVIDIA's open-weight flagship |
| Muse Spark Open | Meta's open-weight reasoning model; 42B active |
| Mistral Large 4 | Mistral open-weight flagship |
| Gemma 4 31B | Google open-weight; strong for size |
| Gemma 4 27B | Google open-weight; predecessor to 31B |
| DeepSeek V4.1 Flash 1017 | Open-weight; near-frontier quality |
| DeepSeek V4 Pro 0813 | Open-weight; strong reasoning |
| Qwen 3.8 2.4T A95B | Alibaba's largest open MoE |
| Qwen 3.8 27B | Open-weight; strong at 27B scale |
| GLM 5.3 | ZhipuAI open-weight flagship |
| Kimi K3 | Moonshot open-weight; strong reasoning |
| Minimax M3.1 Flash | Open-weight flash model |
| MiMo-V2.6-Pro | Xiaomi open-weight; top benchmarks |

### top_writing (10/14)

Best at prose: tone, style and following a writing brief.

| Model | Reason |
|-------|--------|
| GPT-6.1 Sol Pro | Extended reasoning variant; strong at following complex briefs |
| GPT-6.1 Sol | OpenAI flagship; excellent prose quality |
| GPT-6.1 Terra | Noted for writing and visual reasoning strength |
| GPT-6 Astra | Previous-gen flagship; still strong at creative and editorial writing |
| Claude Fable 5.2 | Claude family known for natural, nuanced prose |
| Claude Opus 5.5 | Strong writing with careful instruction following |
| Claude 5.5 Sonnet | Good prose quality at a lower tier than Opus/Fable |
| Gemini 4 Argon | Strong instruction following for writing tasks |
| Muse Wonder 1.0 | Meta's flagship; good at tone matching |
| Mistral Large 4 | Strong prose in English and French |

Grok 4.7 was removed from `top_writing`: AA intelligence index 35
(below-median 41) does not support inclusion among the best prose models.

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
