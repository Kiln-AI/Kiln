"""Paid probe: how OpenAI's Responses API reacts to reasoning items replayed out of order.

Answers whether replaying reasoning items in the shapes LiteLLM's chat-to-Responses
bridge produces (all reasoning first, or only the last reasoning item), or without the
`phase` field on assistant messages, causes errors, prompt-cache misses, or more
reasoning tokens than replaying every output item verbatim in its original order.

Calls `client.responses.create` directly with the official `openai` SDK so the exact
`input` items are under our control. Reads the key from OPENAI_API_KEY.

Usage (from the repo root):

    uv run python specs/projects/improve_reasoning/research/openai-reasoning-order/probe.py \
        capture --model gpt-5.4-mini --out /path/to/captures.json
    uv run python .../probe.py replay --model gpt-5.4-mini --captures /path/to/captures.json \
        --out /path/to/replay.json
    uv run python .../probe.py within --model gpt-5.4-mini --captures /path/to/captures.json \
        --out /path/to/within.json

`capture` runs tool loops and saves every response's output items in full (including
encrypted reasoning). `replay` rebuilds turn 1 of one captured conversation in each
variant shape and measures the turn-2 call (`--mixed-only` runs just the pairs that
prime the cache with one shape and measure another). `within` does the same at a tool
round inside turn 1 (`--round 3` replays rounds 1-3 and measures the call for round 4).
`phase` checks whether dropping `phase` changes the rendered prompt. `orphan` sends a
reasoning item without the items that followed it. Each writes a JSON file of results.

Capture options used for the reported runs: default tasks at `--effort medium` and
`--effort high`, and `--hard` tasks with and without `--no-preamble`, `--parallel true`.
"""

from __future__ import annotations

import argparse
import copy
import json
import statistics
import sys
import time
import uuid
from typing import Any

from openai import BadRequestError, OpenAI

EFFORT = "medium"
# reasoning.context: None leaves the model default; "current_turn" or "all_turns" forces it.
REASONING_CONTEXT: str | None = None

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "lookup_order",
        "description": "Look up an order by its id. Returns the customer id, line items with SKU, quantity and unit weight in kg, and order status.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Order id such as A1001"}
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "lookup_customer",
        "description": "Look up a customer by customer id. Returns name, loyalty tier and the shipping region code of their default address.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Customer id such as C-77",
                }
            },
            "required": ["customer_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_shipping_quote",
        "description": "Get a shipping quote. Needs the destination region code and the total shipment weight in kg. Returns price in USD, transit days and a quote id.",
        "parameters": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "Region code such as NA-WEST",
                },
                "weight_kg": {"type": "number", "description": "Total weight in kg"},
                "speed": {"type": "string", "enum": ["standard", "express"]},
            },
            "required": ["region", "weight_kg", "speed"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

ORDERS: dict[str, dict[str, Any]] = {
    "A1001": {
        "customer_id": "C-77",
        "status": "awaiting_shipment",
        "items": [
            {"sku": "KT-200", "qty": 2, "unit_weight_kg": 3.5},
            {"sku": "GL-15", "qty": 4, "unit_weight_kg": 0.4},
        ],
    },
    "A1002": {
        "customer_id": "C-12",
        "status": "awaiting_shipment",
        "items": [{"sku": "KT-900", "qty": 1, "unit_weight_kg": 18.0}],
    },
    "A1003": {
        "customer_id": "C-77",
        "status": "on_hold",
        "items": [
            {"sku": "SH-03", "qty": 10, "unit_weight_kg": 0.25},
            {"sku": "KT-200", "qty": 1, "unit_weight_kg": 3.5},
        ],
    },
    "A1004": {
        "customer_id": "C-31",
        "status": "awaiting_shipment",
        "items": [
            {"sku": "GL-15", "qty": 12, "unit_weight_kg": 0.4},
            {"sku": "BR-08", "qty": 3, "unit_weight_kg": 1.2},
        ],
    },
    "A1005": {
        "customer_id": "C-45",
        "status": "awaiting_shipment",
        "items": [{"sku": "KT-450", "qty": 2, "unit_weight_kg": 9.75}],
    },
    "A1006": {
        "customer_id": "C-12",
        "status": "awaiting_shipment",
        "items": [
            {"sku": "BR-08", "qty": 5, "unit_weight_kg": 1.2},
            {"sku": "SH-03", "qty": 2, "unit_weight_kg": 0.25},
        ],
    },
}
CUSTOMERS: dict[str, dict[str, Any]] = {
    "C-77": {"name": "Dana Ruiz", "tier": "gold", "region": "NA-WEST"},
    "C-12": {"name": "Ishaan Mehta", "tier": "standard", "region": "EU-CENTRAL"},
    "C-31": {"name": "Mei Tanaka", "tier": "platinum", "region": "APAC-EAST"},
    "C-45": {"name": "Olu Adeyemi", "tier": "silver", "region": "NA-EAST"},
}
REGION_RATES: dict[str, tuple[float, float, int]] = {
    "NA-WEST": (6.0, 1.10, 4),
    "NA-EAST": (6.5, 1.05, 3),
    "EU-CENTRAL": (11.0, 1.80, 6),
    "APAC-EAST": (14.0, 2.20, 8),
}


def run_tool(name: str, args: dict[str, Any]) -> str:
    """Deterministic fake tool backend."""
    if name == "lookup_order":
        order = ORDERS.get(args["order_id"])
        return json.dumps(order if order else {"error": "order not found"})
    if name == "lookup_customer":
        customer = CUSTOMERS.get(args["customer_id"])
        return json.dumps(customer if customer else {"error": "customer not found"})
    if name == "get_shipping_quote":
        rate = REGION_RATES.get(args["region"])
        if not rate:
            return json.dumps({"error": "unknown region"})
        base, per_kg, days = rate
        price = base + per_kg * float(args["weight_kg"])
        if args["speed"] == "express":
            price *= 1.6
            days = max(1, days // 2)
        quote_id = f"Q-{args['region']}-{round(float(args['weight_kg']) * 100)}-{args['speed'][0].upper()}"
        return json.dumps(
            {"price_usd": round(price, 2), "transit_days": days, "quote_id": quote_id}
        )
    return json.dumps({"error": f"unknown tool {name}"})


def build_system_prompt(preamble: bool = True) -> str:
    """A long, fixed support-agent handbook so the prefix is well past 1,024 tokens.

    `preamble=False` drops the instruction to narrate before each tool call, which changes
    how often the model writes commentary messages between calls."""
    parts = [
        "You are Fulfilment Desk, the order and shipping assistant for Northwind Kitchen Supply, a business that sells commercial kitchen tools to restaurants, caterers and serious home cooks.",
        "You help staff answer customer questions about orders, customers and shipping. You have three tools: lookup_order, lookup_customer and get_shipping_quote. Never guess data a tool can give you. Always compute total weight from the order's line items (quantity times unit weight, summed) before asking for a quote.",
        "Before each tool call, write one short sentence telling the user what you are about to check. After you have what you need, give a concise final answer with the numbers you used."
        if preamble
        else "Call tools directly without narrating them. Call independent tools in parallel. After you have what you need, give a concise final answer with the numbers you used.",
    ]
    topics = [
        (
            "Order statuses",
            "An order is awaiting_shipment when it has been paid and picked but not yet handed to a carrier. An order is on_hold when payment review, address verification or stock reconciliation is pending. Orders on hold must not be quoted for express shipping until the hold clears; you may quote standard shipping for planning purposes but must say the order is on hold.",
        ),
        (
            "Loyalty tiers",
            "Customers belong to one of four tiers: standard, silver, gold and platinum. Gold customers receive a 10 percent discount on standard shipping. Platinum customers receive free standard shipping and a 25 percent discount on express. Silver and standard customers pay list price. Always state which tier discount, if any, you applied.",
        ),
        (
            "Regions",
            "Shipping regions are NA-WEST, NA-EAST, EU-CENTRAL and APAC-EAST. Every customer has exactly one default region. Do not invent regions. If a customer has no region, ask staff to verify the address before quoting.",
        ),
        (
            "Weights",
            "Unit weights in the catalogue are shipping weights in kilograms, including packaging. Multiply by quantity and sum across all line items. Round the total to two decimal places before passing it to the quote tool. Do not add extra packaging weight.",
        ),
        (
            "Quotes",
            "Quotes are valid for 48 hours. Always pass the quote id back to staff so they can book the shipment. If staff ask to compare speeds, request one quote per speed. Never quote for more than one region per order.",
        ),
        (
            "Tone",
            "Be precise and brief. Staff are busy. Use plain sentences, no marketing language, and no emoji. Show arithmetic when it would help staff verify a number.",
        ),
        (
            "Escalation",
            "Escalate to a human supervisor when an order is above 50 kg, when a customer disputes a charge, when a tool returns an error twice in a row, or when the request involves hazardous materials. Say clearly that you are escalating and why.",
        ),
        (
            "Privacy",
            "Only reveal customer names and regions to staff, never full addresses. Never repeat payment details. If asked for data you do not have, say so rather than guessing.",
        ),
        (
            "Multiple orders",
            "When staff ask about several orders, handle each order separately and present a short per-order summary followed by a combined total if they ask for one. Orders for the same customer may be combined into one shipment only if both are awaiting_shipment and staff explicitly request it.",
        ),
        (
            "Returns",
            "Returns are handled by a different team. If staff ask about returns, tell them to open a returns ticket and do not quote return shipping.",
        ),
        (
            "Catalogue codes",
            "SKU prefixes: KT is knives and cutting tools, GL is gloves and protective wear, SH is shears and scissors, BR is brushes and cleaning tools. The prefix is informational only and does not change shipping.",
        ),
        (
            "Carrier notes",
            "Standard shipping uses ground carriers. Express uses air where available. Transit days are business days. Express to APAC-EAST may be delayed by customs; mention this when quoting express to that region.",
        ),
    ]
    for i, (title, body) in enumerate(topics, start=1):
        parts.append(f"Section {i}: {title}. {body}")
        parts.append(
            f"Section {i} examples. Example {i}.1: a staff member asks a question that touches {title.lower()}; you check the relevant record with a tool, apply the rule above, and answer in two or three sentences. "
            f"Example {i}.2: a staff member gives you partial information about {title.lower()}; you ask for the missing order id or customer id only if no tool can recover it. "
            f"Example {i}.3: the rule on {title.lower()} conflicts with what a staff member asks for; you follow the rule, explain the conflict in one sentence, and offer the closest allowed alternative."
        )
    parts.append(
        "Worked example. Staff: 'Quote standard shipping for order Z9.' You: 'Looking up order Z9.' (call lookup_order) 'Now checking the customer's region.' (call lookup_customer) "
        "'Total weight is 2 x 1.5 + 3 x 0.2 = 3.6 kg; requesting a standard quote to NA-EAST.' (call get_shipping_quote) Final: 'Order Z9 for a silver customer in NA-EAST weighs 3.6 kg. Standard shipping is $10.28, 3 business days, quote Q-NA-EAST-360-S. No tier discount applies.'"
    )
    return "\n\n".join(parts * 2)


SYSTEM_PROMPT = build_system_prompt()

TASKS: list[str] = [
    "Quote standard shipping for order A1001, applying any tier discount.",
    "Compare standard and express shipping for order A1004 and tell me the cheaper option after tier discounts.",
    "Order A1003: can we ship it express today? If not, give me the standard quote.",
    "Get standard quotes for orders A1002 and A1005 and give me the combined total.",
    "Customer asked about order A1006. Quote express shipping and tell me the transit time.",
    "For order A1001 and order A1003 (same customer), what would standard shipping cost for each separately?",
    "Quote standard shipping for order A1005. Then also check whether express is less than double the standard price.",
    "Order A1002: quote both speeds and include the quote ids.",
    "Check order A1004 and A1006 and quote standard shipping for whichever is heavier.",
    "Quote express shipping for order A1003 and explain any restrictions.",
]

# Harder tasks: many independent lookups and arithmetic, to give the model room to
# reason between tool calls inside one response.
HARD_TASKS: list[str] = [
    "For every order A1001 through A1006: find the customer, compute total weight, get standard and express quotes, apply tier discounts and on-hold rules, then rank the orders by discounted standard cost per kg. Show your arithmetic.",
    "Which customer has the highest combined discounted standard shipping cost across all of their orders (A1001-A1006)? Check every order and quote each one.",
    "Orders A1001 and A1003 belong to the same customer. Quote them separately (standard and express where allowed) and also as one combined standard shipment if the rules allow it; explain which rules block what.",
    "For orders A1002, A1004 and A1005, decide for each whether express is worth it, defined as costing less than 1.5 times the discounted standard price per business day saved. Get all the quotes you need.",
    "Audit orders A1001-A1006 for anything that needs escalation or a restriction under the handbook, and give standard quotes for the rest.",
]

TURN2_MESSAGE = (
    "Thanks. Before I book it: from what you already looked up, which quote id(s) and total weight(s) did you use, "
    "and which tier discount applied? Answer from the conversation so far without calling any tools."
)


def make_client() -> OpenAI:
    return OpenAI(max_retries=2, timeout=300)


USAGE_LOG: list[dict[str, Any]] = []


def call(
    client: OpenAI,
    model: str,
    input_items: list[dict[str, Any]],
    cache_key: str,
    parallel_tool_calls: bool = True,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    """One Responses API call. Returns a plain dict with status, usage and output items, or the error."""
    kwargs: dict[str, Any] = {
        "model": model,
        "instructions": SYSTEM_PROMPT,
        "input": input_items,
        "tools": TOOLS,
        "parallel_tool_calls": parallel_tool_calls,
        "store": False,
        "include": ["reasoning.encrypted_content"],
        "reasoning": {"effort": EFFORT, "summary": "auto"}
        | ({"context": REASONING_CONTEXT} if REASONING_CONTEXT else {}),
        "prompt_cache_key": cache_key,
    }
    if max_output_tokens is not None:
        kwargs["max_output_tokens"] = max_output_tokens
    started = time.time()
    try:
        response = client.responses.create(**kwargs)
    except BadRequestError as error:
        body = getattr(error, "body", None)
        USAGE_LOG.append({"model": model, "error": True})
        return {
            "ok": False,
            "http_status": error.status_code,
            "error": json.dumps(body) if body else str(error),
        }
    usage = response.usage
    record = {
        "ok": True,
        "http_status": 200,
        "status": response.status,
        "seconds": round(time.time() - started, 1),
        "input_tokens": usage.input_tokens if usage else None,
        "cached_tokens": usage.input_tokens_details.cached_tokens if usage else None,
        "output_tokens": usage.output_tokens if usage else None,
        "reasoning_tokens": usage.output_tokens_details.reasoning_tokens
        if usage
        else None,
        "output": [item.model_dump(exclude_none=True) for item in response.output],
    }
    USAGE_LOG.append(
        {
            "model": model,
            "input": record["input_tokens"],
            "cached": record["cached_tokens"],
            "output": record["output_tokens"],
        }
    )
    return record


def sequence(output: list[dict[str, Any]]) -> list[str]:
    labels = []
    for item in output:
        label = item["type"]
        if item["type"] == "message":
            label += f"({item.get('phase', 'no-phase')})"
        if item["type"] == "function_call":
            label += f"({item['name']})"
        labels.append(label)
    return labels


def interleave_stats(output: list[dict[str, Any]]) -> dict[str, Any]:
    types = [item["type"] for item in output]
    seen_non_reasoning = False
    reasoning_after_other = False
    for t in types:
        if t == "reasoning" and seen_non_reasoning:
            reasoning_after_other = True
        if t in ("function_call", "message"):
            seen_non_reasoning = True
    return {
        "reasoning_count": types.count("reasoning"),
        "reasoning_after_call_or_message": reasoning_after_other,
        "message_count": types.count("message"),
        "messages_with_phase": sum(
            1 for i in output if i["type"] == "message" and "phase" in i
        ),
        "function_call_count": types.count("function_call"),
    }


def tool_outputs(output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for item in output:
        if item["type"] == "function_call":
            results.append(
                {
                    "type": "function_call_output",
                    "call_id": item["call_id"],
                    "output": run_tool(item["name"], json.loads(item["arguments"])),
                }
            )
    return results


def cmd_capture(args: argparse.Namespace) -> None:
    global SYSTEM_PROMPT, EFFORT
    SYSTEM_PROMPT = build_system_prompt(preamble=not args.no_preamble)
    EFFORT = args.effort
    client = make_client()
    conversations = []
    tasks = HARD_TASKS if args.hard else TASKS
    for index, task in enumerate(tasks[: args.tasks]):
        parallel = (
            True
            if args.parallel == "true"
            else False
            if args.parallel == "false"
            else index % 2 == 0
        )
        cache_key = f"kiln-reasoning-probe-capture-{args.model}"
        history: list[dict[str, Any]] = [{"role": "user", "content": task}]
        rounds = []
        for _ in range(8):
            result = call(
                client, args.model, history, cache_key, parallel_tool_calls=parallel
            )
            if not result["ok"]:
                print("ERROR", result, file=sys.stderr)
                break
            outputs = tool_outputs(result["output"])
            rounds.append({"response": result, "tool_outputs": outputs})
            print(
                f"task {index} parallel={parallel}: {sequence(result['output'])} in={result['input_tokens']} cached={result['cached_tokens']} reasoning={result['reasoning_tokens']}"
            )
            history = history + result["output"] + outputs
            if not outputs:
                break
        conversations.append(
            {"task": task, "parallel_tool_calls": parallel, "rounds": rounds}
        )
    with open(args.out, "w") as f:
        json.dump(
            {
                "model": args.model,
                "effort": EFFORT,
                "system_prompt": SYSTEM_PROMPT,
                "conversations": conversations,
                "usage_log": USAGE_LOG,
            },
            f,
            indent=1,
        )


# Variant builders. Each takes one response's output items and returns the items to replay.


def v1_exact(output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [copy.deepcopy(i) for i in output]


def v2_reasoning_first(output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reasoning = [copy.deepcopy(i) for i in output if i["type"] == "reasoning"]
    messages = [copy.deepcopy(i) for i in output if i["type"] == "message"]
    calls = [copy.deepcopy(i) for i in output if i["type"] == "function_call"]
    return reasoning + messages + calls


def v3_last_only(output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reasoning = [copy.deepcopy(i) for i in output if i["type"] == "reasoning"]
    messages = [copy.deepcopy(i) for i in output if i["type"] == "message"]
    calls = [copy.deepcopy(i) for i in output if i["type"] == "function_call"]
    return reasoning[-1:] + messages + calls


def v4_no_phase(output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = v1_exact(output)
    for i in items:
        if i["type"] == "message":
            i.pop("phase", None)
    return items


def v5_no_reasoning(output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [copy.deepcopy(i) for i in output if i["type"] != "reasoning"]


def v6_reasoning_no_id(output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = v1_exact(output)
    for i in items:
        if i["type"] == "reasoning":
            i.pop("id", None)
    return items


def v7_litellm_streamed(output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What LiteLLM 1.105.7's bridge sends for a streamed reply: all reasoning first (id,
    encrypted_content, summary), then one assistant message with the joined text and no id
    or phase, then function calls with no id or status."""
    reasoning = [
        {
            "type": "reasoning",
            "id": i["id"],
            "encrypted_content": i.get("encrypted_content"),
            "summary": i.get("summary", []),
        }
        for i in output
        if i["type"] == "reasoning"
    ]
    text = "".join(
        c.get("text", "")
        for i in output
        if i["type"] == "message"
        for c in i.get("content", [])
    )
    messages = (
        [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ]
        if text
        else []
    )
    calls = [
        {
            "type": "function_call",
            "call_id": i["call_id"],
            "name": i["name"],
            "arguments": i["arguments"],
        }
        for i in output
        if i["type"] == "function_call"
    ]
    return reasoning + messages + calls


def v8_litellm_non_streamed(output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = v7_litellm_streamed(output)
    reasoning = [i for i in items if i["type"] == "reasoning"]
    others = [i for i in items if i["type"] != "reasoning"]
    return reasoning[-1:] + others


def v9_litellm_no_reasoning(output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Kiln today across turns: LiteLLM's message and call shape, with no reasoning."""
    return [i for i in v7_litellm_streamed(output) if i["type"] != "reasoning"]


def v10_reasoning_id_only(output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reasoning items with their id but no encrypted_content (what a store:false replay
    looks like if the encrypted blob was not saved)."""
    items = v1_exact(output)
    for i in items:
        if i["type"] == "reasoning":
            i.pop("encrypted_content", None)
    return items


VARIANTS = {
    "V1_exact": v1_exact,
    "V2_reasoning_first": v2_reasoning_first,
    "V3_last_reasoning_only": v3_last_only,
    "V4_no_phase": v4_no_phase,
    "V5_no_reasoning": v5_no_reasoning,
    "V6_reasoning_without_id": v6_reasoning_no_id,
    "V7_litellm_streamed_shape": v7_litellm_streamed,
    "V8_litellm_non_streamed_shape": v8_litellm_non_streamed,
    "V9_litellm_shape_no_reasoning": v9_litellm_no_reasoning,
    "V10_reasoning_id_only": v10_reasoning_id_only,
}

# Synthetic shapes built across rounds, used because no captured response interleaved
# reasoning. They put a reasoning item where its original following item is not next.
SYNTHETIC = {
    # Round 2's reasoning item moved to the front of round 1, next to round 1's own
    # reasoning: [A, B, msg1, call1, out1, msg2, call2, out2]. This is the shape LiteLLM's
    # reasoning-first rule produces for an interleaved [A, call1, B, call2] reply.
    "S1_hoist_next_round_reasoning",
    # Round 1's reasoning item moved after round 1's function call: [msg1, call1, A, out1].
    "S2_reasoning_after_call",
}


def build_history(
    conversation: dict[str, Any],
    variant: str,
    upto_round: int | None = None,
    include_tool_outputs_for_last: bool = True,
    nonce: str = "",
) -> list[dict[str, Any]]:
    """Turn-1 history in a variant shape: user message, then each round's output items
    (transformed) followed by that round's function_call_output items.

    `nonce` is prefixed to the first user message so each variant gets its own cache
    prefix after the system prompt; without it, one variant's calls warm the cache for the
    next variant whenever the server renders both the same way."""
    history: list[dict[str, Any]] = [
        {"role": "user", "content": f"{nonce}{conversation['task']}"}
    ]
    rounds = (
        conversation["rounds"]
        if upto_round is None
        else conversation["rounds"][:upto_round]
    )
    outputs = [v1_exact(r["response"]["output"]) for r in rounds]
    if variant == "S1_hoist_next_round_reasoning":
        reasoning_rounds = [
            i for i, o in enumerate(outputs) if any(x["type"] == "reasoning" for x in o)
        ]
        if len(reasoning_rounds) >= 2:
            first, second = reasoning_rounds[0], reasoning_rounds[1]
            moved = [x for x in outputs[second] if x["type"] == "reasoning"]
            outputs[second] = [x for x in outputs[second] if x["type"] != "reasoning"]
            position = (
                max(i for i, x in enumerate(outputs[first]) if x["type"] == "reasoning")
                + 1
            )
            outputs[first] = (
                outputs[first][:position] + moved + outputs[first][position:]
            )
    elif variant == "S2_reasoning_after_call":
        for i, o in enumerate(outputs):
            if any(x["type"] == "reasoning" for x in o) and any(
                x["type"] == "function_call" for x in o
            ):
                outputs[i] = [x for x in o if x["type"] != "reasoning"] + [
                    x for x in o if x["type"] == "reasoning"
                ]
                break
    else:
        outputs = [VARIANTS[variant](o) for o in outputs]
    for index, (r, o) in enumerate(zip(rounds, outputs)):
        history += o
        if include_tool_outputs_for_last or index < len(rounds) - 1:
            history += r["tool_outputs"]
    return history


def pick_conversation(
    captures: dict[str, Any], index: int | None
) -> tuple[int, dict[str, Any]]:
    """Prefer a finished conversation whose responses interleave reasoning, then the one with the most reasoning items."""
    conversations = captures["conversations"]
    if index is not None:
        return index, conversations[index]

    def score(c: dict[str, Any]) -> tuple[int, int, int]:
        outs = [r["response"]["output"] for r in c["rounds"]]
        finished = int(bool(outs) and outs[-1] and outs[-1][-1]["type"] == "message")
        interleaved = sum(
            interleave_stats(o)["reasoning_after_call_or_message"] for o in outs
        )
        reasoning = sum(interleave_stats(o)["reasoning_count"] for o in outs)
        return finished, interleaved, reasoning

    best = max(range(len(conversations)), key=lambda i: score(conversations[i]))
    return best, conversations[best]


def summarise_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in runs if r["ok"]]
    if not ok:
        return {"n": 0, "errors": [r.get("error") for r in runs]}

    def med(key: str) -> float | None:
        values = [r[key] for r in ok if r.get(key) is not None]
        return statistics.median(values) if values else None

    return {
        "n": len(ok),
        "errors": [r.get("error") for r in runs if not r["ok"]],
        "input_tokens_median": med("input_tokens"),
        "cached_tokens_median": med("cached_tokens"),
        "cached_tokens_all": [r["cached_tokens"] for r in ok],
        "reasoning_tokens_median": med("reasoning_tokens"),
        "reasoning_tokens_all": [r["reasoning_tokens"] for r in ok],
        "output_sequences": [sequence(r["output"]) for r in ok],
    }


def answer_text(output: list[dict[str, Any]]) -> str:
    return " ".join(
        c.get("text", "")
        for i in output
        if i["type"] == "message"
        for c in i.get("content", [])
    )


def measure(
    client: OpenAI,
    model: str,
    prime_items: list[dict[str, Any]] | None,
    items: list[dict[str, Any]],
    cache_key: str,
    repeats: int,
    pause: float,
) -> dict[str, Any]:
    """Optionally prime the cache with `prime_items` (short output), then call with `items`
    once as the first (cross-prefix) measurement and `repeats` more times as identical
    repeats."""
    prime = None
    if prime_items is not None:
        prime = call(
            client,
            model,
            prime_items,
            cache_key,
            max_output_tokens=args_global.prime_max_tokens,
        )
        time.sleep(pause)
    runs = []
    for _ in range(repeats + 1):
        runs.append(call(client, model, items, cache_key))
        time.sleep(pause)
    first, rest = runs[0], runs[1:]
    return {
        "prime": None
        if prime is None
        else {
            k: prime.get(k)
            for k in (
                "ok",
                "http_status",
                "error",
                "status",
                "input_tokens",
                "cached_tokens",
                "reasoning_tokens",
            )
        },
        "first_call": {
            k: first.get(k)
            for k in (
                "ok",
                "http_status",
                "error",
                "input_tokens",
                "cached_tokens",
                "reasoning_tokens",
            )
        }
        | (
            {
                "sequence": sequence(first["output"]),
                "answer": answer_text(first["output"])[:600],
            }
            if first["ok"]
            else {}
        ),
        "repeats": summarise_runs(rest),
        "answers": [answer_text(r["output"])[:600] for r in rest if r["ok"]],
    }


args_global: argparse.Namespace


def load_captures(path: str) -> dict[str, Any]:
    """Load a capture file and reuse its system prompt and effort so replays share the prefix."""
    global SYSTEM_PROMPT, EFFORT
    with open(path) as f:
        captures = json.load(f)
    SYSTEM_PROMPT = captures.get("system_prompt", SYSTEM_PROMPT)
    EFFORT = captures.get("effort", EFFORT)
    return captures


def cmd_replay(args: argparse.Namespace) -> None:
    client = make_client()
    captures = load_captures(args.captures)
    index, conversation = pick_conversation(captures, args.conversation)
    print(f"using conversation {index}: {conversation['task']}")
    print(
        "round sequences:",
        [sequence(r["response"]["output"]) for r in conversation["rounds"]],
    )
    run_id = uuid.uuid4().hex[:8]
    results: dict[str, Any] = {
        "model": args.model,
        "reasoning_context": REASONING_CONTEXT,
        "isolate": args.isolate,
        "conversation_index": index,
        "task": conversation["task"],
        "round_sequences": [
            sequence(r["response"]["output"]) for r in conversation["rounds"]
        ],
        "variants": {},
    }
    variants = (
        []
        if args.mixed_only
        else args.variants.split(",")
        if args.variants
        else list(VARIANTS) + sorted(SYNTHETIC)
    )
    seen: dict[str, str] = {}
    for variant in variants:
        nonce = f"[ticket {run_id}-{variant}] " if args.isolate else ""
        turn1 = build_history(conversation, variant, nonce=nonce)
        fingerprint = json.dumps(build_history(conversation, variant), sort_keys=True)
        if fingerprint in seen:
            print(f"\n== {variant}: identical request to {seen[fingerprint]}, skipped")
            results["variants"][variant] = {"identical_to": seen[fingerprint]}
            continue
        seen[fingerprint] = variant
        # Cache state left by turn 1's own final tool round: everything up to the last
        # function_call_output, in the same shape.
        prime = build_history(
            conversation,
            variant,
            upto_round=len(conversation["rounds"]) - 1,
            nonce=nonce,
        )
        items = [*turn1, {"role": "user", "content": TURN2_MESSAGE}]
        cache_key = f"kiln-probe-{run_id}-{variant}"
        print(f"\n== {variant}: {len(items)} input items")
        result = measure(
            client, args.model, prime, items, cache_key, args.repeats, args.pause
        )
        results["variants"][variant] = result
        print(
            json.dumps(
                {
                    "prime": result["prime"],
                    "first": {
                        k: v for k, v in result["first_call"].items() if k != "answer"
                    },
                    "repeats": {
                        k: v
                        for k, v in result["repeats"].items()
                        if k != "output_sequences"
                    },
                },
                indent=None,
            )
        )
    # Kiln today: turn 1's loop ran through the bridge (streamed: reasoning first), then
    # the next turn is built from the saved trace with no reasoning.
    for name, prime_variant, measure_variant in [
        (
            "mixed_prime_V7_measure_V9",
            "V7_litellm_streamed_shape",
            "V9_litellm_shape_no_reasoning",
        ),
        ("mixed_prime_V1_measure_V7", "V1_exact", "V7_litellm_streamed_shape"),
        ("mixed_prime_V1_measure_V5", "V1_exact", "V5_no_reasoning"),
        ("mixed_prime_V1_measure_S1", "V1_exact", "S1_hoist_next_round_reasoning"),
    ]:
        if args.variants and not args.mixed_only:
            break
        nonce = f"[ticket {run_id}-{name}] " if args.isolate else ""
        prime = build_history(
            conversation,
            prime_variant,
            upto_round=len(conversation["rounds"]) - 1,
            nonce=nonce,
        )
        items = [
            *build_history(conversation, measure_variant, nonce=nonce),
            {"role": "user", "content": TURN2_MESSAGE},
        ]
        cache_key = f"kiln-probe-{run_id}-{name}"
        print(f"\n== {name}")
        result = measure(client, args.model, prime, items, cache_key, 0, args.pause)
        results["variants"][name] = result
        print(
            json.dumps(
                {
                    "prime": result["prime"],
                    "first": {
                        k: v for k, v in result["first_call"].items() if k != "answer"
                    },
                }
            )
        )
    results["usage_log"] = USAGE_LOG
    with open(args.out, "w") as f:
        json.dump(results, f, indent=1)


def cmd_within(args: argparse.Namespace) -> None:
    """Replay at tool round 2 inside turn 1: history through round 1's outputs and tool
    results, in each variant shape, then measure the next call."""
    client = make_client()
    captures = load_captures(args.captures)
    index, conversation = pick_conversation(captures, args.conversation)
    upto = args.round
    print(
        f"using conversation {index}, replaying rounds 1..{upto}: {[sequence(r['response']['output']) for r in conversation['rounds'][:upto]]}"
    )
    run_id = uuid.uuid4().hex[:8]
    results: dict[str, Any] = {
        "model": args.model,
        "reasoning_context": REASONING_CONTEXT,
        "isolate": args.isolate,
        "conversation_index": index,
        "upto_round": upto,
        "round_sequences": [
            sequence(r["response"]["output"]) for r in conversation["rounds"]
        ],
        "variants": {},
    }
    variants = (
        args.variants.split(",")
        if args.variants
        else [
            "V1_exact",
            "V2_reasoning_first",
            "V3_last_reasoning_only",
            "V4_no_phase",
            "V5_no_reasoning",
            "V7_litellm_streamed_shape",
            "V8_litellm_non_streamed_shape",
            "S1_hoist_next_round_reasoning",
            "S2_reasoning_after_call",
        ]
    )
    seen: dict[str, str] = {}
    for variant in variants:
        fingerprint = json.dumps(
            build_history(conversation, variant, upto_round=upto), sort_keys=True
        )
        nonce = f"[ticket {run_id}-{variant}] " if args.isolate else ""
        items = build_history(conversation, variant, upto_round=upto, nonce=nonce)
        if fingerprint in seen:
            print(f"\n== {variant}: identical request to {seen[fingerprint]}, skipped")
            results["variants"][variant] = {"identical_to": seen[fingerprint]}
            continue
        seen[fingerprint] = variant
        prime = (
            build_history(conversation, variant, upto_round=upto - 1, nonce=nonce)
            if upto > 1
            else [{"role": "user", "content": f"{nonce}{conversation['task']}"}]
        )
        cache_key = f"kiln-probe-within-{run_id}-{variant}"
        print(f"\n== {variant}: {len(items)} input items")
        result = measure(
            client, args.model, prime, items, cache_key, args.repeats, args.pause
        )
        results["variants"][variant] = result
        print(
            json.dumps(
                {
                    "prime": result["prime"],
                    "first": {
                        k: v for k, v in result["first_call"].items() if k != "answer"
                    },
                    "repeats": {k: v for k, v in result["repeats"].items()},
                },
                indent=None,
            )
        )
    results["usage_log"] = USAGE_LOG
    with open(args.out, "w") as f:
        json.dump(results, f, indent=1)


def cmd_phase(args: argparse.Namespace) -> None:
    """Does dropping `phase` (or using LiteLLM's message shape) change the rendered prompt?
    Prime with the exact turn-2 request, then send the same turn-2 request in another shape
    under the same cache key, and compare input and cached tokens."""
    client = make_client()
    captures = load_captures(args.captures)
    _, conversation = pick_conversation(captures, None)
    results: dict[str, Any] = {"model": args.model, "results": {}}
    for measure_variant in ["V4_no_phase", "V7_litellm_streamed_shape", "V1_exact"]:
        tag = uuid.uuid4().hex[:8]
        nonce = f"[ticket {tag}] "

        def turn2(variant: str, nonce: str = nonce) -> list[dict[str, Any]]:
            return [
                *build_history(conversation, variant, nonce=nonce),
                {"role": "user", "content": TURN2_MESSAGE},
            ]

        prime = call(
            client,
            args.model,
            turn2("V1_exact"),
            f"phase-check-{tag}",
            max_output_tokens=16,
        )
        time.sleep(3)
        measured = call(
            client,
            args.model,
            turn2(measure_variant),
            f"phase-check-{tag}",
            max_output_tokens=16,
        )
        results["results"][measure_variant] = {
            "prime_input": prime.get("input_tokens"),
            "measure_input": measured.get("input_tokens"),
            "measure_cached": measured.get("cached_tokens"),
        }
        print(measure_variant, results["results"][measure_variant])
    results["usage_log"] = USAGE_LOG
    with open(args.out, "w") as f:
        json.dump(results, f, indent=1)


def cmd_orphan(args: argparse.Namespace) -> None:
    """Send round 1's reasoning item without the items that originally followed it."""
    client = make_client()
    captures = load_captures(args.captures)
    _, conversation = pick_conversation(captures, None)
    round1 = conversation["rounds"][0]
    reasoning = [i for i in round1["response"]["output"] if i["type"] == "reasoning"]
    calls = [i for i in round1["response"]["output"] if i["type"] == "function_call"]
    user = {"role": "user", "content": conversation["task"]}
    cases = {
        "reasoning_then_user": [
            user,
            *reasoning,
            {"role": "user", "content": "Please continue."},
        ],
        "reasoning_last": [user, *reasoning],
        "reasoning_then_output_no_call": [user, *reasoning, *round1["tool_outputs"]],
        "reasoning_call_no_message": [
            user,
            *reasoning,
            *calls,
            *round1["tool_outputs"],
        ],
    }
    results: dict[str, Any] = {"model": args.model, "results": {}}
    for name, items in cases.items():
        r = call(client, args.model, items, "orphan-check", max_output_tokens=200)
        results["results"][name] = {
            k: r.get(k)
            for k in (
                "ok",
                "http_status",
                "error",
                "status",
                "input_tokens",
                "reasoning_tokens",
            )
        }
        print(name, results["results"][name])
    results["usage_log"] = USAGE_LOG
    with open(args.out, "w") as f:
        json.dump(results, f, indent=1)


def cmd_tokens(args: argparse.Namespace) -> None:
    """Measure the system prompt + tools prefix size with one tiny call."""
    client = make_client()
    r = call(
        client,
        args.model,
        [{"role": "user", "content": "ok"}],
        "kiln-probe-tokens",
        max_output_tokens=16,
    )
    print({k: r.get(k) for k in ("input_tokens", "cached_tokens", "status", "error")})


def main() -> None:
    global args_global
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("capture")
    p.add_argument("--model", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--tasks", type=int, default=len(TASKS))
    p.add_argument("--effort", default=EFFORT)
    p.add_argument("--no-preamble", action="store_true")
    p.add_argument("--hard", action="store_true")
    p.add_argument(
        "--parallel", choices=["alternate", "true", "false"], default="alternate"
    )
    for name in ("replay", "within"):
        p = sub.add_parser(name)
        p.add_argument("--model", required=True)
        p.add_argument("--captures", required=True)
        p.add_argument("--out", required=True)
        p.add_argument("--conversation", type=int, default=None)
        p.add_argument("--repeats", type=int, default=3)
        p.add_argument("--pause", type=float, default=2.0)
        p.add_argument("--variants", default="")
        p.add_argument("--prime-max-tokens", type=int, default=16)
        p.add_argument("--isolate", action=argparse.BooleanOptionalAction, default=True)
        p.add_argument(
            "--mixed-only",
            action="store_true",
            help="replay: run only the prime-one-shape, measure-another pairs",
        )
        p.add_argument("--context", choices=["current_turn", "all_turns"], default=None)
        if name == "within":
            p.add_argument("--round", type=int, default=1)
    for name in ("phase", "orphan"):
        p = sub.add_parser(name)
        p.add_argument("--model", required=True)
        p.add_argument("--captures", required=True)
        p.add_argument("--out", required=True)
    p = sub.add_parser("tokens")
    p.add_argument("--model", required=True)
    args = parser.parse_args()
    args_global = args
    global REASONING_CONTEXT
    REASONING_CONTEXT = getattr(args, "context", None)
    {
        "capture": cmd_capture,
        "replay": cmd_replay,
        "within": cmd_within,
        "phase": cmd_phase,
        "orphan": cmd_orphan,
        "tokens": cmd_tokens,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
