# Compute Statistics

**POST /api/statistics**

**Tags:** Statistics

Confidence intervals and significance tests on eval metrics — use this INSTEAD of computing standard errors or significance by hand. Set `operation`:

- "proportion_ci": confidence interval + standard error for ONE proportion (e.g. an "85% pass, n=200" cell). Params: `proportion` (a fraction in [0,1]) and `n`.
- "compare_proportions": difference of two INDEPENDENT proportions with a significance verdict (conservative — for marginals only). Params: `proportion_a`, `n_a`, `proportion_b`, `n_b`.
- "mcnemar_paired": the PAIRED test for two binary pass/fail conditions scored over the SAME items — more powerful than compare_proportions; prefer it when comparing run configs on one eval dataset. Params: `outcomes_a`, `outcomes_b` — two aligned 0/1 arrays (fetch per-item eval results and pair on dataset_id).
- "compare_paired": paired comparison of two numeric arrays for continuous/count metrics (latency, tokens, cost) — NOT binary pass/fail. Params: `values_a`, `values_b`.

Returns JSON with the statistic, a confidence interval, a boolean `significant`, and a one-sentence `interpretation`. `confidence` defaults to 0.95.

## Request

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|operation|string|Yes|Which test to run (see the per-field [operation] tags for the params each one takes). One of: proportion_ci, compare_proportions, mcnemar_paired, compare_paired|
|confidence|number|No|Confidence level in (0,1). Default 0.95.|
|proportion|one of: number or null|No|[proportion_ci] the proportion as a fraction in [0,1] (e.g. 0.85).|
|n|one of: integer or null|No|[proportion_ci] sample size (> 0).|
|proportion_a|one of: number or null|No|[compare_proportions] baseline proportion in [0,1].|
|n_a|one of: integer or null|No|[compare_proportions] baseline sample size (> 0).|
|proportion_b|one of: number or null|No|[compare_proportions] treatment proportion in [0,1].|
|n_b|one of: integer or null|No|[compare_proportions] treatment sample size (> 0).|
|outcomes_a|one of: array of number or null|No|[mcnemar_paired] per-item baseline outcomes (0=fail, 1=pass). outcomes_a[i] and outcomes_b[i] must be the SAME item.|
|outcomes_b|one of: array of number or null|No|[mcnemar_paired] per-item treatment outcomes (0/1), positionally paired with outcomes_a.|
|values_a|one of: array of one of: number or null or null|No|[compare_paired] per-case baseline values (null allowed — that pair is skipped). values_a[i] and values_b[i] must be the same case.|
|values_b|one of: array of one of: number or null or null|No|[compare_paired] per-case treatment values (null allowed), positionally paired with values_a.|

## Responses

### 200 OK

Successful Response

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
