"""
board_simulator.py  --  a fake board you can break on purpose.

Why this exists:
    You have no physical board, but you still need logs to test your isolator.
    So we SIMULATE one. You pick a component to fault; the simulator knows which
    tests touch that component (from coverage.csv) and makes exactly those tests
    fail, with realistic-looking measurements. Out comes a reply log.

The loop this enables:
    inject fault  ->  generate log  ->  run isolator  ->  did it find the part?

Run:
    python3 board_simulator.py            # break a random part, print the log
    python3 board_simulator.py R188       # break a specific part
    python3 board_simulator.py R188 0.1   # ...with 10% measurement noise

Standard library only.
"""

import csv
import sys
import random
from collections import defaultdict
from datetime import datetime


def load_coverage(csv_path="coverage.csv"):
    cov = defaultdict(set)
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            cov[row["test_id"].strip()].add(row["component"].strip())
    return dict(cov)


# Per-test realistic messages: (passing message, failing message).
# Tests not listed here fall back to a generic PASS/FAIL line.
MESSAGES = {
    "T01_power_3v3":     ("measured 3.31V (expected 3.30V)", "measured 1.78V (expected 3.30V)"),
    "T02_power_5v":      ("measured 5.01V",                   "measured 2.41V (expected 5.00V)"),
    "T03_clock":         ("25.000 MHz detected",              "no clock edge detected"),
    "T04_reset":         ("reset asserted/deasserted OK",     "reset line stuck low"),
    "T05_eth_phy":       ("PHY id 0x0181 read OK",            "PHY id read failed, no link"),
    "T06_eth_link_led":  ("link LED on",                      "link LED off"),
    "T07_uart_loopback": ("loopback echo OK",                 "no echo received"),
    "T08_i2c_scan":      ("3 devices found",                  "bus stuck, no ACK"),
    "T09_flash_id":      ("JEDEC id matched",                 "id mismatch / no response"),
}


def all_components(coverage):
    comps = set()
    for parts in coverage.values():
        comps |= parts
    return sorted(comps)


def generate_log(faulted_component, coverage, noise=0.0, seed=None):
    """
    Build a reply log where every test that TOUCHES the faulted component fails.
    `noise` (0..1) optionally flips an occasional result to mimic flaky reality.
    Returns the log string. The faulted component is the hidden ground truth.
    """
    rng = random.Random(seed)
    lines = []
    t = 1
    for test_id in sorted(coverage):
        touches_fault = faulted_component in coverage[test_id]
        failed = touches_fault
        # optional realism: a small chance the result is noisy/intermittent
        if noise and rng.random() < noise:
            failed = not failed
        good, bad = MESSAGES.get(test_id, ("ok", "error"))
        msg = bad if failed else good
        verdict = "FAIL" if failed else "PASS"
        ts = f"[00:00:{t:02d}]"
        lines.append(f"{ts} {test_id:18s}: {msg:34s} {verdict}")
        t += 1
    return "\n".join(lines)


def main():
    coverage = load_coverage()
    comps = all_components(coverage)

    # pick the component to fault
    if len(sys.argv) > 1:
        faulted = sys.argv[1]
        if faulted not in comps:
            print(f"'{faulted}' is not on this board. Known parts: {', '.join(comps)}")
            return
    else:
        faulted = random.choice(comps)

    noise = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0

    log = generate_log(faulted, coverage, noise=noise)
    print("---------- GENERATED REPLY LOG ----------")
    print(log)
    print("-----------------------------------------")
    print(f"(ground truth, hidden in real use: {faulted})")
    print("Feed this log into your isolator and see if it finds that part.")


if __name__ == "__main__":
    main()
