# Thorough search

Read this when the user or the caller asks for a thorough search. Finders read
the change in parallel, each with its own focus and its own fixed rows: a
script lists the units of the change, and every finder gives a verdict for
every unit in its rows. The same pins give the same rows on every run, so
each run covers the same ground and a missed defect traces to one row. You run
the shared tools once, merge what the finders return, record a decision for
every candidate, and confirm each delivered candidate once, with the
confirmations in parallel. A thorough search costs several times one read and
takes about as long as its slowest finder plus one confirmation.

## Contents

- [Seed the sweeps](#seed-the-sweeps)
- [Prepare the worktrees once](#prepare-the-worktrees-once)
- [Start the finders](#start-the-finders)
- [Run the shared tools once](#run-the-shared-tools-once)
- [Decide every candidate](#decide-every-candidate)
- [Confirm in parallel](#confirm-in-parallel)

## Seed the sweeps

Run, with this search's new folder as `--out`:

```bash
python3 <package>/skills/find-bugs/scripts/sweep_units.py seed --base <base> --head <head> --repo <checkout> --out <this search's folder>
```

It lists the units of the change: each changed function or method, the
changed lines outside any definition, and each changed test, prose, or
configuration file as one unit. It writes one `sweep.md` for each finder, with
one row for each unit that finder answers, and prints one line for each:

- `finder-general`: every unit.
- `finder-consumers`: every source unit and every prose or configuration file.
- `finder-inputs` and `finder-state`: every source unit.
- `finder-fault`: every line that `failure_points.py` lists, when it lists five
  or more. With one to four lines, `lead-fault` holds them for you: make each
  listed line fail once yourself in step 3 and write its verdict.

A list longer than 20 rows splits into numbered shards, such as
`finder-inputs-1` and `finder-inputs-2`, each started as its own finder. The
printed lines are the finders to start; start them all.

## Prepare the worktrees once

Before you start the finders, add two disposable worktrees in this search's
folder: `git -C <checkout> worktree add --detach <this search's folder>/base <base>`
and the same for the head at `<this search's folder>/head`. Copy into each the
generated or untracked files that the conditions name, such as a version file.
Every finder and confirmer runs its probes against these two worktrees and
changes nothing in them; a probe that must edit source makes its own worktree in
its own folder. Remove the worktrees when the search is done.

## Start the finders

Through [native delegation](../WORKERS.md), start every finder that the seed
printed, in one message. Give each this assignment, its focus paragraph, and
nothing from your own reading or the shared tools; a finder that knows what was
found looks where the others looked:

> You are one of several independent finders for one change. You do not see the others' work. Repository: `<path>`. Base: `<sha>`. Head: `<sha>`. Base worktree: `<path>`. Head worktree: `<path>`. Conditions: `<dependency and environment notes from step 1>`. Work in `<this search's folder>/<finder folder>/` and leave the checkout and both worktrees unchanged. Your rows are in `<finder folder>/sweep.md`: answer the question at its top for every row, and write the row's verdict in its last cell as `clean:`, `candidate:`, or `n/a:`, each followed by the line or observation that settles it. Follow steps 2 and 3 of `<package>/skills/find-bugs/SKILL.md` for these rows as one read: search alone and start no workers. Report a defect you meet outside your rows as well. The lead runs the static deltas, `weakened_checks.py`, and the base's tests for this search, so begin with the reading. Run code when running it is how you find out, because the source leaves the outcome open: inject a failure, force an interleaving, try an input, or compare base and head on a scenario you suspect. Save each probe you run with its command and result. When the source already shows the outcome, return the candidate as *inferred* with the probe that would show it; the lead confirms each distinct candidate once. Return every candidate you could not contradict: location, trigger, base result, head result, the contract it breaks, and the saved probe, or *inferred* with the probe to run. List the leads you dropped, one line each with the counterevidence. Do not rank or write a report.

The general finder gets the assignment as it stands; it catches what falls
outside the focuses. Each focused finder also gets the paragraph for its
focus, and a shard gets the paragraph of its focus.

The **consumers finder**: *Search only what code outside the change sees.
List the callers of each changed function; the subclasses and overrides of
each changed class; the callbacks and hooks that users supply; the generic
protocols that users apply to changed objects, such as copy, pickle, equality,
and iteration; and the docs, examples, and type declarations that describe the
changed code. For each, compare what it receives or observes at the base and
at the head.*

The **inputs finder**: *Search only the values that the changed code now
treats differently: None, empty, boundary, and malformed arguments; each
default; each option that the changed path reads or now ignores, alone and
combined with the others; and each runtime, operating system, and filesystem
that the project supports. For each value, compare the base and head results.*

The **state finder**: *Search only the state this change adds or shares:
caches, lazy initialization, counters, and containers that outlive one call.
For each, probe what two threads or tasks see when they reach it at once, and
what a reader sees after it changes.*

The **fault finder**: *Search only what happens when the outside world does
not cooperate. Your rows are the added lines that open, read, write, close,
rename, delete, lock, spawn, or connect. Make each one fail in turn, part-way
through the change's sequence, with an error that call can raise, and record
what remains: open descriptors, partial or orphaned files, a flag or counter
still set, and the error type the caller sees against the one the code
documents. Then give each path the change opens or creates what another process
or account could leave there: a directory, a symlink, a file owned by another
user, a file without read permission. Report a candidate only when the base
handled the same condition, or when the change documents how it handles it.*

Where no delegation tool is available, as can happen for a worker, answer the
rows of `finder-general` yourself as one read and say so in the delivery.

When a finder returns, read its `sweep.md`. A finder that left rows empty gets
one continuation for those rows through the host's message to that finder;
rows still empty after it are yours to answer. A finder that fails twice is
*not run*: answer its rows yourself, or state them in the delivery as not
checked.

## Run the shared tools once

While the finders run, run these yourself, once for the whole search. Each
result you keep is a candidate from finder `lead`.

- The static deltas, as step 2 says.
- `weakened_checks.py`, as step 2 says.
- The base's tests against the head. In a third worktree at the head, in this
  search's folder, restore the test files that the change edits or deletes to
  their base versions: `git -C <worktree> checkout <base> -- <test files>`. Run
  those files. A test that passes at the base and fails there pinned a behavior
  that the change altered. Skip this when the change edits no test file, and
  record that.
- The `lead-fault` rows, when the seed wrote them.

A caller can add its own leads, such as suspected defects from its reading;
they are candidates from finder `caller`.

## Decide every candidate

When every finder has returned or is recorded as *not run*, write
`candidates.md` in this search's folder, one row for each candidate that a
finder, a shared tool, or the caller returned:

```markdown
| Candidate | Finders | Disposition |
|---|---|---|
| release() blocks a waiting acquire | consumers, state | delivered |
| same, through release(force=True) | inputs | merged into release() blocks a waiting acquire |
| lifetime warning text | consumers | dropped: same at base: base prints the same text, probe p3 |
| duplicate pool for an encoded host | inputs | delivered |
```

A disposition is `delivered`, `merged into <candidate>`, or a drop that names
one of three grounds and then the evidence for it:

- `dropped: absent at head: <source line or probe result>`
- `dropped: same at base: <source line or probe result>`
- `dropped: documented intent: <the text in the change that documents it>`

Merge candidates that share a location and mechanism, keep every distinct
trigger, and list a merged row's finders on the row it merged into. A
candidate from one finder is as likely real as one from several: confirm it, do
not vote. A small consequence is not a ground for a drop: a behavior that the
head shows and the base does not stays `delivered`, and you deliver it under
`## Minor observations`, naming why it is minor.

Then run both checks:

```bash
python3 <package>/skills/find-bugs/scripts/sweep_units.py check <this search's folder>
python3 <package>/skills/find-bugs/scripts/remaining.py <this search's folder>/candidates.md
```

The first exits 1 while a sweep row has no verdict; the second exits 1 while a
candidate has no disposition or a drop names no allowed ground.

## Confirm in parallel

Step 3's confirmation of each delivered candidate runs in parallel. Through
native delegation, start one confirmer for each delivered row in one message.
Give each the row, the finder's saved probe or the probe it named, both
worktrees, the conditions, and `<this search's folder>/confirm-<n>/` as its
folder, with this task: *Run this probe at the base and at the head, save the
script before you run it, and return the exact command, both outputs, and
whether the head differs from the base as the row predicts. Change nothing in
the worktrees.* Read each returned output yourself before you label a finding
*executed*. A confirmer that fails twice leaves its row for you to probe.
Without a delegation tool, run the probes yourself.

Done when every finder has returned or is recorded as *not run* with its
reason, each shared tool ran or has a recorded reason, both checks exit 0, and
each delivered candidate has a confirmation result or a recorded reason why
none ran.
