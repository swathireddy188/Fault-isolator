# Board Fault Isolator — Step-by-Step Build Guide

A complete walkthrough that builds an automated board fault-isolation tool from an
empty folder. You write it in **8 phases**, each one small, runnable, and adding one
new skill. By the end you have a real program *and* you've practised the developer
skills that matter: program structure, file handling, SQL, and testing.

**Golden rule:** run the code after every phase. If it runs, you understood it. If it
breaks, the error teaches you. Never move to the next phase on broken code.

---

## The idea in one sentence

> The bad component is the one the **failing** tests share and the **passing** tests
> never clear.

Fault isolation is mostly set logic:

```
suspects = (components in failing tests) − (components cleared by passing tests)
```

AI is not the engine. Set intersection is. AI only ranks what's left, much later.

---

## Phase 0 — Setup (5 minutes)

You need Python 3 and a folder. That's it. No libraries to install — everything
used here ships with Python.

```bash
mkdir fault-isolator
cd fault-isolator
python3 --version          # confirm Python 3.x is installed
git init                   # start version control from day one
```

> **Skill:** starting every project under git. After each phase that works, run
> `git add -A && git commit -m "phase N working"`. That habit alone separates
> hobby scripts from real software.

---

## Phase 1 — The coverage matrix (the moat)

The coverage matrix maps each test to the components it exercises. This is the most
valuable part of the whole project — it encodes board knowledge.

Create a file `coverage.csv`:

```csv
test_id,component
T01_power_3v3,VR1
T01_power_3v3,R188
T01_power_3v3,C12
T01_power_3v3,U1
T02_power_5v,VR2
T02_power_5v,C20
T02_power_5v,U1
T03_clock,Y1
T03_clock,U1
T03_clock,C30
T04_reset,U1
T04_reset,R40
T04_reset,C31
T05_eth_phy,U10
T05_eth_phy,R188
T05_eth_phy,Y2
T06_eth_link_led,U10
T06_eth_link_led,D1
T06_eth_link_led,R50
T07_uart_loopback,U1
T07_uart_loopback,U5
T07_uart_loopback,R60
T08_i2c_scan,U1
T08_i2c_scan,U7
T08_i2c_scan,R70
T08_i2c_scan,R71
T09_flash_id,U1
T09_flash_id,U8
```

Each row says "this test touches this component." Notice `U1` appears in almost
every test — that matters later.

> **Skill:** keeping data *out* of code. The matrix is data, so it lives in a file,
> not hard-coded. Edit the board by editing the CSV, never the program.

---

## Phase 2 — Load the matrix from CSV

Create `step2.py`:

```python
import csv
from collections import defaultdict

def load_coverage(csv_path):
    coverage = defaultdict(set)        # {test_id: {components}}
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):  # reads header row automatically
            test = row["test_id"].strip()
            comp = row["component"].strip()
            coverage[test].add(comp)
    return dict(coverage)

if __name__ == "__main__":
    cov = load_coverage("coverage.csv")
    for test, comps in cov.items():
        print(test, "->", sorted(comps))
```

Run it:

```bash
python3 step2.py
```

You should see each test with its component set.

> **Skill:** file handling + `csv.DictReader` (reads each row as a dict keyed by
> the header) + `defaultdict(set)` (auto-creates an empty set for a new key, so you
> never check "does this key exist yet?").

---

## Phase 3 — Parse a reply log into pass/fail

Real logs are messy text. The parser's only job: decide pass or fail per test.

Add to a new file `step3.py`:

```python
from step2 import load_coverage

SAMPLE_LOG = """
[00:00:01] T01_power_3v3      : measured 1.78V (expected 3.30V)   FAIL
[00:00:02] T02_power_5v       : measured 5.01V                    PASS
[00:00:03] T03_clock          : 25.000 MHz detected               PASS
[00:00:04] T04_reset          : reset OK                           PASS
[00:00:05] T05_eth_phy        : PHY id read failed                 FAIL
[00:00:06] T06_eth_link_led   : LED off                            FAIL
[00:00:07] T07_uart_loopback  : loopback OK                        PASS
[00:00:08] T08_i2c_scan       : 3 devices found                    PASS
[00:00:09] T09_flash_id       : id matched                         PASS
"""

def parse_log(raw_log, coverage):
    results = {}
    for line in raw_log.strip().splitlines():
        tokens = line.replace(":", " ").split()
        # first token that is a known test id
        test_id = next((t for t in tokens if t in coverage), None)
        if test_id is None:
            continue
        up = line.upper()
        if "FAIL" in up:
            results[test_id] = False
        elif "PASS" in up:
            results[test_id] = True
    return results

if __name__ == "__main__":
    cov = load_coverage("coverage.csv")
    results = parse_log(SAMPLE_LOG, cov)
    for test, ok in results.items():
        print(test, "PASS" if ok else "FAIL")
```

Run `python3 step3.py`. You'll see three FAILs (3v3, eth_phy, eth_link_led).

> **Skill:** importing your own modules (`from step2 import ...`), string handling,
> and the `next((x for x in ... if ...), None)` pattern for "first match or nothing."

---

## Phase 4 — The isolation engine

Now the core. Add `step4.py`:

```python
from collections import defaultdict
from step2 import load_coverage
from step3 import parse_log, SAMPLE_LOG

def isolate(results, coverage):
    failing = [t for t, ok in results.items() if ok is False]
    passing = [t for t, ok in results.items() if ok is True]
    if not failing:
        return []

    # how many failing tests touch each component
    fail_hits = defaultdict(int)
    for t in failing:
        for comp in coverage.get(t, ()):
            fail_hits[comp] += 1

    # every component a passing test cleared
    cleared = set()
    for t in passing:
        cleared |= coverage.get(t, set())

    ranked = []
    for comp, hits in fail_hits.items():
        unique = comp not in cleared          # never seen in a passing test
        score = hits + (5 if unique else 0)   # big bonus for never-cleared
        ranked.append((comp, score, unique, hits))

    ranked.sort(key=lambda r: r[1], reverse=True)  # highest score first
    return ranked

if __name__ == "__main__":
    cov = load_coverage("coverage.csv")
    results = parse_log(SAMPLE_LOG, cov)
    for comp, score, unique, hits in isolate(results, cov):
        tag = "never cleared" if unique else "also cleared elsewhere"
        print(f"{comp:6s} score={score:<2} ({hits} fails, {tag})")
```

Run `python3 step4.py`. **R188** should top the list, and **U1** should sink to the
bottom — because passing tests cleared U1, even though it appears in a failing test.

> **Skill:** list comprehensions, the `|=` set-union operator, and *scoring* — turning
> a yes/no question ("is it a suspect?") into a ranked answer ("how likely?").
> The `key=lambda` in `sort` is how you sort by a computed value.

---

## Phase 5 — A clean report

Wrap the output in a readable report. Add `step5.py`:

```python
from step2 import load_coverage
from step3 import parse_log, SAMPLE_LOG
from step4 import isolate

def print_report(results, ranked):
    passing = [t for t, ok in results.items() if ok]
    failing = [t for t, ok in results.items() if not ok]
    print("=" * 52)
    print("BOARD FAULT ISOLATION REPORT")
    print("=" * 52)
    print(f"Passed: {len(passing)}   Failed: {len(failing)} -> {', '.join(failing)}")
    print("-" * 52)
    for i, (comp, score, unique, hits) in enumerate(ranked, 1):
        flag = "  <-- PRIME SUSPECT" if i == 1 else ""
        print(f"  {i}. {comp:6s} score {score:>2}{flag}")
    if ranked:
        print("-" * 52)
        print(f"Start probing at: {ranked[0][0]}")

if __name__ == "__main__":
    cov = load_coverage("coverage.csv")
    results = parse_log(SAMPLE_LOG, cov)
    ranked = isolate(results, cov)
    print_report(results, ranked)
```

Run `python3 step5.py`. You now have a working tool. **Commit it.**

> **Skill:** separating *logic* (isolate) from *presentation* (print_report). Keep
> them apart and you can later swap the report for a web page or a CSV without
> touching the engine.

---

## Phase 6 — Refactor into a class

Everything so far is loose functions passing `coverage` around. A class bundles the
data and the behaviour together. This is the "script → software" jump.

Create `fault_isolator.py`:

```python
import csv
from collections import defaultdict

class FaultIsolator:
    def __init__(self):
        self.coverage = {}

    def load_coverage(self, csv_path):
        cov = defaultdict(set)
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                cov[row["test_id"].strip()].add(row["component"].strip())
        self.coverage = dict(cov)
        return self.coverage

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
            ranked.append({"component": comp, "score": score,
                           "unique": unique, "hits": hits})
        ranked.sort(key=lambda r: r["score"], reverse=True)
        return ranked
```

Notice `self.coverage` — the matrix now lives *inside* the object, so the methods
don't pass it around. Test it quickly:

```python
# quick_check.py
from fault_isolator import FaultIsolator
fi = FaultIsolator()
fi.load_coverage("coverage.csv")
log = "T01_power_3v3 FAIL\nT05_eth_phy FAIL\nT02_power_5v PASS"
print(fi.isolate(fi.parse_log(log)))
```

> **Skill:** classes. `__init__` sets up state; `self.x` is data the whole object
> shares; methods are behaviour acting on that state. Try adding a method
> `most_suspect_component()` yourself once Phase 7 gives you data.

---

## Phase 7 — Persist to SQLite (your SQL gym)

A fault tool is a *data* product. Save every session so the tool builds its own
history — which is exactly the labelled data a future ML ranker would train on.

Add these methods inside the `FaultIsolator` class:

```python
import sqlite3
from datetime import datetime

# --- add to the class ---

    def init_db(self, db_path="fault_history.db"):
        self.db_path = db_path
        con = sqlite3.connect(db_path)
        con.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board TEXT, ts TEXT, n_failed INTEGER, prime TEXT
            );
            CREATE TABLE IF NOT EXISTS suspects (
                session_id INTEGER, rank INTEGER,
                component TEXT, score INTEGER
            );
        """)
        con.commit(); con.close()

    def save_session(self, board, results, ranked):
        n_failed = sum(1 for ok in results.values() if ok is False)
        prime = ranked[0]["component"] if ranked else None
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("INSERT INTO sessions (board, ts, n_failed, prime) "
                    "VALUES (?, ?, ?, ?)",
                    (board, datetime.now().isoformat(timespec="seconds"),
                     n_failed, prime))
        sid = cur.lastrowid
        for i, s in enumerate(ranked, 1):
            cur.execute("INSERT INTO suspects (session_id, rank, component, score) "
                        "VALUES (?, ?, ?, ?)",
                        (sid, i, s["component"], s["score"]))
        con.commit(); con.close()
        return sid

    def show_history(self):
        con = sqlite3.connect(self.db_path)
        rows = con.execute(
            "SELECT id, ts, board, n_failed, prime FROM sessions ORDER BY id"
        ).fetchall()
        con.close()
        for sid, ts, board, n_failed, prime in rows:
            print(f"#{sid} {ts} {board} failed={n_failed} prime={prime}")
```

Three SQL skills in one place: **CREATE TABLE** (define structure), **INSERT**
(add rows — note the `?` placeholders, which safely insert values), and **SELECT**
(query back out). The `?` placeholders also protect against SQL injection — always
use them, never string-format values into SQL.

Wire it into a `main()` at the bottom of the file:

```python
import sys

def print_report(results, ranked):
    failing = [t for t, ok in results.items() if not ok]
    print(f"Failed: {len(failing)} -> {', '.join(failing)}")
    for i, s in enumerate(ranked, 1):
        flag = "  <-- PRIME" if i == 1 else ""
        print(f"  {i}. {s['component']:6s} score {s['score']:>2}{flag}")

SAMPLE_LOG = """
T01_power_3v3 FAIL
T02_power_5v PASS
T05_eth_phy FAIL
T06_eth_link_led FAIL
T03_clock PASS
"""

def main():
    fi = FaultIsolator()
    fi.load_coverage("coverage.csv")
    fi.init_db()
    if len(sys.argv) > 1 and sys.argv[1] == "history":
        fi.show_history(); return
    results = fi.parse_log(SAMPLE_LOG)
    ranked = fi.isolate(results)
    print_report(results, ranked)
    sid = fi.save_session("sample-board", results, ranked)
    print(f"Saved session #{sid}. Run 'python3 fault_isolator.py history' to view.")

if __name__ == "__main__":
    main()
```

Run it twice, then view history:

```bash
python3 fault_isolator.py
python3 fault_isolator.py
python3 fault_isolator.py history
```

You'll see two saved sessions pulled back from the database.

> **Skill:** SQL basics + the insight that a database is how a product *accumulates*
> value over time. Every run makes the dataset bigger.

---

## Phase 8 — A self-test

Add this so you can refactor without fear:

```python
def check_engine():
    fi = FaultIsolator()
    fi.coverage = {"tA": {"X", "SHARED"}, "tB": {"SHARED"}}
    ranked = fi.isolate({"tA": False, "tB": True})
    assert ranked[0]["component"] == "X", "X should be isolated"
    print("check_engine: PASS")
```

Call it with `python3 fault_isolator.py test` by adding a branch in `main()`:

```python
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        check_engine(); return
```

The test sets up a tiny board where the answer is known (X is the only thing not
cleared), runs the engine, and asserts the answer. If you later change the scoring
and break it, this fails instantly.

> **Skill:** testing. An `assert` says "this must be true." Tests on known cases are
> what let software grow without quietly breaking.

---

## What you've built and learned

| Phase | Built | Skill gained |
|------:|-------|--------------|
| 0 | folder + git | version control habit |
| 1 | coverage.csv | data out of code |
| 2 | CSV loader | file handling, defaultdict |
| 3 | log parser | string handling, imports |
| 4 | isolation engine | comprehensions, sets, scoring |
| 5 | report | logic vs presentation |
| 6 | class refactor | program structure |
| 7 | SQLite | SQL: create / insert / select |
| 8 | self-test | testing with assert |

---

## Where to take it next (pick one)

1. **Real log format.** Replace `SAMPLE_LOG` with a real log shape you have, and adjust
   `parse_log` to match. The matrix and engine don't change — proof your design is clean.
2. **Coverage from a netlist.** Generate `coverage.csv` from a real board's test
   definitions instead of by hand. This is the hardest and most valuable extension.
3. **Fault dictionary.** Record the full pass/fail *signature* of known faults, then
   match a new log against the library — "recognise the fault from the log."
4. **ML ranker.** Once `fault_history.db` has enough labelled (log → bad part) rows,
   train a simple classifier to rank suspects. Only worth it after you have real data.

---

## Working habits to keep

- Commit after every phase that runs.
- Learn by extending *this* project, not by finishing unrelated tutorials.
- Keep your bench knowledge (real board IP, proprietary logs) separate from anything
  you might one day take commercial — build on your own sample data.
- "Perfect fault detection" is a trap. Aim for "narrow 500 parts to the top 3, ranked."
  That's already transformative on a repair line, and achievable.
