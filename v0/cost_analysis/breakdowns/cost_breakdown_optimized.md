# Cost Breakdown (optimized caching, observed params)

**Strategy found by exhaustive search** over all section orderings and
cache breakpoint placements (`python -m cost_analysis --optimize`).

**Rating** (Sonnet, dominates cost): `system | shared_header | character | instruction | history | [BP]`
Character data and instruction are placed *between* the shared header
and history, with a single breakpoint at the end. For the same villager
across turns, the entire prefix up to the previous turn's history
endpoint is a cache read ($0.30/M). Only the new history line (~40 tok)
is a cache write ($3.75/M). This is cheaper than both:
- *Current scheme* (shared-first): caches header+history across
  villagers within a turn, but character tokens (~676–6570) always pay
  full input ($3.00/M).
- *Char-first*: caches character across turns, but history is uncached
  input every turn.

**Speaking** (Opus): `system | shared_header | history | character | instruction` — **no caching**.
Opus requires a 2048-token minimum cached prefix. On day 1, even the
full prompt is ~1588 tokens — below the threshold. Different speakers
each turn also prevents cross-turn prefix reuse. By day 5 memories
push character above 3300 tokens, but the speaker still changes every
turn so only the shared prefix (header+history, ~1534 tok max) could
be reused — still below 2048. Speaking remains uncached at all days.

**Memory** (Sonnet): `system | phase_context | history | instruction | character | [BP]`
Shared context (phase, history, instruction) is placed before
per-villager character data with a breakpoint at end. First villager's
save writes the cache; remaining villagers in the same conversation
read the shared prefix.

**Location** (Sonnet): `system | character | instruction | location_list` — no useful caching.
Each villager makes one call per phase. No prefix reuse opportunity.

> **Key finding**: the original char-first model overstates savings
> because it ignores Anthropic's minimum cache prefix (1024 Sonnet,
> 2048 Opus). The optimizer enforces these thresholds. Char-first
> appears cheaper at day 5+ in the old model, but those speaking
> savings ($0.29/day on day 1) are phantom — Opus never hits 2048
> until memories grow large, and even then speakers change each turn.

## Day 1 — $1.52/day (0 memories/villager) — saves $1.20 vs no-cache (44%)

- **Rating** — $0.44 (29%) — Sonnet, 340 calls
  - Character description + memories (cached read on turns 5+) — $0.10 (7%)
  - Conversation history (cache write: delta only) — $0.08 (5%)
  - Shared header (cached read) — $0.01 (<1%)
  - System prompt + instruction (cached read) — $0.01 (<1%)
  - Uncached input (turns 0–4, prefix < 1024) — $0.21 (14%)
  - Output — $0.03 (2%)
- **Speaking** — $0.87 (57%) — Opus, 90 calls — **uncached** (prefix < 2048)
  - Character description — $0.30 (20%)
  - Conversation history — $0.33 (22%)
  - System prompt — $0.01 (<1%)
  - Output — $0.17 (11%)
  - Other (header, memories, instruction) — $0.06 (4%)
- **Memory save** — $0.14 (9%) — Sonnet, 18 calls
- **Location choice** — $0.07 (5%) — Sonnet, 24 calls

## Day 5 — $3.30/day (12 memories/villager) — saves $3.63 vs no-cache (52%)

- **Rating** — $0.70 (21%) — Sonnet, 340 calls
  - Character + memories (cached read, 3317 tok) — $0.13 (4%)
  - Conversation history (cache write: delta only) — $0.08 (2%)
  - Shared header + system + instruction (cached read) — $0.01 (<1%)
  - Uncached input (turn 0 only, prefix > 1024 from turn 1) — $0.44 (13%)
  - Output — $0.03 (1%)
- **Speaking** — $2.06 (62%) — Opus, 90 calls — **uncached** (speakers change)
  - Character + memories — $1.69 (51%)
  - Conversation history — $0.33 (10%)
  - Output — $0.17 (5%)
  - Other — $0.05 (2%)
- **Memory save** — $0.28 (8%) — Sonnet, 18 calls
- **Location choice** — $0.26 (8%) — Sonnet, 24 calls

## Day 10 — $5.66/day (27 memories/villager) — saves $6.46 vs no-cache (53%)

- **Rating** — $1.19 (21%) — Sonnet, 340 calls
  - Character + memories (cached read, 6570 tok) — $0.23 (4%)
  - Conversation history (cache write: delta only) — $0.08 (1%)
  - Shared header + system + instruction (cached read) — $0.01 (<1%)
  - Uncached input (turn 0 only) — $0.84 (15%)
  - Output — $0.03 (<1%)
- **Speaking** — $3.53 (62%) — Opus, 90 calls — **uncached**
  - Character + memories — $3.29 (58%)
  - Conversation history — $0.33 (6%)
  - Output — $0.17 (3%)
  - Other — $0.05 (<1%)
- **Memory save** — $0.46 (8%) — Sonnet, 18 calls
- **Location choice** — $0.49 (9%) — Sonnet, 24 calls

## Comparison vs all strategies

| Day | No cache | Current | Char-first* | Optimized | Savings |
|----:|---------:|--------:|------------:|----------:|--------:|
|   1 |    $2.72 |   $1.98 |       $1.78 |     $1.52 |    44%  |
|   5 |    $6.93 |   $6.20 |       $2.74 |     $3.30 |    52%  |
|  10 |   $12.12 |  $11.39 |       $3.93 |     $5.66 |    53%  |

\* Char-first numbers from the original model, which does **not** enforce
Anthropic's minimum cache prefix thresholds. The $1.78 on day 1 assumes
Opus speaking calls are cached at $0.50/M read — but the prefix is only
777 tokens, well below Opus's 2048 minimum. True char-first with
threshold enforcement would be closer to the optimized column.

## Where the remaining cost lives

On day 1, **speaking is 57% of total cost** — and it's entirely uncached.
Opus's 2048-token cache minimum means that on day 1 (no memories), the
prompt is simply too small to cache. Rating drops from $1.61 (no cache)
to $0.44 (73% savings) through cross-turn prefix reuse.

By day 10, speaking still dominates at 62%. Memories grow to 5910
tokens per villager — easily above 2048 — but the speaker changes every
turn, so only the shared prefix (header + history, ~1534 tok max) could
be reused, and that's still below 2048.

## Further optimization opportunities

1. **Sonnet for speaking** — if speaking quality is acceptable on Sonnet
   ($3.00/$15.00/M, 1024 min), the optimized caching would apply to
   speaking too. Day 1 speaking would drop from $0.87 to ~$0.15.
   Day 10: $3.53 → ~$0.60. This is the single largest savings available.

2. **Memory compaction** — memories grow ~220 tok/day and drive both
   speaking cost (uncached) and turn-0 rating cost (cache write on
   the full prompt). Capping at N most recent or summarizing older
   memories would bound token growth.

3. **Cache memory saves** — the optimized memory layout already shares
   conversation context across villagers. Further savings could come
   from caching character data across conversations (second breakpoint),
   saving ~$0.05/day by day 10.

4. **Sticky speakers** — if the simulation slightly favored the previous
   speaker in rating ties, consecutive same-speaker turns would enable
   Opus cross-turn caching. Even 30% same-speaker probability would
   save ~$0.20/day on day 5.
