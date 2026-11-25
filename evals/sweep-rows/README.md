# Fixed sweep rows for each finder in the thorough search

This folder records one experiment. It is not a shipped eval: `evals/run.py`
does not pick it up, and each run costs real money.

The question: separate thorough searches of the same pins report different
defects. If a script lists the units of the change and every finder must give
a verdict for every unit in its focus, do runs agree more, find more, and
finish sooner?

## The two arms

- **`main`** (commit 607578d): the thorough search of release 0.9.0. A general
  finder and consumers, inputs, and state finders, plus a fault finder when
  `failure_points.py` lists five or more lines.
- **Sweep rows** (commit e6eb630 on branch `ccr-802504f9-rvycar`):
  `sweep_units.py`, kept here, lists each changed function or method, the
  changed lines outside a definition, and each changed test, prose, or
  configuration file. It writes one table for each finder with one row per
  unit in that finder's focus. A list of more than 20 rows splits into up to
  three shards, each started as its own finder. Every row needs a `clean:`,
  `candidate:`, or `n/a:` verdict. The lead prepares base and head worktrees
  once and confirms candidates through parallel confirmers.

PR 10 (`9ca3def`, not merged) tried a single reader with eight defect
classes per unit. This experiment instead keeps the focused finders and gives
each finder rows for its focus only.

## Cases

The four cases of `evals/thorough-focus`: fastapi PR 15745 and filelock PR 659
from `evals/real-pr` on `find-bugs-variance`, with the thorough prompts from
`evals/thorough-focus/cases/`, and the urllib3 PR 5095 and pipx PR 2229 cases
there. `max_turns` was 200 in every prompt. `evals/`
and `docs/` were removed from both plugin copies so that no run could read
graders. Both arms ran on Opus 5.5 through `run_overlap.py` from
`find-bugs-variance`, changed to record wall-clock seconds, with two runners
side by side on a 4-CPU machine.

A run counts when its final message has `## Defects`. Overlap is the mean
pairwise Jaccard index of the graders each run passed; the
`defects-section` grader is left out of the counts. `summary.py results/`
prints the table below from the saved runs.

## Results

| PR | Arm | Defects found | Mean | Overlap | Wall minutes | Cost for each run |
|---|---|---|---|---|---|---|
| fastapi, of 14 | `main` | 12, 10, 10 | 10.7 | 0.73 | 9, 11, 10 | $6.73 |
| | sweep rows | 11, 11, 13 | 11.7 | 0.80 | 13, 13, 11 | $17.31 |
| filelock, of 21 | `main` | 10, 13, 10 | 11.0 | 0.69 | 10, 11, 10 | $10.12 |
| | sweep rows | 10, 12 | 11.0 | 0.83 | 14, 11 | $26.07 |
| pipx, of 5 | `main` | 5, 4, 5 | 4.7 | 0.87 | 8, 7, 9 | $6.09 |
| | sweep rows | 4, 4, 4 | 4.0 | 0.73 | 7, 9, 8 | $6.33 |
| urllib3, of 6 | `main` | 4, 5, 4 | 4.3 | 0.87 | 6, 6, 6 | $4.52 |
| | sweep rows | 3, 3, 3 | 3.0 | 1.00 | 6, 6, 6 | $4.81 |

A third sweep-rows run on filelock delivered nothing: `claude -p` exited
after 20 minutes while one of its 15 finders still ran. The first batch
stopped at a five-hour usage limit; its unfinished runs were repeated in
`out2-*` and `out3-*`, and only complete runs are counted.

## What the runs support

- Sweep rows found one more fastapi defect on average, the same on filelock,
  and fewer on pipx and urllib3. Runs agreed more on three PRs, but on urllib3
  they agreed by missing the same three defects in every run.
- On urllib3, finders with rows found the `_tunnel_host` case mismatch in two
  runs and the lead dropped it as *same at base*, though the upper-case pool
  host is new at the head. The state finder of `main` reported the duplicate
  pools in all three runs; with seven rows, mostly *n/a*, the state finder
  reported it once, and the lead dropped it. A row list appears to close the
  search where the list ends.
- Sweep rows were slower on the two large PRs. On fastapi run 0, the twelve
  finders started over 1.6 minutes and the last returned at 10.2 minutes,
  against 6.5 for the four finders of `main`. On the large PRs each run cost
  about 2.5 times as much.
- No arm reached the union of its own three runs in one run: `main` found 10.7
  of a 13-defect union on fastapi and 11.0 of 14 on filelock.

The sweep rows were not adopted.
