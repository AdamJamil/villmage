"""All prompt templates for the Villmage simulation."""

from data import Villager, Location

VILLAGE_NAME = "Villmage"


def system_prompt() -> str:
    return (
        f"You are a villmager in {VILLAGE_NAME}. Your goal is simply to live a "
        "normal life and socialize with other villmagers."
    )


def _format_memories(villager: Villager) -> str:
    if not villager.memories:
        return "You have no memories yet."
    return "\n".join(
        f"{i}. {m}" for i, m in enumerate(villager.memories, 1)
    )


def _location_list(locations: list[Location]) -> str:
    return "\n".join(f"- {loc.name} — {loc.description}" for loc in locations)


# ---------------------------------------------------------------------------
# Location choice (Sonnet) — no caching benefit, character-first
# ---------------------------------------------------------------------------

def location_choice_user(
    villager: Villager,
    day: int,
    phase: str,
    locations: list[Location],
) -> str:
    return (
        f"Here is a description of your character:\n{villager.description}\n"
        "Never contradict it, but feel free to extend it where appropriate.\n\n"
        f"Here are your memories:\n{_format_memories(villager)}\n\n"
        f"It is {phase} on day {day}. Choose a location to go to.\n"
        "Only say the name of the location and nothing else.\n\n"
        f"Locations:\n{_location_list(locations)}"
    )


# ---------------------------------------------------------------------------
# Desire rating (Sonnet) — shared prefix for caching
# ---------------------------------------------------------------------------

def rating_shared(
    day: int,
    phase: str,
    location: Location,
    all_names: list[str],
    history: list[str],
) -> str:
    names_str = ", ".join(all_names)
    if history:
        conv = "Here is the conversation so far:\n" + "\n".join(history)
    else:
        conv = "Nobody has spoken yet."
    return (
        f"It is {phase} on day {day}.\n"
        f"You are currently at {location.name}.\n"
        f"The following villmagers are here: {names_str}.\n\n"
        f"{conv}"
    )


def rating_character(villager: Villager) -> str:
    return (
        f"You are {villager.name}.\n\n"
        f"Here is a description of your character:\n{villager.description}\n"
        "Never contradict it, but feel free to extend it where appropriate.\n\n"
        f"Here are your memories:\n{_format_memories(villager)}\n\n"
        "Output a single integer from 0 to 10 ranking how badly you want to speak "
        "right now. This will determine who speaks next. Alternatively, output -1 "
        "to leave the location and end your time here. Output one integer and "
        "nothing else."
    )


# ---------------------------------------------------------------------------
# Speaking (Opus) — shared prefix for caching
# ---------------------------------------------------------------------------

def speaking_shared(
    day: int,
    phase: str,
    location: Location,
    all_names: list[str],
    history: list[str],
) -> str:
    names_str = ", ".join(all_names)
    if history:
        conv = "Here is the conversation so far:\n" + "\n".join(history)
    else:
        conv = "Nobody has spoken yet."
    return (
        f"It is {phase} on day {day}.\n"
        f"You are currently at {location.name}.\n"
        f"The following villmagers are here: {names_str}.\n\n"
        f"{conv}"
    )


def speaking_character(villager: Villager) -> str:
    return (
        f"You are {villager.name}.\n\n"
        f"Here is a description of your character:\n{villager.description}\n"
        "Never contradict it, but feel free to extend it where appropriate.\n\n"
        f"Here are your memories:\n{_format_memories(villager)}\n\n"
        "It is your turn to speak now. Have a realistic conversation with those "
        "present. Keep it short, only a sentence or two, unless the other people "
        "expect you to say more. Aim for a grounded improvisational style — "
        "everything should be deeply realistic and a slow-burn."
    )


# ---------------------------------------------------------------------------
# Memory save (Sonnet) — no caching benefit
# ---------------------------------------------------------------------------

def memory_save_user(
    villager: Villager,
    day: int,
    phase: str,
    location: Location,
    history: list[str],
) -> str:
    return (
        f"Here is a description of your character:\n{villager.description}\n\n"
        f"Here are your current memories:\n{_format_memories(villager)}\n\n"
        f"It is the end of the {phase} on day {day}. You were at {location.name}.\n\n"
        f"Here is the conversation:\n" + "\n".join(history) + "\n\n"
        "Summarize the conversation into a couple sentences to recall for the "
        "future. Make sure to record future appointments (both day and time of day), and "
        "updated opinions on the villmagers you talked to."
    )
