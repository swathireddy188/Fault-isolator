"""
fault_isolator_v2.py  --  the script grown into a program.

What changed from v1, and WHY (each change teaches a developer skill):

  1. CLASS structure ......... logic lives in a FaultIsolator class, not
                               loose functions. This is the "script -> software"
                               jump: state + behaviour bundled together.
  2. CSV coverage matrix ..... the matrix is DATA now (coverage.csv), loaded
                               at runtime. Edit the board without touching code.
  3. SQLite database ......... every test session is SAVED to fault_history.db.
                               This is your SQL gym, AND it's how a real product
                               accumulates the labelled data that ML needs later.
  4. History query ........... pull past sessions back out with SQL.
  5. A self-test ............. check_engine() asserts the engine is correct,
                               so you can refactor without fear.

Run:
    python3 fault_isolator_v2.py          # isolate + save a session
    python3 fault_isolator_v2.py history  # show saved sessions from the DB
    python3 fault_isolator_v2.py test     # run the self-test

Standard library only (csv + sqlite3 ship with Python). Nothing to install.
"""

import csv
import sys
import sqlite3
from collections import defaultdict
from datetime import datetime


SAMPLE_LOG = """
[00:00:01] T01_power_3v3      : measured 1.78V (expected 3.30V)   FAIL
[00:00:02] T02_power_5v       : measured 5.01V                    PASS
[00:00:03] T03_clock          : 25.000 MHz detected               PASS
[00:00:04] T04_reset          : reset asserted/deasserted OK       PASS
[00:00:05] T05_eth_phy        : no link, PHY id read failed        FAIL
[00:00:06] T06_eth_link_led   : LED off                            FAIL
[00:00:07] T07_uart_loopback  : loopback OK                        PASS
[00:00:08] T08_i2c_scan       : 3 devices found                    PASS
[00:00:09] T09_flash_id       : JEDEC id matched                   PASS
"""


class FaultIsolator:
    """Holds a board's coverage matrix and isolates faults from a log."""

    def __init__(self, db_path="fault_history.db"):
        self.coverage = {}            # {test_id: set(components)}
        self.db_path = db_path
        self._init_db()

    # ---- 1. load the coverage matrix from CSV --------------------------
    def load_coverage(self, csv_path):
        coverage = defaultdict(set)
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                coverage[row["test_id"].strip()].add(row["component"].strip())
        self.coverage = dict(coverage)
        return self.coverage

    # ---- 2. parse a raw reply log --------------------------------------
    def parse_log(self, raw_log):
        results = {}
        for line in raw_log.strip().splitlines():
            tokens = line.replace(":", " ").split()
            test_id = next((t for t in tokens if t in self.coverage), None)
            if test_id is None:
                continue
            up = line.upper()
            if "FAIL" in up:
                results[test_id] = False
            elif "PASS" in up:
                results[test_id] = True
        return results

    # ---- 3. the engine: candidate reduction + ranking ------------------
    def isolate(self, results):
        failing = [t for t, ok in results.items() if ok is False]
        passing = [t for t, ok in results.items() if ok is True]
        if not failing:
            return []

        fail_hits = defaultdict(int)
        for t in failing:
            for comp in self.coverage.get(t, ()):
                fail_hits[comp] += 1

        cleared = set()
        for t in passing:
            cleared |= self.coverage.get(t, set())

        ranked = []
        for comp, hits in fail_hits.items():
            unique = comp not in cleared
            score = hits + (5 if unique else 0)
            ranked.append({
                "component": comp,
                "score": score,
                "unique": unique,
                "why": (f"in {hits} failing test(s), "
                        + ("never cleared" if unique else "also cleared elsewhere")),
            })
        ranked.sort(key=lambda r: r["score"], reverse=True)
        return ranked

    # ---- 4. SQLite: persistence ----------------------------------------
    def _init_db(self):
        con = sqlite3.connect(self.db_path)
        con.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                board     TEXT,
                ts        TEXT,
                n_tests   INTEGER,
                n_failed  INTEGER,
                prime     TEXT
            );
            CREATE TABLE IF NOT EXISTS suspects (
                session_id INTEGER,
                rank       INTEGER,
                component  TEXT,
                score      INTEGER,
                why        TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );
        """)
        con.commit()
        con.close()

    def save_session(self, board, results, ranked):
        n_failed = sum(1 for ok in results.values() if ok is False)
        prime = ranked[0]["component"] if ranked else None
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute(
            "INSERT INTO sessions (board, ts, n_tests, n_failed, prime) "
            "VALUES (?, ?, ?, ?, ?)",
            (board, datetime.now().isoformat(timespec="seconds"),
             len(results), n_failed, prime),
        )
        sid = cur.lastrowid
        for i, s in enumerate(ranked, 1):
            cur.execute(
                "INSERT INTO suspects (session_id, rank, component, score, why) "
                "VALUES (?, ?, ?, ?, ?)",
                (sid, i, s["component"], s["score"], s["why"]),
            )
        con.commit()
        con.close()
        return sid

    def show_history(self):
        con = sqlite3.connect(self.db_path)
        rows = con.execute(
            "SELECT id, ts, board, n_failed, prime FROM sessions ORDER BY id"
        ).fetchall()
        con.close()
        if not rows:
            print("No sessions saved yet. Run with no argument first.")
            return
        print("SESSION HISTORY (from SQLite):")
        for sid, ts, board, n_failed, prime in rows:
            print(f"  #{sid}  {ts}  {board}  failed={n_failed}  prime={prime}")


def print_report(results, ranked):
    passing = [t for t, ok in results.items() if ok]
    failing = [t for t, ok in results.items() if not ok]
    print("=" * 56)
    print("BOARD FAULT ISOLATION REPORT")
    print("=" * 56)
    print(f"Passed: {len(passing)}   Failed: {len(failing)} -> {', '.join(failing)}")
    print("-" * 56)
    for i, s in enumerate(ranked, 1):
        flag = "  <-- PRIME SUSPECT" if i == 1 else ""
        print(f"  {i}. {s['component']:6s} score {s['score']:>2}  {s['why']}{flag}")
    if ranked:
        print("-" * 56)
        print(f"Start probing at: {ranked[0]['component']}")


def check_engine():
    """Self-test: a fault unique to one failing test must rank #1."""
    fi = FaultIsolator(db_path=":memory:")
    fi.coverage = {
        "tA": {"X", "SHARED"},   # fails
        "tB": {"SHARED"},        # passes -> clears SHARED
    }
    ranked = fi.isolate({"tA": False, "tB": True})
    assert ranked[0]["component"] == "X", "engine should isolate X"
    assert ranked[0]["unique"] is True
    print("check_engine: PASS  (X correctly isolated, SHARED exonerated)")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    fi = FaultIsolator()

    if mode == "test":
        check_engine()
        return
    if mode == "history":
        fi.show_history()
        return

    fi.load_coverage("coverage.csv")
    results = fi.parse_log(SAMPLE_LOG)
    ranked = fi.isolate(results)
    print_report(results, ranked)
    sid = fi.save_session("CloudLink-sample", results, ranked)
    print(f"\nSaved as session #{sid} in fault_history.db "
          f"(run 'python3 {sys.argv[0]} history' to see it).")


if __name__ == "__main__":
    main()
