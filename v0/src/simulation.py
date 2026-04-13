"""Phase orchestration and conversation engine."""

import random
import re
from typing import Dict, List, Tuple

import trio

from data import Villager, Location
from llm import gemini_call
from prompts import (
    system_prompt,
    location_choice_user,
    rating_shared,
    rating_character,
    speaking_shared,
    speaking_character,
    memory_save_user,
)
from output import Output

MAX_TURNS = 20
SYSTEM = system_prompt()


# ---------------------------------------------------------------------------
# Parallel helper
# ---------------------------------------------------------------------------

async def parallel_calls(items, fn):
    """Run fn(item) for each item, return {item: result}."""
    results = {}

    async def _run(item):
        results[item] = await fn(item)

    async with trio.open_nursery() as nursery:
        for item in items:
            nursery.start_soon(_run, item)
    return results


# ---------------------------------------------------------------------------
# Location selection
# ---------------------------------------------------------------------------

def _match_location(response: str, locations: list[Location]) -> Location | None:
    response_lower = response.lower().strip()
    for loc in locations:
        if loc.name.lower() in response_lower:
            return loc
    # Substring match
    for loc in locations:
        # Try matching key words
        words = loc.name.lower().split()
        if any(w in response_lower for w in words if len(w) > 3):
            return loc
    return None


async def choose_location(
    villager: Villager,
    day: int,
    phase: str,
    locations: list[Location],
) -> Location:
    user_msg = location_choice_user(villager, day, phase, locations)
    response = await gemini_call(SYSTEM, user_msg)
    loc = _match_location(response, locations)
    return loc or random.choice(locations)


async def select_locations(
    villagers: List[Villager],
    day: int,
    phase: str,
    locations: List[Location],
) -> Dict[Location, List[Villager]]:
    """All villagers choose locations in parallel. Returns {location: [villagers]}."""
    assignments: dict[Location, list[Villager]] = {loc: [] for loc in locations}

    async def _pick(v):
        return await choose_location(v, day, phase, locations)

    choices = await parallel_calls(villagers, _pick)
    for v, loc in choices.items():
        assignments[loc].append(v)
    return assignments


# ---------------------------------------------------------------------------
# Conversation engine
# ---------------------------------------------------------------------------

def _parse_rating(text: str) -> int:
    match = re.search(r"-?\d+", text)
    if not match:
        return 0
    val = int(match.group())
    return max(-1, min(10, val))


async def run_conversation(
    location: Location,
    villagers: list[Villager],
    day: int,
    phase: str,
    out: Output,
) -> dict[str, str]:
    """Run the conversation at a location. Returns {name: memory_text} for each participant."""
    history: list[str] = []
    present: list[Villager] = list(villagers)
    departure_history: dict[str, list[str]] = {}
    all_names = [v.name for v in villagers]

    out.conversation_header(day, phase, location.name, [v.name for v in villagers])

    for _ in range(1, MAX_TURNS + 1):
        if len(present) < 2:
            break

        # 1. All present villagers rate desire to speak
        present_names = [v.name for v in present]
        shared = rating_shared(day, phase, location, present_names, history)

        async def _rate(v):
            char = rating_character(v)
            text = "\n\n".join((shared, char))
            resp = await gemini_call(SYSTEM, text, max_tokens=2)
            return _parse_rating(resp)

        ratings = await parallel_calls(present, _rate)

        # Display ratings
        out.ratings_display(day, {v.name: r for v, r in ratings.items()})

        # 2. Process departures
        departing = [v for v, r in ratings.items() if r == -1]
        for v in departing:
            present.remove(v)
            departure_history[v.name] = list(history)
            history.append(f"{v.name} left {location.name}.")
            out.departure(day, v.name)

        if len(present) < 2:
            break

        # 3. Highest remaining score speaks
        candidates = {v: r for v, r in ratings.items() if v in present}
        max_score = max(candidates.values())
        tied = [v for v, r in candidates.items() if r == max_score]
        speaker = random.choice(tied)

        # 4. Speaker speaks (Opus)
        speak_shared = speaking_shared(day, phase, location, [v.name for v in present], history)
        speak_char = speaking_character(speaker)
        text = "\n\n".join((speak_shared, speak_char))
        utterance = await gemini_call(SYSTEM, text)

        history.append(f"{speaker.name}: {utterance}")
        out.speech(day, speaker.name, max_score, utterance)

    # End scene
    history.append(f"The {phase} has ended.")
    out.conversation_end()

    # Save memories in parallel
    memories: dict[str, str] = {}

    async def _save_mem(v):
        h = departure_history.get(v.name, history)
        user_msg = memory_save_user(v, day, phase, location, h)
        summary = await gemini_call(SYSTEM, user_msg)
        tag = f"[Day {day}, {phase}] {summary}"
        v.memories.append(tag)
        return tag

    mem_results = await parallel_calls(villagers, _save_mem)
    memories = {v.name: tag for v, tag in mem_results.items()}
    out.memories_saved(day, memories)
    return memories


# ---------------------------------------------------------------------------
# Phase orchestration
# ---------------------------------------------------------------------------

async def run_phase(
    villagers: List[Villager],
    locations: List[Location],
    day: int,
    phase: str,
    out: Output,
    location_tracker: Dict[Tuple[str, str], str],
) -> None:
    """Run one phase: location selection → conversations → memory saves."""
    # 1. Location selection
    assignments = await select_locations(villagers, day, phase, locations)
    out.phase_start(phase, assignments)

    # Track locations
    for loc, vs in assignments.items():
        for v in vs:
            location_tracker[(v.name, phase)] = loc.name

    # 2. Solo villagers save a memory without LLM call
    for loc, vs in assignments.items():
        if len(vs) == 1:
            v = vs[0]
            tag = f"[Day {day}, {phase}] Nobody else appeared at {loc.name}."
            v.memories.append(tag)

    # 3. Run conversations at all qualifying locations concurrently
    conv_locations = [(loc, vs) for loc, vs in assignments.items() if len(vs) >= 2]

    async with trio.open_nursery() as nursery:
        for loc, vs in conv_locations:
            nursery.start_soon(run_conversation, loc, vs, day, phase, out)
