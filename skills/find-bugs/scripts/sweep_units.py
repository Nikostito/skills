#!/usr/bin/env python3
"""Seed and check the sweep tables of a thorough search.

  sweep_units.py seed --base <base> --head <head> --repo <checkout> --out <search folder>
  sweep_units.py check <search folder>

Seed lists the units of the change. A source file gives one unit per changed
function or method, named with its class, such as `Lock.release`, and one unit
for its changed lines outside any definition. A test file, and a file that is not
source, such as prose or configuration, gives one unit for the whole file. Each
source unit carries up to eight files outside the change that name it. Seed then
writes one `sweep.md` for each finder of the thorough search, with one empty row
for each unit that finder must answer:

  finder-general                     every unit
  finder-consumers                   every source unit and every prose or configuration file
  finder-inputs, finder-state        every source unit
  finder-fault                       every failure point, when there are five or more
  lead-fault                         every failure point, when there are one to four

A list longer than --shard-size rows splits into numbered shards, such as
finder-inputs-1 and finder-inputs-2, at most --max-shards for one focus. The same
pins give the same units, finders, and rows on every run. Seed prints one line
for each sweep file it writes and records the rows in `sweep-plan.json`. It
refuses a folder that already holds a sweep plan.

Check reads every sweep file the plan names. Each row needs a verdict that starts
`clean:`, `candidate:`, or `n/a:` and then gives its evidence. Check exits 0 when
every row has one, 1 when a row or a file is missing or a verdict is invalid, and
2 for invalid input. Seed exits 2 for invalid input or failed Git operations.
"""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

SOURCE = {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".kt", ".kts",
          ".rb", ".php", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".cs", ".swift", ".m", ".mm", ".scala",
          ".sh", ".bash", ".zsh", ".sql", ".vue", ".svelte", ".dart", ".ex", ".exs", ".lua", ".pl", ".pm"}
SKIP = {"node_modules", "vendor", "dist", "build", "__pycache__", "generated"}
DEFINITIONS = (
    re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*class\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"),
    re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)"),
    re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?(?:class|interface|struct|enum|trait|type)\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*(?:public|private|protected|internal|static|final|abstract|override|virtual|async|\s)*"
               r"[A-Za-z_][\w<>\[\],.?]*\s+([A-Za-z_]\w*)\s*\([^;]*\)\s*\{"),
)
HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
VERDICT = re.compile(r"^(clean|candidate|n/a):\s*\S", re.I)
CONSUMER_CAP = 8
UNIT_FOCUSES = (("general", {"source", "test", "text"}), ("consumers", {"source", "text"}),
                ("inputs", {"source"}), ("state", {"source"}))
TEST = re.compile(r"(^|/)(tests?|__tests__|spec|specs|testing)/|(^|/)test_[^/]*$|_test\.[^/.]+$|\.(test|spec)\.[^/.]+$")
QUESTIONS = {
    "general": "Under what input, version, timing, or caller does this unit misbehave?",
    "consumers": "What does each caller, subclass, hook, generic protocol, document, and type declaration "
                 "outside the change receive or observe from this unit at the base and at the head?",
    "inputs": "Which None, empty, boundary, malformed, default, option, runtime, or platform value does this "
              "unit now treat differently, and what results at the base and at the head?",
    "state": "What state does this unit add or share that outlives one call, and what do two threads or tasks, "
             "or a reader after a change, see there?",
    "fault": "When this call fails part-way, or the path holds what another process could leave there, "
             "what remains, and what error does the caller see?",
}


def git(repo, *args):
    # Read the requested checkout, not a repository selected by inherited Git state.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    result = subprocess.run(["git", "-C", str(repo), *args], env=env, capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"git failed with exit {result.returncode}")
    return result.stdout


def indent(text):
    expanded = text.expandtabs(8)
    return len(expanded) - len(expanded.lstrip())


def definitions(lines):
    found = []
    for number, text in enumerate(lines, 1):
        for pattern in DEFINITIONS:
            match = pattern.match(text)
            if match:
                found.append((number, indent(text), match.group(1)))
                break
    return found


def enclosing(defs, number, depth):
    """Return the dotted path of the definitions that contain a changed line, or None."""
    names, limit = [], None
    for line, own, name in reversed(defs):
        if line > number:
            continue
        inside = own < depth or (line == number and not names)
        if inside and (limit is None or own < limit):
            names.append(name)
            limit = own
            if own == 0:
                break
    return ".".join(reversed(names)) or None


def ranges(numbers):
    spans = []
    for number in sorted(set(numbers)):
        if spans and number == spans[-1][1] + 1:
            spans[-1][1] = number
        else:
            spans.append([number, number])
    return ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in spans)


def parse(diff):
    files, current, hunk, header = [], None, None, False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            header, current, hunk = True, None, None
            continue
        if header and line.startswith("--- "):
            old = None if line == "--- /dev/null" else line[4:]
            current = {"old_path": old, "path": old, "hunks": []}
            files.append(current)
            continue
        if header and line.startswith("+++ "):
            if line != "+++ /dev/null":
                current["path"] = line[4:]
            continue
        match = HUNK.match(line)
        if match and current is not None:
            header = False
            hunk = {"old": int(match.group(1)), "new": int(match.group(2)), "added": [], "removed": []}
            current["hunks"].append(hunk)
            continue
        if header or hunk is None or not line or line[0] not in "+-":
            continue
        side, key = ("added", "new") if line[0] == "+" else ("removed", "old")
        hunk[side].append((hunk[key], line[1:]))
        hunk[key] += 1
    return files


def show(repo, rev, path):
    if path is None:
        return []
    try:
        return git(repo, "show", f"{rev}:{path}").splitlines()
    except ValueError:
        return []


def is_source(path):
    return PurePosixPath(path).suffix.lower() in SOURCE


def kind(path):
    if not is_source(path):
        return "text"
    return "test" if TEST.search(path) else "source"


def consumers(repo, head, symbol, changed, cache):
    symbol = symbol.rsplit(".", 1)[-1]
    if symbol.startswith("__") and symbol.endswith("__"):
        return []
    if symbol not in cache:
        try:
            listing = git(repo, "grep", "-l", "-w", "-F", symbol, head)
        except ValueError:
            listing = ""
        cache[symbol] = [line.split(":", 1)[-1] for line in listing.splitlines()]
    return [path for path in cache[symbol]
            if path not in changed and is_source(path) and not SKIP & set(PurePosixPath(path).parts)]


def units(repo, base, head):
    files = parse(git(repo, "diff", "--unified=0", "--no-color", "--no-prefix", "--no-ext-diff", f"{base}..{head}"))
    changed = {file["path"] for file in files}
    found, cache = [], {}
    for file in files:
        path = file["path"]
        if kind(path) != "source":
            added = [n for hunk in file["hunks"] for n, _ in hunk["added"]]
            removed = [n for hunk in file["hunks"] for n, _ in hunk["removed"]]
            found.append({"id": f"{path} (file)", "path": path, "kind": kind(path), "lines": ranges(added),
                          "removed": ranges(removed), "consumers": []})
            continue
        head_lines, base_lines = show(repo, head, path), show(repo, base, file["old_path"])
        head_defs, base_defs = definitions(head_lines), definitions(base_lines)
        grouped = {}
        for hunk in file["hunks"]:
            for side, defs in (("added", head_defs), ("removed", base_defs)):
                for number, text in hunk[side]:
                    if not text.strip():
                        continue
                    symbol = enclosing(defs, number, indent(text))
                    entry = grouped.setdefault(symbol or "module level", {"symbol": symbol, "added": [], "removed": []})
                    entry[side].append(number)
        if not grouped:
            grouped["module level"] = {"symbol": None, "added": [n for h in file["hunks"] for n, _ in h["added"]], "removed": []}
        for key, entry in grouped.items():
            listed = consumers(repo, head, entry["symbol"], changed, cache) if entry["symbol"] else []
            found.append({"id": f"{path}::{key}", "path": path, "kind": "source", "lines": ranges(entry["added"]),
                          "removed": ranges(entry["removed"]), "consumers": listed[:CONSUMER_CAP],
                          "more": max(0, len(listed) - CONSUMER_CAP)})
    return sorted(found, key=lambda unit: unit["id"])


def failure_points(repo, base, head):
    spec = importlib.util.spec_from_file_location("failure_points", Path(__file__).with_name("failure_points.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    diff = git(repo, "diff", "--unified=0", "--no-color", "--no-ext-diff", f"{base}..{head}")
    return [{"id": f"{path}:{number}", "path": path, "lines": str(number), "context": context, "text": text}
            for path, number, context, text in module.points(diff, lambda path: show(repo, head, path))]


def shards(rows, size, limit):
    count = min(limit, max(1, math.ceil(len(rows) / size)))
    step = math.ceil(len(rows) / count) if rows else 0
    return [rows[i:i + step] for i in range(0, len(rows), step)] if rows else []


def cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def table(focus, label, rows, base, head):
    out = [f"# Sweep: {label}", "", f"Base: `{base}`. Head: `{head}`.", "",
           f"Question for every row: {QUESTIONS[focus]}", "",
           "Write one verdict in the last cell of every row, then its evidence:",
           "`clean: <the line or observation that settles it>`, `candidate: <the short name of the candidate you "
           "return>`, or `n/a: <the source fact that makes this question not apply>`.", ""]
    if focus == "fault":
        out += ["| Unit | Call | Verdict |", "|---|---|---|"]
        out += [f"| `{cell(row['id'])}` | {cell((row['context'] + ': ') if row['context'] else '')}"
                f"`{cell(row['text'][:100])}` | |" for row in rows]
    else:
        out += ["| Unit | Lines at head | Lines at base | Consumers outside the change | Verdict |",
                "|---|---|---|---|---|"]
        for row in rows:
            names = ", ".join(f"`{cell(path)}`" for path in row["consumers"]) or "none listed"
            if row.get("more"):
                names += f", and {row['more']} more"
            out.append(f"| `{cell(row['id'])}` | {row['lines'] or 'none'} | {row['removed'] or 'none'} | {names} | |")
    return "\n".join(out) + "\n"


def seed(args):
    out = Path(args.out)
    if (out / "sweep-plan.json").exists():
        raise ValueError(f"{out / 'sweep-plan.json'} exists: seed a new search folder")
    base = git(args.repo, "rev-parse", "--verify", f"{args.base}^{{commit}}").strip()
    head = git(args.repo, "rev-parse", "--verify", f"{args.head}^{{commit}}").strip()
    found, points = units(args.repo, base, head), failure_points(args.repo, base, head)
    lists = [(focus, [unit for unit in found if unit["kind"] in kinds]) for focus, kinds in UNIT_FOCUSES]
    if len(points) >= 5:
        lists.append(("fault", points))
    plan = {"base": base, "head": head, "units": len(found), "failure_points": len(points), "sweeps": []}
    if points and len(points) < 5:
        plan["sweeps"].append(write(out, "lead-fault", "fault", "fault, for the lead", points, base, head))
    for focus, rows in lists:
        parts = shards(rows, args.shard_size, args.max_shards)
        for number, part in enumerate(parts, 1):
            name = f"finder-{focus}" if len(parts) == 1 else f"finder-{focus}-{number}"
            label = focus if len(parts) == 1 else f"{focus}, shard {number} of {len(parts)}"
            plan["sweeps"].append(write(out, name, focus, label, part, base, head))
    (out / "sweep-plan.json").write_text(json.dumps(plan, indent=1) + "\n")
    print(f"{len(found)} units, {len(points)} failure points. Base {base[:12]}, head {head[:12]}.")
    for sweep in plan["sweeps"]:
        print(f"{sweep['file']}\t{sweep['focus']}\t{len(sweep['rows'])} rows")


def write(out, name, focus, label, rows, base, head):
    folder = out / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "sweep.md").write_text(table(focus, label, rows, base, head))
    return {"file": f"{name}/sweep.md", "focus": focus, "rows": [row["id"] for row in rows]}


def verdicts(text):
    found = {}
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [part.strip() for part in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if len(cells) < 2 or cells[0].lower() == "unit" or all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
            continue
        found[cells[0].strip("`").replace("\\|", "|")] = cells[-1]
    return found


def check(folder):
    plan = json.loads((Path(folder) / "sweep-plan.json").read_text())
    problems, totals = [], {"clean": 0, "candidate": 0, "n/a": 0}
    for sweep in plan["sweeps"]:
        path = Path(folder) / sweep["file"]
        if not path.is_file():
            problems.append(f"{sweep['file']}: missing")
            continue
        found = verdicts(path.read_text())
        for row in sweep["rows"]:
            verdict = found.get(row)
            if verdict is None:
                problems.append(f"{sweep['file']}: row {row} is missing")
            elif not VERDICT.match(verdict):
                problems.append(f"{sweep['file']}: row {row} has no valid verdict")
            else:
                totals[verdict.split(":", 1)[0].lower()] += 1
    rows = sum(len(sweep["rows"]) for sweep in plan["sweeps"])
    if problems:
        print(f"{len(problems)} of {rows} rows or files lack a verdict:")
        print("\n".join(f"- {problem}" for problem in problems))
        print("A verdict starts with clean:, candidate:, or n/a: and then gives its evidence.")
        return 1
    print(f"Every row of {len(plan['sweeps'])} sweeps has a verdict: {totals['clean']} clean, "
          f"{totals['candidate']} candidate, {totals['n/a']} n/a.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    seeding = commands.add_parser("seed")
    seeding.add_argument("--base", required=True)
    seeding.add_argument("--head", required=True)
    seeding.add_argument("--repo", default=".")
    seeding.add_argument("--out", required=True)
    seeding.add_argument("--shard-size", type=int, default=20)
    seeding.add_argument("--max-shards", type=int, default=3)
    checking = commands.add_parser("check")
    checking.add_argument("folder")
    args = parser.parse_args(argv)
    try:
        if args.command == "seed":
            if args.shard_size < 1 or args.max_shards < 1:
                raise ValueError("--shard-size and --max-shards must be at least 1")
            seed(args)
            return 0
        return check(args.folder)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
