"""Cost computation for caching strategies."""

from __future__ import annotations

from dataclasses import dataclass

from cost_analysis.measurement import TokenMeasurement
from cost_analysis.pricing import SONNET, OPUS, cost
from cost_analysis.scenarios import SimParams, PHASES, N_VILLAGERS


@dataclass
class CostBreakdown:
    location: float = 0.0
    rating_input: float = 0.0
    rating_output: float = 0.0
    speaking_input: float = 0.0
    speaking_output: float = 0.0
    memory: float = 0.0

    @property
    def rating(self) -> float:
        return self.rating_input + self.rating_output

    @property
    def speaking(self) -> float:
        return self.speaking_input + self.speaking_output

    @property
    def total(self) -> float:
        return self.location + self.rating + self.speaking + self.memory


def _extrapolate_shared_tokens(
    shared_by_turn: list[int], needed: int,
) -> list[int]:
    """Extend shared_tokens_by_turn to *needed* entries via linear extrapolation."""
    if needed <= len(shared_by_turn):
        return list(shared_by_turn[:needed])
    if len(shared_by_turn) >= 2:
        growth = (shared_by_turn[-1] - shared_by_turn[0]) / (len(shared_by_turn) - 1)
    else:
        growth = 40
    extended = list(shared_by_turn)
    for i in range(needed - len(extended)):
        extended.append(extended[-1] + int(growth * (i + 1)))
    return extended


def compute_costs(
    measurements: TokenMeasurement,
    params: SimParams,
) -> tuple[CostBreakdown, CostBreakdown, CostBreakdown]:
    """Compute costs for (no_cache, current_scheme, char_first).

    This preserves the original three hardcoded strategies for backward
    compatibility with the comparison report.
    """
    no_cache = CostBreakdown()
    current = CostBreakdown()
    char_first = CostBreakdown()

    sys_tok = measurements.sys_tokens
    char_rating = measurements.avg_char_tokens
    char_speaking = measurements.speaking_char_tokens

    # -- Location selection: always PHASES * N_VILLAGERS Sonnet calls, no caching --
    loc_input = PHASES * N_VILLAGERS * (sys_tok + measurements.loc_user_tokens)
    loc_output = PHASES * N_VILLAGERS * params.out_location
    loc_cost_val = cost(loc_input, SONNET.input) + cost(loc_output, SONNET.output)
    no_cache.location = current.location = char_first.location = loc_cost_val

    # -- Rating + Speaking: iterate conversation groups --
    for group in params.conversations:
        group_size = group.size
        convs_per_day = group.per_day
        turns = group.turns

        shared_by_turn = _extrapolate_shared_tokens(
            measurements.shared_tokens_by_turn, turns,
        )

        for t in range(turns):
            shared_tok = shared_by_turn[t]
            full_rating_in = sys_tok + shared_tok + char_rating
            full_speaking_in = sys_tok + shared_tok + char_speaking

            # Rating (Sonnet, group_size calls per turn)
            no_cache.rating_input += convs_per_day * group_size * cost(full_rating_in, SONNET.input)

            # Current scheme: cross-turn + within-turn prefix sharing
            cached_prefix = sys_tok + shared_tok
            if t == 0:
                prefix_read = 0
                prefix_write = cached_prefix
            else:
                prev_prefix = sys_tok + shared_by_turn[t - 1]
                prefix_read = prev_prefix
                prefix_write = cached_prefix - prev_prefix

            current.rating_input += convs_per_day * (
                cost(prefix_read, SONNET.cache_read)
                + cost(prefix_write, SONNET.cache_write)
                + (group_size - 1) * cost(cached_prefix, SONNET.cache_read)
                + group_size * cost(char_rating, SONNET.input)
            )

            # Char-first scheme: character description cached across turns
            cached_char = sys_tok + char_rating
            if t == 0:
                char_first.rating_input += convs_per_day * group_size * (
                    cost(cached_char, SONNET.cache_write)
                    + cost(shared_tok, SONNET.input)
                )
            else:
                char_first.rating_input += convs_per_day * group_size * (
                    cost(cached_char, SONNET.cache_read)
                    + cost(shared_tok, SONNET.input)
                )

            out_r = convs_per_day * group_size * cost(params.out_rating, SONNET.output)
            no_cache.rating_output += out_r
            current.rating_output += out_r
            char_first.rating_output += out_r

            # Speaking (Opus, 1 call per turn)
            no_cache.speaking_input += convs_per_day * cost(full_speaking_in, OPUS.input)
            current.speaking_input += convs_per_day * cost(full_speaking_in, OPUS.input)

            cached_speak = sys_tok + char_speaking
            if t == 0:
                char_first.speaking_input += convs_per_day * (
                    cost(cached_speak, OPUS.cache_write)
                    + cost(shared_tok, OPUS.input)
                )
            else:
                char_first.speaking_input += convs_per_day * (
                    cost(cached_speak, OPUS.cache_read)
                    + cost(shared_tok, OPUS.input)
                )

            out_s = convs_per_day * cost(params.out_speaking, OPUS.output)
            no_cache.speaking_output += out_s
            current.speaking_output += out_s
            char_first.speaking_output += out_s

    # -- Memory saves: Sonnet, no caching --
    vill_in_conv = params.total_villagers_in_convs_per_day
    mem_total_in = vill_in_conv * (sys_tok + measurements.mem_user_tokens)
    mem_total_out = vill_in_conv * params.out_memory
    mem_cost_val = cost(mem_total_in, SONNET.input) + cost(mem_total_out, SONNET.output)
    no_cache.memory = current.memory = char_first.memory = mem_cost_val

    return no_cache, current, char_first
