# Automated Board Fault Isolator

A lightweight tool that reads a board's test **reply log** and outputs a **ranked list
of the components most likely to be faulty** — turning the manual fault-isolation
reasoning a debug technician does by hand into a repeatable algorithm.

Built in pure Python (standard library only — nothing to install) as a learning and
portfolio project. Includes a **virtual board simulator** so the whole pipeline can be
developed and validated without any hardware.

---

## The core idea

> The faulty component is the one the **failing** tests share and the **passing** tests
> never clear.

Fault isolation is mostly set logic, not AI:

```
suspects = (components in failing tests) − (components cleared by passing tests)
```

Each suspect is then ranked, with a strong bonus for components that no passing test
ever exonerated.

---

## Measured performance

Validated over hundreds of injected-fault trials against the virtual board
(reproduce with `accuracy_test.py`):

| Condition            | Correct part in **top 3** | Correct part is **#1** |
|----------------------|:-------------------------:|:----------------------:|
| Clean logs           | ~100%                     | ~60%                   |
| 5% measurement noise | ~87%                      | ~44%                   |

Top-1 is intentionally below 100%: components sharing identical test coverage are
mathematically indistinguishable by tests alone. The fix is better test *coverage
design*, not more code — the accuracy harness reports exactly which parts are ambiguous.

---

## Quick start

```bash
# isolate faults from a sample log and save the session to a database
python3 fault_isolator.py

# view saved sessions (SQL query)
python3 fault_isolator.py history

# run the engine self-test
python3 fault_isolator.py test

# generate a realistic log by breaking one part
python3 board_simulator.py R188

# measure isolation accuracy over 500 random faults
python3 accuracy_test.py 500

# ...with 5% measurement noise
python3 accuracy_test.py 1000 0.05
```

---

## How it works

1. **Coverage matrix** (`coverage.csv`) — maps each test to the components it exercises.
   This is the key asset; it encodes board knowledge.
2. **Log parser** — turns a raw reply log into pass/fail per test.
3. **Isolation engine** — intersects failing-test coverage, subtracts what passing
   tests cleared, and ranks the survivors by suspicion score.
4. **SQLite persistence** — every session is saved, so the tool accumulates a labelled
   (log → faulty component) dataset over time.
5. **Virtual board simulator** — injects a fault and emits a realistic log, enabling a
   fully software-based develop-and-validate loop.

```
inject fault  →  generate log  →  isolate  →  was the right part found?
```

---

## Project structure

```
fault-isolator/
├── README.md            project overview (this file)
├── BUILD_GUIDE.md       step-by-step guide to build it from scratch
├── coverage.csv         the test-to-component coverage matrix (data)
├── fault_isolator.py    main program: parse → isolate → rank → persist
├── board_simulator.py   virtual board: inject a fault, emit a reply log
├── accuracy_test.py     harness: measure top-1 / top-3 isolation accuracy
├── .gitignore
└── LICENSE
```

---

## Skills demonstrated

Python program structure (classes, modules), file handling (CSV), SQL (SQLite:
create / insert / select), testing (assertions), and the domain reasoning behind
board bring-up and fault isolation.

---

## Where it goes next

- Parse a real test-system log format
- Generate the coverage matrix from a netlist instead of by hand
- Add a **fault dictionary** that matches whole pass/fail signatures to known faults
- Train an ML ranker once enough labelled sessions accumulate in the database

---

## Note

Built for learning and demonstration using synthetic sample data. It contains no
proprietary board designs, test programs, or production logs.
