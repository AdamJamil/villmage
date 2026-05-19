"""Exhaustive enumeration of prompt caching strategies.

Explores all valid orderings of prompt sections, cache breakpoint
placements, and batching configurations to find the cheapest approach.
Models are locked (rating=Sonnet, speaking=Opus, location=Sonnet,
memory=Sonnet) and output quality is unaffected — only the arrangement
and caching of input tokens changes.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from itertools import permutations, combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data import VILLAGERS, LOCATIONS, Villager
from prompts import (
    system_prompt,
    _format_memories,
    _location_list,
)

from cost_analysis.pricing import ModelPricing, SONNET, OPUS, count_tokens, cost
from cost_analysis.scenarios import SimParams, PHASES, N_VILLAGERS, N_LOCATIONS
from cost_analysis.measurement import TokenMeasurement, _get_memories_for_day
from cost_analysis.transcript import load_history_lines


# ── Section definitions ──────────────────────────────────────────────

class Variation(Enum):
    STATIC = "static"
    PER_CONVERSATION = "per_conv"
    PER_TURN = "per_turn"
    PER_VILLAGER = "per_villager"


@dataclass(frozen=True)
class Section:
    name: str
    variation: Variation
    tokens: int  # 0 for PER_TURN (history), actual count for others


@dataclass(frozen=True)
class SectionTokens:
    """Per-section token counts measured from real prompts."""
    system: int
    shared_header: int
    char_name: int
    char_desc: int
    char_memories: int
    rating_instruction: int
    speaking_instruction: int
    loc_instruction: int
    loc_list: int
    mem_context: int
    mem_instruction: int
    # history_by_turn[t] = tokens in history section at turn t
    history_by_turn: list[int]


def measure_section_tokens(day: int, max_turns: int) -> SectionTokens:
    """Measure individual section token counts from real data."""
    memories = _get_memories_for_day(day)
    villager = VILLAGERS[0]
    v = Villager(name=villager.name, description=villager.description, memories=memories)
    location = LOCATIONS[0]
    history_lines = load_history_lines()

    sys_tok = count_tokens(system_prompt())

    # Shared header (without history)
    names = [vx.name for vx in VILLAGERS[:5]]
    names_str = ", ".join(names)
    header_text = (
        f"It is morning on day {day}.\n"
        f"You are currently at {location.name}.\n"
        f"The following villmagers are here: {names_str}.\n\n"
    )
    shared_header_tok = count_tokens(header_text)

    # History at each turn
    history_by_turn = []
    for t in range(max_turns):
        lines = history_lines[:t]
        if lines:
            text = "Here is the conversation so far:\n" + "\n".join(lines)
        else:
            text = "Nobody has spoken yet."
        history_by_turn.append(count_tokens(text))

    # Character sections
    name_tok = count_tokens(f"You are {v.name}.\n\n")
    desc_tok = count_tokens(
        f"Here is a description of your character:\n{v.description}\n"
        "Never contradict it, but feel free to extend it where appropriate.\n\n"
    )
    mem_text = f"Here are your memories:\n{_format_memories(v)}\n\n"
    mem_tok = count_tokens(mem_text)

    # Also average across villagers for desc
    all_desc = []
    for vx in VILLAGERS:
        vx2 = Villager(name=vx.name, description=vx.description, memories=memories)
        all_desc.append(count_tokens(
            f"Here is a description of your character:\n{vx2.description}\n"
            "Never contradict it, but feel free to extend it where appropriate.\n\n"
        ))
    avg_desc = sum(all_desc) // len(all_desc)

    # Instructions
    rating_instr = count_tokens(
        "Output a single integer from 0 to 10 ranking how badly you want to speak "
        "right now. This will determine who speaks next. Alternatively, output -1 "
        "to leave the location and end your time here. Output one integer and "
        "nothing else."
    )
    speaking_instr = count_tokens(
        "It is your turn to speak now. Have a realistic conversation with those "
        "present. Keep it short, only a sentence or two, unless the other people "
        "expect you to say more. Aim for a grounded improvisational style — "
        "everything should be deeply realistic and a slow-burn."
    )

    # Location choice sections
    loc_instr = count_tokens(
        f"It is morning on day {day}. Choose a location to go to.\n"
        "Only say the name of the location and nothing else.\n\n"
    )
    loc_list = count_tokens("Locations:\n" + _location_list(LOCATIONS))

    # Memory save sections
    mem_context = count_tokens(
        f"It is the end of the morning on day {day}. You were at {location.name}.\n\n"
    )
    mem_save_instr = count_tokens(
        "Summarize the conversation into a couple sentences to recall for the "
        "future. Make sure to record future appointments (both day and time of day), and "
        "updated opinions on the villmagers you talked to."
    )

    return SectionTokens(
        system=sys_tok,
        shared_header=shared_header_tok,
        char_name=name_tok,
        char_desc=avg_desc,
        char_memories=mem_tok,
        rating_instruction=rating_instr,
        speaking_instruction=speaking_instr,
        loc_instruction=loc_instr,
        loc_list=loc_list,
        mem_context=mem_context,
        mem_instruction=mem_save_instr,
        history_by_turn=history_by_turn,
    )


# ── Strategy representation ──────────────────────────────────────────

@dataclass(frozen=True)
class PromptLayout:
    """Section ordering + breakpoint placement for one call type."""
    sections: tuple[str, ...]
    breakpoints: tuple[int, ...]  # section indices after which to place breakpoints

    def describe(self) -> str:
        parts = ["system"]
        for i, s in enumerate(self.sections):
            parts.append(s)
            if i in self.breakpoints:
                parts.append("[BP]")
        return " | ".join(parts)


@dataclass(frozen=True)
class CachingStrategy:
    rating: PromptLayout
    speaking: PromptLayout
    location: PromptLayout
    memory: PromptLayout


@dataclass
class StrategyResult:
    strategy: CachingStrategy
    replay_cost: float
    projected_cost: float
    savings_vs_nocache_pct: float
    savings_vs_current_pct: float
    rating_cost: float
    speaking_cost: float
    location_cost: float
    memory_cost: float


# ── Section definitions per call type ────────────────────────────────

RATING_SECTIONS = {
    "shared_header": Variation.PER_CONVERSATION,
    "history": Variation.PER_TURN,
    "character": Variation.PER_VILLAGER,  # name + desc + memories bundled
    "instruction": Variation.STATIC,
}

SPEAKING_SECTIONS = {
    "shared_header": Variation.PER_CONVERSATION,
    "history": Variation.PER_TURN,
    "character": Variation.PER_VILLAGER,
    "instruction": Variation.STATIC,
}

LOCATION_SECTIONS = {
    "character": Variation.PER_VILLAGER,
    "instruction": Variation.STATIC,
    "location_list": Variation.STATIC,
}

MEMORY_SECTIONS = {
    "character": Variation.PER_VILLAGER,
    "phase_context": Variation.PER_CONVERSATION,
    "history": Variation.PER_TURN,
    "instruction": Variation.STATIC,
}


def _section_tokens(
    name: str, stoks: SectionTokens, call_type: str, turn: int = 0,
) -> int:
    """Return token count for a named section."""
    if name == "shared_header":
        return stoks.shared_header
    if name == "history":
        t = min(turn, len(stoks.history_by_turn) - 1)
        return stoks.history_by_turn[t]
    if name == "character":
        return stoks.char_name + stoks.char_desc + stoks.char_memories
    if name == "instruction":
        if call_type == "rating":
            return stoks.rating_instruction
        if call_type == "speaking":
            return stoks.speaking_instruction
        if call_type == "location":
            return stoks.loc_instruction
        if call_type == "memory":
            return stoks.mem_instruction
    if name == "location_list":
        return stoks.loc_list
    if name == "phase_context":
        return stoks.mem_context
    raise ValueError(f"Unknown section: {name}")


# ── Cost evaluation ──────────────────────────────────────────────────

def _evaluate_rating_layout(
    layout: PromptLayout,
    stoks: SectionTokens,
    params: SimParams,
) -> float:
    """Compute total daily rating cost for a given layout.

    Models within-turn sharing (parallel calls for K villagers) and
    cross-turn sharing (prefix-monotonic history) based on how sections
    are ordered.
    """
    sections = layout.sections
    section_defs = RATING_SECTIONS
    pricing = SONNET

    total = 0.0

    for group in params.conversations:
        group_size = group.size
        turns = group.turns
        cpd = group.per_day

        for t in range(turns):
            # Token count per section at this turn
            sec_toks = [_section_tokens(s, stoks, "rating", t) for s in sections]
            full_input = stoks.system + sum(sec_toks)

            # Within-turn shared prefix: consecutive sections from start
            # that are NOT PER_VILLAGER
            within_prefix = stoks.system
            for i, s in enumerate(sections):
                if section_defs[s] == Variation.PER_VILLAGER:
                    break
                within_prefix += sec_toks[i]

            per_villager_suffix = full_input - within_prefix

            # Cross-turn prefix for same villager:
            # Everything before history diverges. History is prefix-monotonic,
            # so the cache from turn T-1 matches up to history_{T-1}'s end.
            cross_turn_prefix = 0
            if t > 0:
                cross_turn_prefix = stoks.system
                for i, s in enumerate(sections):
                    if section_defs[s] == Variation.PER_TURN:
                        # Add previous turn's history length
                        prev_t = min(t - 1, len(stoks.history_by_turn) - 1)
                        cross_turn_prefix += stoks.history_by_turn[prev_t]
                        break
                    cross_turn_prefix += sec_toks[i]

            # Tokens after the cached prefix
            history_delta = 0
            if t > 0:
                curr_h = _section_tokens("history", stoks, "rating", t)
                prev_h = _section_tokens("history", stoks, "rating", t - 1)
                history_delta = max(0, curr_h - prev_h)

            # Find where the breakpoint is — determines what gets cached
            # Breakpoint at position P means sections 0..P are cached
            if layout.breakpoints:
                bp = max(layout.breakpoints)
                cached_end = stoks.system + sum(sec_toks[:bp + 1])
            else:
                cached_end = 0  # no caching

            # --- Turn 0: no cross-turn cache ---
            if t == 0:
                if cached_end >= pricing.min_cache_prefix and within_prefix > stoks.system:
                    # V1 writes cache, V2..VK read within-turn prefix
                    cached_shared = min(within_prefix, cached_end)
                    v1 = (cost(cached_shared, pricing.cache_write)
                          + cost(full_input - cached_shared, pricing.input))
                    vrest = (cost(cached_shared, pricing.cache_read)
                             + cost(full_input - cached_shared, pricing.input))
                    turn_cost = v1 + (group_size - 1) * vrest
                elif cached_end >= pricing.min_cache_prefix:
                    # Cache exists but no within-turn prefix (char-first)
                    # Each villager writes their own cache
                    turn_cost = group_size * cost(cached_end, pricing.cache_write) + group_size * cost(max(0, full_input - cached_end), pricing.input)
                else:
                    # No caching
                    turn_cost = group_size * cost(full_input, pricing.input)
            else:
                # --- Turn T > 0: cross-turn + within-turn ---
                # V1 (first call this turn): only cross-turn cache available
                if cross_turn_prefix >= pricing.min_cache_prefix:
                    # Read cross-turn prefix, write delta, input the rest
                    v1_cached_read = min(cross_turn_prefix, cached_end)
                    remaining_cached = max(0, min(cached_end, within_prefix) - v1_cached_read)
                    uncached = full_input - v1_cached_read - remaining_cached
                    v1 = (cost(v1_cached_read, pricing.cache_read)
                          + cost(remaining_cached, pricing.cache_write)
                          + cost(max(0, uncached), pricing.input))
                elif within_prefix >= pricing.min_cache_prefix and cached_end >= pricing.min_cache_prefix:
                    v1 = (cost(min(within_prefix, cached_end), pricing.cache_write)
                          + cost(full_input - min(within_prefix, cached_end), pricing.input))
                else:
                    v1 = cost(full_input, pricing.input)

                # V2..VK: choose max(within-turn, cross-turn) prefix
                if within_prefix >= cross_turn_prefix and within_prefix >= pricing.min_cache_prefix:
                    # Within-turn is longer (shared-first ordering)
                    cached_shared = min(within_prefix, cached_end)
                    vrest = (cost(cached_shared, pricing.cache_read)
                             + cost(full_input - cached_shared, pricing.input))
                elif cross_turn_prefix >= pricing.min_cache_prefix:
                    # Cross-turn is longer (char-first ordering)
                    # Each villager reads their own cross-turn cache
                    v_cached_read = min(cross_turn_prefix, cached_end)
                    remaining_write = max(0, min(cached_end, full_input) - v_cached_read)
                    uncached = max(0, full_input - v_cached_read - remaining_write)
                    vrest = (cost(v_cached_read, pricing.cache_read)
                             + cost(remaining_write, pricing.cache_write)
                             + cost(uncached, pricing.input))
                else:
                    vrest = cost(full_input, pricing.input)

                turn_cost = v1 + (group_size - 1) * vrest

            # Output
            turn_cost += group_size * cost(params.out_rating, pricing.output)
            total += cpd * turn_cost

    return total


def _evaluate_speaking_layout(
    layout: PromptLayout,
    stoks: SectionTokens,
    params: SimParams,
) -> float:
    """Compute total daily speaking cost (Opus, 1 call per turn)."""
    sections = layout.sections
    section_defs = SPEAKING_SECTIONS
    pricing = OPUS

    total = 0.0

    for group in params.conversations:
        turns = group.turns
        cpd = group.per_day

        for t in range(turns):
            sec_toks = [_section_tokens(s, stoks, "speaking", t) for s in sections]
            full_input = stoks.system + sum(sec_toks)

            # Cross-turn prefix for same speaker: only useful if the SAME
            # villager speaks consecutive turns (unlikely). For safety,
            # assume no cross-turn reuse for speaking.
            # Only benefit: if breakpoint covers static/shared sections.

            if layout.breakpoints:
                bp = max(layout.breakpoints)
                cached_end = stoks.system + sum(sec_toks[:bp + 1])
            else:
                cached_end = 0

            # Cross-turn: history is prefix-monotonic, so previous turn's
            # cache partially matches. Only 1 call per turn (no within-turn).
            cross_turn_prefix = 0
            if t > 0:
                cross_turn_prefix = stoks.system
                for i, s in enumerate(sections):
                    if section_defs[s] == Variation.PER_TURN:
                        prev_h = _section_tokens("history", stoks, "speaking", t - 1)
                        cross_turn_prefix += prev_h
                        break
                    elif section_defs[s] == Variation.PER_VILLAGER:
                        # Different speaker each turn — prefix breaks here
                        break
                    else:
                        cross_turn_prefix += sec_toks[i]

            if t == 0:
                if cached_end >= pricing.min_cache_prefix:
                    call_cost = (cost(cached_end, pricing.cache_write)
                                 + cost(max(0, full_input - cached_end), pricing.input))
                else:
                    call_cost = cost(full_input, pricing.input)
            else:
                if cross_turn_prefix >= pricing.min_cache_prefix and cached_end >= pricing.min_cache_prefix:
                    read_part = min(cross_turn_prefix, cached_end)
                    write_part = max(0, cached_end - read_part)
                    uncached = max(0, full_input - cached_end)
                    call_cost = (cost(read_part, pricing.cache_read)
                                 + cost(write_part, pricing.cache_write)
                                 + cost(uncached, pricing.input))
                elif cached_end >= pricing.min_cache_prefix:
                    call_cost = (cost(cached_end, pricing.cache_write)
                                 + cost(max(0, full_input - cached_end), pricing.input))
                else:
                    call_cost = cost(full_input, pricing.input)

            call_cost += cost(params.out_speaking, pricing.output)
            total += cpd * call_cost

    return total


def _evaluate_location_layout(
    layout: PromptLayout,
    stoks: SectionTokens,
    params: SimParams,
) -> float:
    """Location selection: PHASES * N_VILLAGERS Sonnet calls, each unique."""
    # Each call has a different villager, so no sharing between calls.
    # Only benefit: if same villager's cache persists across phases.
    # With 5-min TTL this is unlikely. Model as no caching.
    sec_toks = [_section_tokens(s, stoks, "location", 0) for s in layout.sections]
    full_input = stoks.system + sum(sec_toks)
    n_calls = PHASES * N_VILLAGERS

    # Check if cross-villager sharing is possible (only static sections match)
    if layout.breakpoints:
        bp = max(layout.breakpoints)
        cached_end = stoks.system + sum(sec_toks[:bp + 1])
        # Static prefix: consecutive static sections from start
        static_prefix = stoks.system
        for i, s in enumerate(layout.sections):
            if LOCATION_SECTIONS[s] != Variation.STATIC:
                break
            static_prefix += sec_toks[i]

        if static_prefix >= SONNET.min_cache_prefix and static_prefix <= cached_end:
            # First call writes, rest read the static prefix
            call1 = (cost(cached_end, SONNET.cache_write)
                      + cost(max(0, full_input - cached_end), SONNET.input))
            rest = (cost(static_prefix, SONNET.cache_read)
                    + cost(max(0, cached_end - static_prefix), SONNET.cache_write)
                    + cost(max(0, full_input - cached_end), SONNET.input))
            return call1 + (n_calls - 1) * rest + n_calls * cost(params.out_location, SONNET.output)

    # No useful caching
    input_cost = n_calls * cost(full_input, SONNET.input)
    output_cost = n_calls * cost(params.out_location, SONNET.output)
    return input_cost + output_cost


def _evaluate_memory_layout(
    layout: PromptLayout,
    stoks: SectionTokens,
    params: SimParams,
) -> float:
    """Memory saves: one per villager per conversation, Sonnet."""
    sections = layout.sections
    section_defs = MEMORY_SECTIONS
    pricing = SONNET

    total = 0.0

    for group in params.conversations:
        group_size = group.size
        cpd = group.per_day

        # Memory calls happen at the end of the conversation with full history.
        # All villagers in a conversation share the same history and phase_context.
        t = group.turns  # history length = full conversation
        sec_toks = [_section_tokens(s, stoks, "memory", t) for s in sections]
        full_input = stoks.system + sum(sec_toks)

        # Within-conversation sharing: sections that don't vary per villager
        within_prefix = stoks.system
        for i, s in enumerate(sections):
            if section_defs[s] == Variation.PER_VILLAGER:
                break
            within_prefix += sec_toks[i]

        if layout.breakpoints:
            bp = max(layout.breakpoints)
            cached_end = stoks.system + sum(sec_toks[:bp + 1])
        else:
            cached_end = 0

        if (within_prefix > stoks.system
                and cached_end >= pricing.min_cache_prefix
                and within_prefix <= cached_end):
            cached_shared = min(within_prefix, cached_end)
            v1 = (cost(cached_shared, pricing.cache_write)
                  + cost(full_input - cached_shared, pricing.input))
            vrest = (cost(cached_shared, pricing.cache_read)
                     + cost(full_input - cached_shared, pricing.input))
            input_cost = cpd * (v1 + (group_size - 1) * vrest)
        else:
            input_cost = cpd * group_size * cost(full_input, pricing.input)

        output_cost = cpd * group_size * cost(params.out_memory, pricing.output)
        total += input_cost + output_cost

    return total


# ── Enumeration ──────────────────────────────────────────────────────

def _generate_layouts(
    section_names: list[str], max_breakpoints: int = 2,
) -> list[PromptLayout]:
    """Generate all (ordering, breakpoint) combinations for a set of sections."""
    layouts = []
    for perm in permutations(section_names):
        n = len(perm)
        # 0 breakpoints (no caching)
        layouts.append(PromptLayout(sections=perm, breakpoints=()))
        # 1..max_breakpoints breakpoints
        for nbp in range(1, min(max_breakpoints, n) + 1):
            for bp_positions in combinations(range(n), nbp):
                layouts.append(PromptLayout(sections=perm, breakpoints=bp_positions))
        # Always include breakpoint at end (most common useful config)
        bp_end = (n - 1,)
        if bp_end not in [l.breakpoints for l in layouts if l.sections == perm]:
            layouts.append(PromptLayout(sections=perm, breakpoints=bp_end))
    return layouts


def _deduplicate_layouts(layouts: list[PromptLayout]) -> list[PromptLayout]:
    """Remove duplicate layouts (same sections and breakpoints)."""
    seen: set[tuple] = set()
    unique = []
    for l in layouts:
        key = (l.sections, l.breakpoints)
        if key not in seen:
            seen.add(key)
            unique.append(l)
    return unique


def optimize_call_type(
    call_type: str,
    section_names: list[str],
    evaluator,
    stoks: SectionTokens,
    params: SimParams,
) -> list[tuple[PromptLayout, float]]:
    """Enumerate all layouts for a call type and return sorted by cost."""
    layouts = _deduplicate_layouts(_generate_layouts(section_names))
    results = []
    for layout in layouts:
        try:
            c = evaluator(layout, stoks, params)
            results.append((layout, c))
        except Exception:
            continue
    results.sort(key=lambda x: x[1])
    return results


def optimize(
    params: SimParams,
    day: int = 1,
    max_turns: int = 20,
    top_n: int = 3,
) -> list[StrategyResult]:
    """Run exhaustive optimization across all call types.

    Returns the top_n strategies ranked by total projected cost.
    """
    stoks = measure_section_tokens(day, max_turns)

    # Compute no-cache baseline
    from cost_analysis.computation import compute_costs
    from cost_analysis.measurement import measure_tokens
    measurements = measure_tokens(day, max_turns)
    no_cache, current, _ = compute_costs(measurements, params)
    nocache_total = no_cache.total
    current_total = current.total

    # Optimize each call type independently
    rating_results = optimize_call_type(
        "rating",
        list(RATING_SECTIONS.keys()),
        _evaluate_rating_layout,
        stoks, params,
    )
    speaking_results = optimize_call_type(
        "speaking",
        list(SPEAKING_SECTIONS.keys()),
        _evaluate_speaking_layout,
        stoks, params,
    )
    location_results = optimize_call_type(
        "location",
        list(LOCATION_SECTIONS.keys()),
        _evaluate_location_layout,
        stoks, params,
    )
    memory_results = optimize_call_type(
        "memory",
        list(MEMORY_SECTIONS.keys()),
        _evaluate_memory_layout,
        stoks, params,
    )

    # Best layout per call type
    best_rating = rating_results[0] if rating_results else None
    best_speaking = speaking_results[0] if speaking_results else None
    best_location = location_results[0] if location_results else None
    best_memory = memory_results[0] if memory_results else None

    # Combine: take top-N rating layouts and pair with best of others
    # (rating dominates cost, so varying it produces the most different strategies)
    results = []
    seen_costs: set[float] = set()

    for rating_layout, rating_cost in rating_results:
        if best_speaking is None or best_location is None or best_memory is None:
            continue

        total = (rating_cost + best_speaking[1]
                 + best_location[1] + best_memory[1])

        # Deduplicate by cost (strategies with same cost are equivalent)
        rounded = round(total, 6)
        if rounded in seen_costs:
            continue
        seen_costs.add(rounded)

        strategy = CachingStrategy(
            rating=rating_layout,
            speaking=best_speaking[0],
            location=best_location[0],
            memory=best_memory[0],
        )

        savings_nc = (nocache_total - total) / nocache_total * 100 if nocache_total > 0 else 0
        savings_cur = (current_total - total) / current_total * 100 if current_total > 0 else 0

        results.append(StrategyResult(
            strategy=strategy,
            replay_cost=0.0,  # TODO: transcript replay
            projected_cost=total,
            savings_vs_nocache_pct=savings_nc,
            savings_vs_current_pct=savings_cur,
            rating_cost=rating_cost,
            speaking_cost=best_speaking[1],
            location_cost=best_location[1],
            memory_cost=best_memory[1],
        ))

        if len(results) >= top_n:
            break

    return results
