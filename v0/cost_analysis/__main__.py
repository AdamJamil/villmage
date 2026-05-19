"""CLI entry point: python -m cost_analysis"""

import argparse

from cost_analysis.reporting import print_report, print_optimization_results
from cost_analysis.optimizer import optimize
from cost_analysis.scenarios import OBSERVED_PARAMS


def main():
    parser = argparse.ArgumentParser(description="Villmage caching cost analysis")
    parser.add_argument("--day", type=int, default=1,
                        help="Simulation day (affects memory count)")
    parser.add_argument("--optimize", action="store_true",
                        help="Run optimizer to find best caching strategy")
    parser.add_argument("--top", type=int, default=3,
                        help="Number of top strategies to show (default: 3)")
    args = parser.parse_args()

    print_report(args.day, run_optimizer=args.optimize)

    if args.optimize:
        results = optimize(OBSERVED_PARAMS, day=args.day, top_n=args.top)
        print_optimization_results(results)


if __name__ == "__main__":
    main()
