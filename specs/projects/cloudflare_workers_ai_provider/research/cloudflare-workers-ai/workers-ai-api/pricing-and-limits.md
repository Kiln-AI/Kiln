# Workers AI: Pricing and Rate Limits

Research date: 2026-09-28. Sources: [Pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) and [Limits](https://developers.cloudflare.com/workers-ai/platform/limits/), read from the `cloudflare/cloudflare-docs` repo source (commit `c153001`, 2026-09-28), plus changelog entries.

## Pricing model: Neurons

- Verbatim: "Workers AI is included in both the Free and Paid Workers plans and is priced at **$0.011 per 1,000 Neurons**."
- "Our free allocation allows anyone to use a total of **10,000 Neurons per day at no charge**. To use more than 10,000 Neurons per day, you need to sign up for the Workers Paid plan."
- "All limits reset daily at 00:00 UTC. If you exceed any one of the above limits, further operations will fail with an error." The error is HTTP 429, code 3036: "You have used up your daily free allocation of 10,000 neurons..." ([errors](https://developers.cloudflare.com/workers-ai/platform/errors/)).
- "Neurons are our way of measuring AI outputs across different models, representing the GPU compute needed to perform your request."
- Pricing is now shown per token but billed in Neurons: "Workers AI has updated pricing to be more granular, with per-model unit-based pricing presented, but still billing in neurons in the back end." The pricing table gives both "Price in Tokens" and "Price in Neurons" and says they are equivalent.
- Workers Paid "starts at $5 per month and still includes the 10,000 free Neurons per day allocation" ([changelog 2026-07-28](https://developers.cloudflare.com/changelog/post/2026-07-28-models-require-workers-paid/)).
- Prompt caching: some models have a discounted cached-input price (e.g. Kimi K2.6 $0.16/M cached vs $0.95/M input). Caching is on by default for select models; the `x-session-affinity` header improves hit rates ([prompt caching](https://developers.cloudflare.com/workers-ai/features/prompt-caching/)).
- Alternative payment: prepaid AI Gateway credits can pay for Workers AI when the gateway's Workers AI billing is set to "Unified billing" (details in the AI Gateway subtopic).

### Paid-only models
"Some models require a paid billing method. This applies to `@cf/moonshotai/kimi-k2.6`, `@cf/moonshotai/kimi-k2.7-code`, `@cf/zai-org/glm-5.2`, `@cf/zai-org/glm-5.3`, `@cf/zai-org/glm-5.3-flash`, `@cf/deepseek-ai/deepseek-v4-flash-0731`, and `@cf/deepseek-ai/deepseek-v4-pro-0813`." On Workers Free these return HTTP 403, code 5035. (Kimi K2.6/K2.7 Code/GLM 5.2 moved behind the paywall on 2026-07-28 "so we can prioritize capacity".) Kiln should surface 5035 as "this model needs a Workers Paid plan", not as a bad key.

### Sample LLM prices (from the pricing table, 2026-09-28)

| Model | Input $/M | Output $/M |
|---|---|---|
| @cf/ibm-granite/granite-4.0-h-micro | 0.017 | 0.112 |
| @cf/zai-org/glm-4.7-flash | 0.060 | 0.400 |
| @cf/google/gemma-4-26b-a4b-it | 0.100 | 0.300 |
| @cf/openai/gpt-oss-20b | 0.200 | 0.300 |
| @cf/meta/llama-4-scout-17b-16e-instruct | 0.270 | 0.850 |
| @cf/meta/llama-3.3-70b-instruct-fp8-fast | 0.293 | 2.253 |
| @cf/openai/gpt-oss-120b | 0.350 | 0.750 |
| @cf/qwen/qwen3.8-27b | 0.450 | 3.200 |
| @cf/nvidia/nemotron-3-120b-a12b | 0.500 | 1.500 |
| @cf/moonshotai/kimi-k2.6 (paid only) | 0.950 | 4.000 |
| @cf/deepseek-ai/deepseek-v4-pro-0813 (paid only) | 1.320 | 3.960 |
| @cf/zai-org/glm-5.3 (paid only) | 1.400 | 4.400 |

### What 10,000 free Neurons buys per day (my arithmetic from the Neuron column)

| Model | Neurons per M in / out | ≈ free input tokens/day | ≈ free output tokens/day |
|---|---|---|---|
| glm-4.7-flash | 5,500 / 36,400 | 1.8M | 275k |
| gemma-4-26b-a4b-it | 9,091 / 27,273 | 1.1M | 367k |
| gpt-oss-120b | 31,818 / 68,182 | 314k | 147k |
| llama-3.3-70b-instruct-fp8-fast | 26,668 / 204,805 | 375k | 49k |

These are single-dimension upper bounds (all input or all output). In practice a Kiln eval or synthetic-data run will exhaust the free tier quickly on mid-size models; users doing real work need Workers Paid.

Docs drift: the pricing table still lists models deprecated on 2026-05-30 (e.g. `@cf/meta/llama-3.1-8b-instruct`, `@cf/mistral/mistral-7b-instruct-v0.1`, `@cf/google/gemma-3-12b-it`, `@cf/moonshotai/kimi-k2.5`).

## Rate limits

From [Limits](https://developers.cloudflare.com/workers-ai/platform/limits/), verbatim where quoted:

- Limits are "default per task type, with some per-model limits".
- **Text Generation: "300 requests per minute, unless the model requires the Workers Paid plan"**.
- Paid-only models: "The following limits apply per account, per model": **20 requests per minute** with standard Workers AI billing, **50 requests per minute** with prepaid AI Gateway credits (unified billing). "These limits are designed for typical agentic and coding workloads, where requests to frontier models can take longer to complete."
- Text Embeddings: 3000 rpm (bge-large 1500 rpm).
- "Beta models may have lower rate limits." "Model inferences in local mode using Wrangler will also count towards these limits."
- Custom/higher limits via a Custom Requirements Form.
- No tokens-per-minute limit is documented.

Capacity is a separate failure mode from rate limits: HTTP 429 code 3040 "Capacity temporarily exceeded, please try again." Requests normally wait in a capacity queue; `options.rejectIfBusy: true` makes them fail fast instead ([reject busy requests](https://developers.cloudflare.com/workers-ai/features/reject-if-busy/)). Some models also advertise `async_queue` (Batch API) support; not relevant to Kiln's synchronous calls.

General Cloudflare API limit: "The global rate limit for the Cloudflare API is 1,200 requests per five minute period per user ... If you exceed this limit, all API calls for the next five minutes will be blocked" ([API rate limits](https://developers.cloudflare.com/fundamentals/api/reference/limits/)). **Unclear** whether this applies to Workers AI inference calls on `api.cloudflare.com`; the Workers AI limits page does not mention it, and 1,200/5 min (240 rpm) would be lower than the documented 300 rpm text-generation limit. I found no source resolving this.

What matters for Kiln users:
- Kiln runs many parallel requests during evals and synthetic data generation. At 20 rpm, paid-only frontier models (Kimi, GLM 5.x, DeepSeek V4) will throttle heavily; Kiln's concurrency for Workers AI should be conservative and retry on 3040.
- Three different 429s: 3021 (per-minute rate limit, observed in the [live test](../../../live_test_findings.md#rate-limits) — retryable), 3036 (daily free Neurons exhausted — not retryable today) and 3040 (capacity — retryable).
