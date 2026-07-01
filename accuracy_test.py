"""
accuracy_test.py  --  measure how good your isolator actually is.

This is the payoff of having a simulator: you can run hundreds of trials.
Each trial: break a random part -> generate its log -> run the isolator ->
record whether the broken part came out as the #1 suspect (top-1) and whether
it landed anywhere in the top 3 (top-3).

Why top-3 matters: some parts are genuinely indistinguishable from each other
(two resistors exercised by the exact same single test can't be told apart by
tests alone). So top-1 will never be 100%, and that's correct, not a bug. Top-3
is the number a repair line actually cares about: "probe these 3 parts."

Run:
    python3 accuracy_test.py            # 500 trials, no noise
    python3 accuracy_test.py 1000 0.05  # 1000 trials, 5% measurement noise

Needs: fault_isolator_v2.py (the class) and board_simulator.py, both alongside.
"""

import sys
import random

from fault_isolator import FaultIsolator
from board_simulator import load_coverage, all_components, generate_log


def run(trials=500, noise=0.0):
    coverage = load_coverage()
    comps = all_components(coverage)

    fi = FaultIsolator(db_path=":memory:")   # in-memory DB; don't pollute history
    fi.coverage = coverage

    top1 = top3 = 0
    misses = []

    for _ in range(trials):
        truth = random.choice(comps)
        log = generate_log(truth, coverage, noise=noise)
        ranked = fi.isolate(fi.parse_log(log))
        names = [r["component"] for r in ranked]
        if names and names[0] == truth:
            top1 += 1
        if truth in names[:3]:
            top3 += 1
        else:
            misses.append(truth)

    print("=" * 50)
    print(f"ISOLATOR ACCURACY  ({trials} trials, noise={noise})")
    print("=" * 50)
    print(f"Top-1 (prime suspect was right): {top1/trials:6.1%}")
    print(f"Top-3 (right part in top 3)    : {top3/trials:6.1%}")
    if misses:
        # which parts are hardest to localise?
        from collections import Counter
        worst = Counter(misses).most_common(5)
        print("-" * 50)
        print("Hardest-to-isolate parts (top-3 misses):")
        for comp, n in worst:
            print(f"  {comp:6s} missed {n} time(s)")
        print("These are usually parts sharing identical test coverage —")
        print("the fix is more tests that separate them, not more code.")


def main():
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    noise = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    run(trials, noise)


if __name__ == "__main__":
    main()
