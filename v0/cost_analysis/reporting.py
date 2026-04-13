"""Report formatting and printing."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data import VILLAGERS, LOCATIONS, Villager
from prompts import (
    system_prompt,
    _format_memories,
    _location_list,
)

from cost_analysis.pricing import SONNET, OPUS, count_tokens, cost
from cost_analysis.scenarios import (
    SimParams, PHASES, N_VILLAGERS,
    UNIFORM_PARAMS, OBSERVED_PARAMS,
)
from cost_analysis.measurement import (
    TokenMeasurement, measure_tokens, _get_memories_for_day,
)
from cost_analysis.computation import CostBreakdown, compute_costs
from cost_analysis.transcript import load_history_lines


# ── Formatting helpers ───────────────────────────────────────────────

def pct(part: float, whole: float) -> str:
    if whole == 0:
        return "  -  "
    return f"{part / whole * 100:5.1f}%"


def fmt_dollar(v: float) -> str:
    return f"${v:.2f}"


# ── Params comparison report ─────────────────────────────────────────

def print_params_report(
    label: str,
    params: SimParams,
    measurements: TokenMeasurement,
    no_cache: CostBreakdown,
    current: CostBreakdown,
    char_first: CostBreakdown,
    optimized: "StrategyResult | None" = None,
):
    avg_group = (params.total_villagers_in_convs_per_day
                 / params.total_convs_per_day)
    total_rating = sum(g.size * g.turns * g.per_day for g in params.conversations)
    total_speaking = sum(g.turns * g.per_day for g in params.conversations)

    has_opt = optimized is not None

    print(f"\n{'─' * (84 if has_opt else 72)}")
    print(f"  {label}: {params.name}")
    print(f"{'─' * (84 if has_opt else 72)}")
    print(f"  Conversations/day:  {params.total_convs_per_day:>6.2f}      "
          f"Avg group size:  {avg_group:.2f}")
    print(f"  Rating calls:       {total_rating:>6.0f}      "
          f"Speaking calls:  {total_speaking:.0f}")
    print(f"  Memory save calls:  {params.total_villagers_in_convs_per_day:>6.0f}      "
          f"Output tok/speech: {params.out_speaking}")
    print(f"  Output tok/memory:  {params.out_memory:>6}")
    print()

    opt_hdr = f" {'Optimized':>10s}" if has_opt else ""
    opt_sep = f" {'─'*10}" if has_opt else ""
    print(f"  {'':24s} {'No cache':>10s} {'Current':>10s} {'Char-first':>10s}{opt_hdr}")
    print(f"  {'─'*24} {'─'*10} {'─'*10} {'─'*10}{opt_sep}")

    def _opt_col(call_cost):
        return f" {fmt_dollar(call_cost):>10s}" if has_opt else ""

    opt_loc = optimized.location_cost if has_opt else 0
    opt_rat = optimized.rating_cost if has_opt else 0
    opt_spk = optimized.speaking_cost if has_opt else 0
    opt_mem = optimized.memory_cost if has_opt else 0

    print(f"  {'Location  (Sonnet)':24s} {fmt_dollar(no_cache.location):>10s} "
          f"{fmt_dollar(current.location):>10s} {fmt_dollar(char_first.location):>10s}{_opt_col(opt_loc)}")
    print(f"  {'Rating    (Sonnet)':24s} {fmt_dollar(no_cache.rating):>10s} "
          f"{fmt_dollar(current.rating):>10s} {fmt_dollar(char_first.rating):>10s}{_opt_col(opt_rat)}")
    print(f"  {'Speaking  (Opus)':24s} {fmt_dollar(no_cache.speaking):>10s} "
          f"{fmt_dollar(current.speaking):>10s} {fmt_dollar(char_first.speaking):>10s}{_opt_col(opt_spk)}")
    print(f"  {'Memory    (Sonnet)':24s} {fmt_dollar(no_cache.memory):>10s} "
          f"{fmt_dollar(current.memory):>10s} {fmt_dollar(char_first.memory):>10s}{_opt_col(opt_mem)}")
    print(f"  {'─'*24} {'─'*10} {'─'*10} {'─'*10}{opt_sep}")
    opt_total = optimized.projected_cost if has_opt else 0
    print(f"  {'TOTAL':24s} {fmt_dollar(no_cache.total):>10s} "
          f"{fmt_dollar(current.total):>10s} {fmt_dollar(char_first.total):>10s}{_opt_col(opt_total)}")
    print()
    cs_save = no_cache.total - current.total
    cf_save = no_cache.total - char_first.total
    print(f"  Current saves:     {fmt_dollar(cs_save):>7s}/day  ({pct(cs_save, no_cache.total)})")
    print(f"  Char-first saves:  {fmt_dollar(cf_save):>7s}/day  ({pct(cf_save, no_cache.total)})")
    if has_opt:
        opt_save = no_cache.total - opt_total
        print(f"  Optimized saves:   {fmt_dollar(opt_save):>7s}/day  ({pct(opt_save, no_cache.total)})")


# ── Component breakdown ──────────────────────────────────────────────

TAG_SYSTEM = "System prompt"
TAG_DESCRIPTION = "Character description"
TAG_MEMORIES = "Memories"
TAG_HISTORY = "Conversation history"
TAG_INSTRUCTION = "Instruction text"
TAG_HEADER = "Shared header (time/loc/names)"
TAG_LOC_LIST = "Location list"
TAG_CONTEXT = "Phase/location context"
TAG_NAME = "Name line"
TAG_OUTPUT = "Output tokens"


def _component_row(label, tag, tokens, calls, pricing):
    total_tokens = tokens * calls
    dollars = cost(int(total_tokens), pricing)
    return (label, tag, tokens, calls, total_tokens, dollars)


def _print_section_block(title, note, rows, grand_total_ref):
    """Print one section of the component breakdown."""
    print(f"\n  {title}")
    if note:
        print(f"  {note}")
    for kind, label, tag, tok, calls, total_tok, dollars in rows:
        pct_str = f"{dollars/grand_total_ref[0]*100:6.1f}%" if grand_total_ref[0] > 0 else ""
        if kind == "output":
            print(f"    {'→ ' + label:<34s} {tok:>8} {calls:>7.0f} {total_tok:>10.0f} ${dollars:>8.4f} {pct_str:>8s}")
        else:
            print(f"    {label:<36s} {tok:>8} {calls:>7.0f} {total_tok:>10.0f} ${dollars:>8.4f} {pct_str:>8s}")
        grand_total_ref[0] += dollars


def print_component_breakdown(day: int, params: SimParams, max_turns: int):
    """Break each prompt type into its constituent sections and price them."""
    memories = _get_memories_for_day(day)
    villager = VILLAGERS[0]
    v = Villager(name=villager.name, description=villager.description, memories=memories)
    location = LOCATIONS[0]
    all_names = ["Pell Arenway", "Sable Dunmore", "Denn Corvale", "Orla Fenn", "Ham Birch"]
    history_lines = load_history_lines()

    sys_tok = count_tokens(system_prompt())

    # Measure all villager descriptions
    all_desc_toks = []
    for vx in VILLAGERS:
        vx2 = Villager(name=vx.name, description=vx.description, memories=memories)
        all_desc_toks.append(count_tokens(
            f"Here is a description of your character:\n{vx2.description}\n"
            "Never contradict it, but feel free to extend it where appropriate.\n\n"
        ))
    avg_desc_tok = sum(all_desc_toks) // len(all_desc_toks)

    mem_text = f"Here are your memories:\n{_format_memories(v)}\n\n"
    mem_tok = count_tokens(mem_text)
    name_tok = count_tokens(f"You are {v.name}.\n\n")

    # Shared header
    names_str = ", ".join(all_names)
    shared_header_tok = count_tokens(
        f"It is morning on day {day}.\n"
        f"You are currently at {location.name}.\n"
        f"The following villmagers are here: {names_str}.\n\n"
    )

    # History at midpoint and full
    mid_turn = max_turns // 2
    history_mid_text = "Here is the conversation so far:\n" + "\n".join(history_lines[:mid_turn])
    history_full_text = "Here is the conversation so far:\n" + "\n".join(history_lines[:max_turns])
    history_full_tok = count_tokens(history_full_text)
    history_avg_tok = (count_tokens("Nobody has spoken yet.") + history_full_tok) // 2

    # Instructions
    rating_instr_tok = count_tokens(
        "Output a single integer from 0 to 10 ranking how badly you want to speak "
        "right now. This will determine who speaks next. Alternatively, output -1 "
        "to leave the location and end your time here. Output one integer and "
        "nothing else."
    )
    speaking_instr_tok = count_tokens(
        "It is your turn to speak now. Have a realistic conversation with those "
        "present. Keep it short, only a sentence or two, unless the other people "
        "expect you to say more. Aim for a grounded improvisational style — "
        "everything should be deeply realistic and a slow-burn."
    )

    # Location choice
    loc_instr_tok = count_tokens(
        f"It is morning on day {day}. Choose a location to go to.\n"
        "Only say the name of the location and nothing else.\n\n"
    )
    loc_list_tok = count_tokens("Locations:\n" + _location_list(LOCATIONS))

    # Memory save
    mem_save_context_tok = count_tokens(
        f"It is the end of the morning on day {day}. You were at {location.name}.\n\n"
    )
    mem_save_instr_tok = count_tokens(
        "Summarize the conversation into a couple sentences to recall for the "
        "future. Make sure to record future appointments (both day and time of day), and "
        "updated opinions on the villmagers you talked to."
    )

    # Call counts
    n_memories = max(0, (day - 1) * PHASES)
    loc_calls = PHASES * N_VILLAGERS
    total_rating_calls = sum(g.size * g.turns * g.per_day for g in params.conversations)
    total_speaking_calls = sum(g.turns * g.per_day for g in params.conversations)
    total_mem_calls = params.total_villagers_in_convs_per_day
    avg_turns_weighted = (sum(g.turns * g.per_day for g in params.conversations)
                          / params.total_convs_per_day)

    # Build all rows and accumulate grand total
    grand_total = [0.0]  # mutable ref for _print_section_block

    print(f"\n{'=' * 84}")
    print(f"  PROMPT COMPONENT BREAKDOWN — Day {day}, {params.name}")
    print(f"  Memories per villager: ~{n_memories}")
    print(f"{'=' * 84}")
    print()
    print(f"  {'Component':<36s} {'tok/call':>8s} {'calls':>7s} {'total tok':>10s} {'cost':>10s} {'% total':>8s}")
    print(f"  {'─'*36} {'─'*8} {'─'*7} {'─'*10} {'─'*10} {'─'*8}")

    # We need grand_total computed first for percentages — do two passes
    all_rows = []

    # Location
    for label, tag, tok in [
        ("system prompt", TAG_SYSTEM, sys_tok),
        ("description + header", TAG_DESCRIPTION, avg_desc_tok),
        ("memories", TAG_MEMORIES, mem_tok),
        ("instruction", TAG_INSTRUCTION, loc_instr_tok),
        ("location list", TAG_LOC_LIST, loc_list_tok),
    ]:
        r = _component_row(label, tag, tok, loc_calls, SONNET.input)
        all_rows.append(("LOCATION CHOICE (Sonnet)", None, "input", *r))
    r = _component_row("output", TAG_OUTPUT, params.out_location, loc_calls, SONNET.output)
    all_rows.append(("LOCATION CHOICE (Sonnet)", None, "output", *r))

    # Rating
    rating_note = (f"  {total_rating_calls:.0f} calls = "
                   f"{params.total_convs_per_day:.0f} convos x {avg_turns_weighted:.0f} turns x "
                   f"avg {params.total_villagers_in_convs_per_day/params.total_convs_per_day:.1f} villagers")
    for label, tag, tok in [
        ("system prompt", TAG_SYSTEM, sys_tok),
        ("shared: header (time/loc/names)", TAG_HEADER, shared_header_tok),
        ("shared: conversation history", TAG_HISTORY, history_avg_tok),
        ("per-char: name line", TAG_NAME, name_tok),
        ("per-char: description + header", TAG_DESCRIPTION, avg_desc_tok),
        ("per-char: memories", TAG_MEMORIES, mem_tok),
        ("per-char: rating instruction", TAG_INSTRUCTION, rating_instr_tok),
    ]:
        r = _component_row(label, tag, tok, total_rating_calls, SONNET.input)
        all_rows.append(("DESIRE RATING (Sonnet)", rating_note, "input", *r))
    r = _component_row("output", TAG_OUTPUT, params.out_rating, total_rating_calls, SONNET.output)
    all_rows.append(("DESIRE RATING (Sonnet)", rating_note, "output", *r))

    # Speaking
    speaking_note = (f"  {total_speaking_calls:.0f} calls = "
                     f"{params.total_convs_per_day:.0f} convos x {avg_turns_weighted:.0f} turns x 1 speaker")
    for label, tag, tok in [
        ("system prompt", TAG_SYSTEM, sys_tok),
        ("shared: header (time/loc/names)", TAG_HEADER, shared_header_tok),
        ("shared: conversation history", TAG_HISTORY, history_avg_tok),
        ("per-char: name line", TAG_NAME, name_tok),
        ("per-char: description + header", TAG_DESCRIPTION, avg_desc_tok),
        ("per-char: memories", TAG_MEMORIES, mem_tok),
        ("per-char: speaking instruction", TAG_INSTRUCTION, speaking_instr_tok),
    ]:
        r = _component_row(label, tag, tok, total_speaking_calls, OPUS.input)
        all_rows.append(("SPEAKING (Opus)", speaking_note, "input", *r))
    r = _component_row("output", TAG_OUTPUT, params.out_speaking, total_speaking_calls, OPUS.output)
    all_rows.append(("SPEAKING (Opus)", speaking_note, "output", *r))

    # Memory
    for label, tag, tok in [
        ("system prompt", TAG_SYSTEM, sys_tok),
        ("description + header", TAG_DESCRIPTION, avg_desc_tok),
        ("current memories", TAG_MEMORIES, mem_tok),
        ("phase/location context", TAG_CONTEXT, mem_save_context_tok),
        ("conversation history", TAG_HISTORY, history_full_tok),
        ("instruction", TAG_INSTRUCTION, mem_save_instr_tok),
    ]:
        r = _component_row(label, tag, tok, total_mem_calls, SONNET.input)
        all_rows.append(("MEMORY SAVE (Sonnet)", None, "input", *r))
    r = _component_row("output", TAG_OUTPUT, params.out_memory, total_mem_calls, SONNET.output)
    all_rows.append(("MEMORY SAVE (Sonnet)", None, "output", *r))

    grand_total[0] = sum(row[8] for row in all_rows)

    # Print
    current_header = None
    for section_title, note, kind, label, tag, tok, calls, total_tok, dollars in all_rows:
        if section_title != current_header:
            current_header = section_title
            print(f"\n  {section_title}")
            if note:
                print(f"  {note}")
        pct_str = f"{dollars/grand_total[0]*100:6.1f}%" if grand_total[0] > 0 else ""
        if kind == "output":
            print(f"    {'→ ' + label:<34s} {tok:>8} {calls:>7.0f} {total_tok:>10.0f} ${dollars:>8.4f} {pct_str:>8s}")
        else:
            print(f"    {label:<36s} {tok:>8} {calls:>7.0f} {total_tok:>10.0f} ${dollars:>8.4f} {pct_str:>8s}")

    print(f"\n  {'─'*36} {'─'*8} {'─'*7} {'─'*10} {'─'*10} {'─'*8}")
    print(f"  {'GRAND TOTAL':<36s} {'':>8s} {'':>7s} {'':>10s} ${grand_total[0]:>8.4f} {'100.0%':>8s}")

    # Aggregate by tag
    agg: dict[str, float] = {}
    for row in all_rows:
        tag = row[4]
        dollars = row[8]
        agg[tag] = agg.get(tag, 0) + dollars

    print(f"\n  {'─'*84}")
    print(f"  AGGREGATED BY COMPONENT (across all call types)")
    print(f"  {'─'*84}")
    for tag, dollars in sorted(agg.items(), key=lambda x: -x[1]):
        print(f"    {tag:<36s} ${dollars:>8.4f}  {pct(dollars, grand_total[0]):>8s}")
    print(f"    {'─'*36} {'─'*10} {'─'*8}")
    print(f"    {'TOTAL':<36s} ${grand_total[0]:>8.4f}  {'100.0%':>8s}")


# ── Optimization results ─────────────────────────────────────────────

def print_optimization_results(results):
    """Print the top-N optimization results."""
    from cost_analysis.optimizer import StrategyResult

    print(f"\n{'=' * 84}")
    print(f"  OPTIMAL CACHING STRATEGIES (top {len(results)})")
    print(f"{'=' * 84}")

    for rank, r in enumerate(results, 1):
        s = r.strategy
        print(f"\n  #{rank}  Total: {fmt_dollar(r.projected_cost)}/day"
              f"  (vs no-cache: {r.savings_vs_nocache_pct:+.1f}%"
              f"  vs current: {r.savings_vs_current_pct:+.1f}%)")
        print(f"  {'─' * 78}")
        print(f"    Rating   ({fmt_dollar(r.rating_cost)}):   {s.rating.describe()}")
        print(f"    Speaking ({fmt_dollar(r.speaking_cost)}):   {s.speaking.describe()}")
        print(f"    Location ({fmt_dollar(r.location_cost)}):   {s.location.describe()}")
        print(f"    Memory   ({fmt_dollar(r.memory_cost)}):   {s.memory.describe()}")

    if results:
        best = results[0]
        print(f"\n  Recommendation: strategy #{1}")
        print(f"    Projected daily cost: {fmt_dollar(best.projected_cost)}")
        print(f"    Savings vs no-cache:  {best.savings_vs_nocache_pct:+.1f}%")
        print(f"    Savings vs current:   {best.savings_vs_current_pct:+.1f}%")
    print()


# ── Main report ──────────────────────────────────────────────────────

def print_report(day: int, run_optimizer: bool = False):
    from cost_analysis.optimizer import optimize

    max_turns_needed = max(
        max(g.turns for g in p.conversations)
        for p in [UNIFORM_PARAMS, OBSERVED_PARAMS]
    )
    measurements = measure_tokens(day, max_turns_needed)

    print("=" * 72)
    print(f"  VILLMAGE COST ANALYSIS — Day {day}")
    print(f"  Memories per villager: ~{max(0, (day - 1) * PHASES)}")
    print("=" * 72)

    # Token measurements
    print(f"\n  Token measurements (from actual prompts + descriptions):")
    print(f"    System prompt:        {measurements.sys_tokens:>4} tokens")
    print(f"    Location choice user: {measurements.loc_user_tokens:>4} tokens")
    print(f"    Shared prefix (avg):  {measurements.avg_shared:>4} tokens "
          f"(turn 1: {measurements.shared_tokens_by_turn[0]}, "
          f"turn {max_turns_needed}: {measurements.shared_tokens_by_turn[-1]})")
    print(f"    Per-char rating:      {measurements.avg_char_tokens:>4} tokens "
          f"(range: {measurements.min_char_tokens}–{measurements.max_char_tokens})")
    print(f"    Per-char speaking:    {measurements.speaking_char_tokens:>4} tokens")
    print(f"    Memory save user:     {measurements.mem_user_tokens:>4} tokens")

    # Run optimizer for each param set if requested
    opt_observed = None
    opt_uniform = None
    if run_optimizer:
        opt_results_o = optimize(OBSERVED_PARAMS, day=day, top_n=1)
        opt_observed = opt_results_o[0] if opt_results_o else None
        opt_results_u = optimize(UNIFORM_PARAMS, day=day, top_n=1)
        opt_uniform = opt_results_u[0] if opt_results_u else None

    # Component breakdown
    print_component_breakdown(day, OBSERVED_PARAMS, max_turns_needed)

    # Both parameter sets
    for params in [UNIFORM_PARAMS, OBSERVED_PARAMS]:
        no_cache, current, char_first = compute_costs(measurements, params)
        opt = opt_uniform if params is UNIFORM_PARAMS else opt_observed
        print_params_report(
            "MODEL" if params is UNIFORM_PARAMS else "ACTUAL",
            params, measurements, no_cache, current, char_first,
            optimized=opt,
        )

    # Side-by-side delta
    no_cache_u, current_u, char_first_u = compute_costs(measurements, UNIFORM_PARAMS)
    no_cache_o, current_o, char_first_o = compute_costs(measurements, OBSERVED_PARAMS)

    opt_hdr = f" {'Optimized':>10s}" if run_optimizer else ""
    opt_sep = f" {'─'*10}" if run_optimizer else ""
    w = 84 if run_optimizer else 72

    print(f"\n{'─' * w}")
    print(f"  Uniform vs Observed (no-cache baseline)")
    print(f"{'─' * w}")
    print(f"  {'':24s} {'Uniform':>10s} {'Observed':>10s} {'Ratio':>10s}{opt_hdr}")
    print(f"  {'─'*24} {'─'*10} {'─'*10} {'─'*10}{opt_sep}")
    rows = [
        ("Total (no cache)", no_cache_u.total, no_cache_o.total, None),
        ("Total (current)", current_u.total, current_o.total, None),
        ("Total (char-first)", char_first_u.total, char_first_o.total, None),
    ]
    if run_optimizer and opt_uniform and opt_observed:
        rows.append(("Total (optimized)", opt_uniform.projected_cost, opt_observed.projected_cost, None))
    for label, u, o, _ in rows:
        ratio = o / u if u > 0 else 0
        opt_col = ""
        if run_optimizer and "optimized" not in label:
            opt_col = f" {'':>10s}"
        print(f"  {label:24s} {fmt_dollar(u):>10s} {fmt_dollar(o):>10s} {ratio:>9.2f}x{opt_col}")

    # Key assumption mismatches
    print(f"\n  Key assumption mismatches (day 1 actual vs uniform model):")
    u_convs = UNIFORM_PARAMS.total_convs_per_day
    o_convs = OBSERVED_PARAMS.total_convs_per_day
    u_avg_group = UNIFORM_PARAMS.total_villagers_in_convs_per_day / u_convs
    o_avg_group = OBSERVED_PARAMS.total_villagers_in_convs_per_day / o_convs
    u_avg_turns = sum(g.turns * g.per_day for g in UNIFORM_PARAMS.conversations) / u_convs
    o_avg_turns = sum(g.turns * g.per_day for g in OBSERVED_PARAMS.conversations) / o_convs
    print(f"    {'':30s} {'Uniform':>10s} {'Observed':>10s}")
    print(f"    {'Conversations/day':30s} {u_convs:>10.1f} {o_convs:>10.0f}")
    print(f"    {'Avg group size':30s} {u_avg_group:>10.2f} {o_avg_group:>10.2f}")
    print(f"    {'Avg turns/conversation':30s} {u_avg_turns:>10.1f} {o_avg_turns:>10.1f}")
    print(f"    {'Speech output tokens':30s} "
          f"{UNIFORM_PARAMS.out_speaking:>10} {OBSERVED_PARAMS.out_speaking:>10}")
    print(f"    {'Memory output tokens':30s} "
          f"{UNIFORM_PARAMS.out_memory:>10} {OBSERVED_PARAMS.out_memory:>10}")
    print(f"    {'Location distribution':30s} {'uniform':>10s} {'K&C=54%':>10s}")

    # Multi-day projection
    opt_col_hdr = f"  {'Optimized':>10s}" if run_optimizer else ""
    print(f"\n{'─' * w}")
    print(f"  Multi-day projection (observed params)")
    print(f"{'─' * w}")
    print(f"  {'Day':>5s}  {'No cache':>10s}  {'Current':>10s}  {'Char-first':>10s}{opt_col_hdr}")
    for d in [1, 3, 5, 10]:
        md = measure_tokens(d, max_turns_needed)
        n, c, f = compute_costs(md, OBSERVED_PARAMS)
        opt_val = ""
        if run_optimizer:
            opt_d = optimize(OBSERVED_PARAMS, day=d, top_n=1)
            opt_val = f"  {fmt_dollar(opt_d[0].projected_cost):>10s}" if opt_d else ""
        print(f"  {d:>5d}  {fmt_dollar(n.total):>10s}  {fmt_dollar(c.total):>10s}  {fmt_dollar(f.total):>10s}{opt_val}")

    print()
