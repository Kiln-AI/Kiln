// Run config builders for the lineage unit tests. Test support only.
import type {
  KilnAgentRunConfigProperties,
  McpRunConfigProperties,
  TaskRunConfig,
} from "$lib/types"

type ConfigOverrides = Partial<Omit<TaskRunConfig, "run_config_properties">> & {
  derived_from?: (string | null)[]
}

export type AgentConfigOverrides = ConfigOverrides & {
  properties?: Partial<KilnAgentRunConfigProperties>
}

export type McpConfigOverrides = ConfigOverrides & {
  tool?: Partial<McpRunConfigProperties["tool_reference"]>
}

/** An ISO timestamp `index` minutes after a fixed start, for ordering tests. */
export function created_at_for(index: number): string {
  return new Date(Date.UTC(2026, 0, 1, 0, index)).toISOString()
}

export function make_agent_config(
  overrides: AgentConfigOverrides = {},
): TaskRunConfig {
  const { properties, ...rest } = overrides
  return {
    ...base_config(rest),
    run_config_properties: {
      type: "kiln_agent",
      model_name: "gpt_5",
      model_provider_name: "openai",
      prompt_id: "simple_prompt_builder",
      temperature: 1,
      top_p: 1,
      structured_output_mode: "json_schema",
      thinking_level: null,
      tools_config: null,
      input_transform: null,
      ...properties,
    },
  }
}

export function make_mcp_config(
  overrides: McpConfigOverrides = {},
): TaskRunConfig {
  const { tool, ...rest } = overrides
  return {
    ...base_config(rest),
    run_config_properties: {
      type: "mcp",
      tool_reference: {
        tool_id: "mcp::local::server_1::run_task",
        tool_name: "Run Task",
        ...tool,
      },
    },
  }
}

/**
 * An agent config named after its id, created `minute` minutes after the
 * fixture start, derived from `derived_from`.
 */
export function make_dated_config(
  id: string,
  minute: number,
  derived_from: (string | null)[] = [],
  properties: Partial<KilnAgentRunConfigProperties> = {},
): TaskRunConfig {
  return make_agent_config({
    id,
    name: `Name ${id}`,
    created_at: created_at_for(minute),
    derived_from,
    properties,
  })
}

/** `n` identical agent configs, `rc_0` to `rc_{n-1}`, each derived from the one before. */
export function make_chain(n: number): TaskRunConfig[] {
  return Array.from({ length: n }, (_, i) =>
    make_agent_config({
      id: `rc_${i}`,
      name: `Config ${i}`,
      created_at: created_at_for(i),
      derived_from: i === 0 ? [] : [`rc_${i - 1}`],
    }),
  )
}

/**
 * `n` agent configs with a seeded random lineage: a mix of new roots, nodes
 * with no recorded parent, one or two parents and missing parents, with
 * random prompt, model and temperature values. The same seed always gives the
 * same configs.
 */
export function make_random_lineage(n: number, seed: number): TaskRunConfig[] {
  const random = seeded_random(seed)
  const configs: TaskRunConfig[] = []
  for (let i = 0; i < n; i++) {
    const roll = random()
    const derived_from: string[] = []
    if (i > 0 && roll > 0.1) {
      derived_from.push(`rc_${Math.floor(random() * i)}`)
      if (roll > 0.9) {
        derived_from.push(`rc_${Math.floor(random() * i)}`)
      }
      if (roll > 0.97) {
        derived_from.unshift(`missing_${Math.floor(random() * 5)}`)
      }
    }
    configs.push(
      make_agent_config({
        id: `rc_${i}`,
        name: `Config ${i}`,
        created_at: created_at_for(i),
        derived_from,
        properties: {
          prompt_id: `prompt_${Math.floor(random() * 4)}`,
          model_name: `model_${Math.floor(random() * 3)}`,
          temperature: Math.floor(random() * 3) / 2,
        },
      }),
    )
  }
  return configs
}

function base_config({
  derived_from,
  ...rest
}: ConfigOverrides): Omit<TaskRunConfig, "run_config_properties"> {
  return {
    v: 1,
    id: "rc_default",
    created_at: created_at_for(0),
    created_by: "test_user",
    name: "Test Config",
    description: null,
    prompt: null,
    starred: false,
    model_type: "task_run_config",
    provenance:
      derived_from === undefined ? null : { derived_from_ids: derived_from },
    ...rest,
  }
}

// mulberry32: a small, fast seeded generator returning floats in [0, 1).
function seeded_random(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
