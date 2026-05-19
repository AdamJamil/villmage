"""Cost analysis for different prompt caching strategies.

Compares caching regimes for the Villmage simulation's API calls and
includes an optimizer that exhaustively enumerates section orderings,
breakpoint placements, and batching strategies to find the cheapest
approach.

Run:
  python -m cost_analysis                    # side-by-side comparison
  python -m cost_analysis --day 5            # project to day 5 memory growth
  python -m cost_analysis --optimize         # find optimal caching strategy
"""

from cost_analysis.pricing import SONNET, OPUS, count_tokens, cost, ModelPricing
from cost_analysis.scenarios import (
    UNIFORM_PARAMS, OBSERVED_PARAMS, SimParams, ConversationGroup,
)
from cost_analysis.computation import CostBreakdown, compute_costs
from cost_analysis.reporting import print_report
