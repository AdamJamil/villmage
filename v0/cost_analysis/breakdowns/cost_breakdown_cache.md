# Cost Breakdown (char-first caching, observed params)

**Strategy:** Cache `system prompt + character description + memories + instruction`
as a prefix block per villager. On turn 0 of each conversation this block is a
cache write ($3.75/M Sonnet, $6.25/M Opus); on turns 1+ it is a cache read
($0.30/M Sonnet, $0.50/M Opus). The conversation history remains uncached input.

Effective blended rate for a 20-turn conversation:
- Sonnet: $0.47/M (vs $3.00/M uncached — **84% cheaper**)
- Opus:   $0.79/M (vs $5.00/M uncached — **84% cheaper**)

## Day 1 — $1.27/day (0 memories/villager) — saves $1.18 vs no-cache (48%)

- **Rating** — $0.61 (48%) — Sonnet, 340 calls
  - Character description (cached) — $0.11 (9%)
  - Memories (cached) — $0.03 (2%)
  - Conversation history — $0.43 (34%)
  - System prompt (cached) — $0.01 (1%)
  - Output — $0.03 (2%)
- **Speaking** — $0.43 (34%) — Opus, 90 calls
  - Character description (cached) — $0.05 (4%)
  - Memories (cached) — $0.02 (2%)
  - Conversation history — $0.19 (15%)
  - System prompt (cached) — $0.00 (<1%)
  - Output — $0.17 (13%)
- **Memory save** — $0.15 (12%) — Sonnet, 18 calls
- **Location choice** — $0.08 (6%) — Sonnet, 24 calls

## Day 5 — $2.08/day (12 memories/villager) — saves $3.89 vs no-cache (65%)

- **Rating** — $0.98 (47%) — Sonnet, 340 calls
  - Character description (cached) — $0.11 (5%)
  - Memories (cached) — $0.40 (19%)
  - Conversation history — $0.42 (20%)
  - System prompt (cached) — $0.01 (<1%)
  - Output — $0.03 (1%)
- **Speaking** — $0.59 (28%) — Opus, 90 calls
  - Character description (cached) — $0.05 (2%)
  - Memories (cached) — $0.18 (9%)
  - Conversation history — $0.19 (9%)
  - System prompt (cached) — $0.00 (<1%)
  - Output — $0.17 (8%)
- **Memory save** — $0.27 (13%) — Sonnet, 18 calls
- **Location choice** — $0.23 (11%) — Sonnet, 24 calls

## Day 10 — $3.17/day (27 memories/villager) — saves $7.61 vs no-cache (71%)

- **Rating** — $1.47 (46%) — Sonnet, 340 calls
  - Character description (cached) — $0.11 (3%)
  - Memories (cached) — $0.89 (28%)
  - Conversation history — $0.42 (13%)
  - System prompt (cached) — $0.01 (<1%)
  - Output — $0.03 (1%)
- **Speaking** — $0.82 (26%) — Opus, 90 calls
  - Character description (cached) — $0.05 (2%)
  - Memories (cached) — $0.40 (13%)
  - Conversation history — $0.19 (6%)
  - System prompt (cached) — $0.00 (<1%)
  - Output — $0.17 (5%)
- **Memory save** — $0.44 (14%) — Sonnet, 18 calls
- **Location choice** — $0.45 (14%) — Sonnet, 24 calls

## Comparison vs no-cache baseline

| Day | No cache | Char-first | Savings |
|----:|---------:|-----------:|--------:|
|   1 |    $2.45 |      $1.27 |    48%  |
|   3 |    $4.05 |      $1.64 |    60%  |
|   5 |    $5.97 |      $2.08 |    65%  |
|  10 |   $10.78 |      $3.17 |    71%  |

## Where the remaining cost lives

On day 1, conversation history (34% of total) and output tokens (15%)
dominate after caching eliminates most of the character/memory input cost.

By day 10, memories — even at the cache-read rate — become the largest
single component again (28% rating + 13% speaking = 41%), because 27
memories per villager means ~5400 tokens that still get billed at cache-read
rates across 340+90 calls. Conversation history drops to 19% of total.

Location choice and memory save are **not cached** in this strategy (they
are single-call-per-villager phases with no prefix reuse opportunity),
and grow from 18% of the total on day 1 to 28% by day 10.

## Further optimization opportunities

1. **Haiku for ratings** — ratings are 5-token integer outputs; Haiku
   ($0.25/$1.25/M) would cut rating input cost by ~12x vs Sonnet.
   Day 10 rating would drop from $1.47 to ~$0.12.

2. **Memory summarization / compaction** — cap memories at N most recent
   or periodically summarize older memories to bound token growth.
   Without this, memory tokens grow ~200/day and eventually dominate
   even at cache-read rates.

3. **Cache location + memory-save calls** — these are currently uncached.
   Caching the character prefix for these calls too would save ~$0.10/day
   on day 10 (small but free).
