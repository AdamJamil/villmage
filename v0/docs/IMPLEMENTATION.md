# Implementation

## Stack & Files

Python 3.12, `anthropic` async SDK, `trio`.

```
main.py          — entry point, CLI args, day/phase loop
simulation.py    — phase orchestration, conversation engine
llm.py           — AsyncAnthropic client, model-routed API wrappers
prompts.py       — all prompt templates as functions
data.py          — Villager/Location dataclasses, character defs, location list
output.py        — terminal formatting + transcript file writer
```

## Data Model

```python
@dataclass
class Villager:
    name: str
    description: str      # profession + appearance + desires + background + relationships
    memories: list[str]   # grows unbounded, each entry is one post-conversation summary

@dataclass
class Location:
    name: str
    description: str      # one-line flavor text
```

**8 villagers:** Margot, Denn, Sable, Pell, Orla, Aldric, Wren, Ham.

**5 locations:** The Kettle & Crow, Moss Square, The Calloway Academy, Moss & Measure, Fenwick Meadow.

Each villager's `description` includes all four sections from DESIGN.md (profession, appearance, desires, background) plus their relevant relationship entries, rewritten from their POV. Example for Orla:

> *Your relationship with Margot: You and Margot have an unspoken standoff — you're the same kind of stubborn and neither of you will blink first. She once left a free tin of tea outside your workshop. You used it but never mentioned it.*

This is a one-time data prep step — tedious but important for immersion.

## Game Loop

```
for each day (1..N):
  for each phase (morning, afternoon, evening):

    1. LOCATION SELECTION — 8 parallel Sonnet calls
       Each villager picks a location blind (no knowledge of others' choices).
       Parse response, match to location list. Fallback: random.
       Result: dict[Location, list[Villager]]

    2. SOLO LOCATIONS
       Villagers alone at a location save a memory:
       "Nobody else appeared at {location}." No LLM call needed.

    3. CONVERSATIONS — parallel across locations, sequential turns within
       Skip locations with <2 villagers.
       Each qualifying location runs the conversation engine (below).
       Independent locations run concurrently in a trio nursery.

    4. MEMORY SAVING — parallel Sonnet calls, done inside each conversation
       Every participant saves a memory at conversation end.
       Early leavers get history truncated to their departure point.
```

### Trio concurrency pattern

Every "parallel batch" uses the same shape: a nursery that spawns tasks writing
into a shared dict, then reads from it after the nursery exits.

```python
async def parallel_calls(items, fn):
    """Run fn(item) for each item, return {item: result}."""
    results = {}
    async def _run(item):
        results[item] = await fn(item)
    async with trio.open_nursery() as nursery:
        for item in items:
            nursery.start_soon(_run, item)
    return results
```

This replaces `asyncio.gather` everywhere — location choices, ratings, memory saves,
and running conversations at multiple locations concurrently.

## Conversation Engine

This is the core of the simulation. One instance runs per location per phase.

```python
async def run_conversation(location, villagers, day, phase):
    history: list[str] = []          # "Sable: ..." or "Pell left The Kettle & Crow."
    present: list[Villager] = list(villagers)
    departure_history: dict[str, list[str]] = {}  # name -> history snapshot at departure

    for turn in range(1, 21):
        if len(present) < 2:
            break

        # 1. All present villagers rate desire to speak (parallel Sonnet)
        ratings: dict[Villager, int] = {}
        async with trio.open_nursery() as nursery:
            for v in present:
                nursery.start_soon(rate_and_store, v, location, history, ratings)

        # 2. Process departures (-1)
        for v, r in ratings.items():
            if r == -1:
                present.remove(v)
                departure_history[v.name] = list(history)
                history.append(f"{v.name} left {location.name}.")

        if len(present) < 2:
            break

        # 3. Highest remaining score speaks (random tiebreak)
        candidates = {v: r for v, r in ratings.items() if v in present}
        max_score = max(candidates.values())
        speaker = random.choice([v for v, r in candidates.items() if r == max_score])

        # 4. Speaker speaks (single Opus call)
        utterance = await get_speech(speaker, location, history, present)
        history.append(f"{speaker.name}: {utterance}")

    # End scene
    history.append(f"The {phase} has ended.")

    # Save memories (parallel Sonnet via nursery)
    async with trio.open_nursery() as nursery:
        for v in villagers:
            h = departure_history.get(v.name, history)  # truncated or full
            nursery.start_soon(save_memory, v, location, h)
```

### Edge cases handled

- **Tie in ratings**: random choice among tied highest.
- **All rate 0**: someone still speaks (0 is "I don't want to" but not "I'm leaving"). Only -1 exits.
- **Everyone leaves on the same turn**: conversation ends, no more speech. All save memories.
- **1 villager at location**: no conversation, but they save a memory: "Nobody else appeared at {location}."
- **0 villagers**: skipped.
- **Leaver was highest scorer**: they leave (removed before speaking phase), next-highest speaks.

## Prompts

### Cache ordering

Prompts are ordered for Anthropic prompt caching. The cache matches on exact
prefix, so shared content goes first and per-character content goes last.

For conversation calls (rating + speaking), all villagers at the same location
in the same turn share the system prompt, time/location context, and
conversation history. That shared prefix is cached across parallel calls.

```
SYSTEM (cached across entire simulation):
  village preamble — never changes

USER (ordered for caching):
  1. shared context — same for all villagers at this location+turn (cacheable)
     time, location, who's here, conversation history
  2. character context — different per villager
     description, relationships, memories
  3. instruction — same for all (but after the varying part, so not cached)
```

### System prompt (same for ALL calls, entire simulation)

```
You are a villmager in {VILLAGE_NAME}. Your goal is simply to live a
normal life and socialize with other villmagers.
```

### Location choice (user msg — Sonnet)

No caching benefit here — each villager's call is independent and the
shared portion (location list) is small. Character info first is fine.

```
Here is a description of your character:
{DESCRIPTION}
Never contradict it, but feel free to extend it where appropriate.

Here are your memories:
{MEMORIES_LIST or "You have no memories yet."}

It is {PHASE} on day {DAY}. Choose a location to go to.
Only say the name of the location and nothing else.

Locations:
- The Kettle & Crow — Sable's tavern. Smells like bread and woodsmoke. The unofficial living room of the village.
- Moss Square — The open town center. A few benches, an old well nobody uses, and a notice board Pell maintains with excessive enthusiasm.
- The Calloway Academy — Wren's schoolhouse and lending library. Cramped, quiet, and smells like old paper.
- Moss & Measure — Aldric's general store. Ruthlessly organized. Everything has a price tag and a place.
- Fenwick Meadow — The grassy hillside at the edge of town. Wildflowers in spring, golden in summer, muddy in autumn.
```

### Desire rating (user msg — Sonnet)

Shared prefix (cacheable across all villagers at this location+turn):
```
It is {PHASE} on day {DAY}.
You are currently at {LOCATION}.
The following villmagers are here: {ALL_NAMES}.

{"Nobody has spoken yet." | "Here is the conversation so far:\n" + HISTORY}
```

Per-character (varies):
```
You are {NAME}.

Here is a description of your character:
{DESCRIPTION}
Never contradict it, but feel free to extend it where appropriate.

Here are your memories:
{MEMORIES_LIST or "You have no memories yet."}

Output a single integer from 0 to 10 ranking how badly you want to speak
right now. This will determine who speaks next. Alternatively, output -1
to leave the location and end your time here. Output one integer and
nothing else.
```

### Speaking (user msg — Opus)

Same cache-first structure as rating.

Shared prefix:
```
It is {PHASE} on day {DAY}.
You are currently at {LOCATION}.
The following villmagers are here: {ALL_NAMES}.

Here is the conversation so far:
{HISTORY | "Nobody has spoken yet."}
```

Per-character:
```
You are {NAME}.

Here is a description of your character:
{DESCRIPTION}
Never contradict it, but feel free to extend it where appropriate.

Here are your memories:
{MEMORIES_LIST or "You have no memories yet."}

It is your turn to speak now. Have a realistic conversation with those
present. Keep it short, only a sentence or two, unless the other people
expect you to say more. Aim for a grounded improvisational style —
everything should be deeply realistic and a slow-burn.
```

### Memory save (user msg — Sonnet)

No caching benefit — one call per villager with different history slices.

```
Here is a description of your character:
{DESCRIPTION}

Here are your current memories:
{MEMORIES_LIST or "You have no memories yet."}

It is the end of the {PHASE} on day {DAY}. You were at {LOCATION}.

Here is the conversation:
{HISTORY}

Summarize the conversation into a couple sentences to recall for the
future. Make sure to record future appointments (both day and time of day), and
updated opinions on the villmagers you talked to.
```

### Memory format

Memories are stored as a numbered list:
```
1. [Day 1, morning] ...
2. [Day 1, afternoon] ...
```

## Output

### Terminal (real-time)

Same content as the transcript file but with ANSI colors: villager names colored,
locations bold, ratings dim. Nothing fancy.

### Transcript file

Written to `transcripts/day_{N}.md` — markdown formatted, appended in real-time (crash-safe).

```markdown
# Day 1

---

## Morning

**The Kettle & Crow** — Margot, Sable, Ham
**Moss & Measure** — Pell, Aldric
**The Calloway Academy** — Wren *(alone)*
**Moss Square** — Denn *(alone)*
**Fenwick Meadow** — *empty*

---

### The Kettle & Crow — Morning
*Margot, Sable, Ham — {N} turns*

**{speaker}** `[{score}]`: {LLM-generated dialogue}

**{speaker}** `[{score}]`: {LLM-generated dialogue}

*{name} left.*

**{speaker}** `[{score}]`: {LLM-generated dialogue}

<details><summary>Memories saved</summary>

- **Margot**: [Day 1, morning] {LLM-generated summary}
- **Sable**: [Day 1, morning] {LLM-generated summary}
- **Ham**: [Day 1, morning] {LLM-generated summary}

</details>

---

### Moss & Measure — Morning
*Pell, Aldric — {N} turns*

...

---

## Afternoon

...

---

## Evening

...

---

## End of Day 1

### Where everyone went
| | Morning | Afternoon | Evening |
|---|---|---|---|
| Margot | {location} | {location} | {location} |
| Denn | ... | ... | ... |
| ... | | | |

### Social interactions
Who shared a location (conversation count):
| | Margot | Denn | Sable | Pell | Orla | Aldric | Wren | Ham |
|---|---|---|---|---|---|---|---|---|
| Margot | - | {n} | {n} | ... | | | | |
| ... | | | | | | | | |

### All memories at end of day
<details><summary>Margot ({N} memories)</summary>

1. [Day 1, morning] {LLM-generated summary}
2. [Day 1, afternoon] {LLM-generated summary}
3. ...

</details>

<details><summary>Denn ({N} memories)</summary>

...

</details>
```

## Model Routing

| Task | Model | Typical tokens (in/out) | Why |
|------|-------|------------------------|-----|
| Location choice | Sonnet 4.6 | ~300 / ~10 | Structured, trivial output |
| Desire rating | Sonnet 4.6 | ~400 / ~5 | Single integer |
| **Speaking** | **Opus 4.6** | ~500 / ~60 | Core creative output — needs personality depth |
| Memory save | Sonnet 4.6 | ~600 / ~80 | Summarization |

### Rough cost per game-day

3 phases/day, ~2.5 conversations per phase, ~10 turns per conversation:

- 3 phases x 8 location calls = 24 Sonnet calls
- ~7.5 conversations x 10 turns x ~3 villagers rating = ~225 Sonnet calls
- ~7.5 conversations x ~6 memory saves each = ~45 Sonnet calls
- ~7.5 conversations x 10 turns x 1 speaker = **~75 Opus calls**
- **Sonnet**: ~294 calls, ~130K input tokens, ~12K output → ~$0.57
- **Opus**: ~75 calls, ~64K input tokens, ~3K output → ~$1.19
- **Total: ~$1.75/game-day** (grows as memories accumulate and conversation history lengthens)

## Parsing & Error Handling

| Output | Strategy |
|--------|----------|
| Location name | Strip whitespace, case-insensitive substring match against location names. No match → retry once with stricter prompt. Still no match → random. |
| Desire rating | Regex for `-?\d+`, clamp to [-1, 10]. Parse fail → 0. |
| Speech | Raw output, no parsing. |
| Memory | Raw output, prepend `[Day {N}, {phase}]` tag, append to villager's list. |
| API errors | SDK built-in retry with backoff. |
