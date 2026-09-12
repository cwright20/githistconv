"""Convert between git log's delimited plaintext output and line-delimited JSON.

git log --format=... produces text meant for a terminal, not a parser. Any
format string that includes a subject line can't be split on plain
whitespace or commas without risking collisions with real commit data. The
trick is to make git emit unlikely-to-collide separators: the ASCII unit
separator (0x1f) between fields and record separator (0x1e) between commits.
Those bytes essentially never show up in commit metadata, so splitting on
them is safe.

Expected git log invocation:

    git log --date=iso-strict \
        --format='%H%x1f%an%x1f%ae%x1f%ad%x1f%P%x1f%s%x1e'

That produces one record per commit: hash, author name, author email,
author date, space-separated parent hashes, subject line.
"""

import argparse
import heapq
import json
import sys
from datetime import datetime

FIELD_SEP = "\x1f"
RECORD_SEP = "\x1e"

FIELDS = ("hash", "author_name", "author_email", "date", "parents", "subject")


def parse_log(text):
    """Parse git's delimited log format into a list of commit dicts."""
    commits = []
    for raw in text.split(RECORD_SEP):
        raw = raw.strip("\n")
        if not raw.strip():
            continue
        fields = raw.split(FIELD_SEP)
        if len(fields) != len(FIELDS):
            raise ValueError(
                "expected %d fields, got %d in record: %r"
                % (len(FIELDS), len(fields), raw)
            )
        commit_hash, author_name, author_email, date, parents, subject = fields
        commits.append(
            {
                "hash": commit_hash,
                "author_name": author_name,
                "author_email": author_email,
                "date": date,
                "parents": parents.split() if parents else [],
                "subject": subject,
            }
        )
    return commits


def to_log_format(commits):
    """Serialize commit dicts back into git's delimited log format."""
    parts = []
    for c in commits:
        fields = [
            c["hash"],
            c["author_name"],
            c["author_email"],
            c["date"],
            " ".join(c["parents"]),
            c["subject"],
        ]
        parts.append(FIELD_SEP.join(fields) + RECORD_SEP + "\n")
    return "".join(parts)


def to_jsonl(commits):
    """Serialize commit dicts as line-delimited JSON, one commit per line."""
    return "\n".join(json.dumps(c, ensure_ascii=False) for c in commits) + "\n"


def from_jsonl(text):
    """Parse line-delimited JSON back into commit dicts."""
    commits = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        commit = json.loads(line)
        missing = set(FIELDS) - set(commit)
        if missing:
            raise ValueError("commit record missing fields: %s" % ", ".join(sorted(missing)))
        commits.append(commit)
    return commits


def _topo_order(commits):
    """Order commits so every parent precedes its children.

    Parents not present in `commits` (history was sliced with -n, or the
    root is out of range) are ignored rather than treated as an error --
    the commit just becomes a root in the rebuilt graph.
    """
    by_hash = {c["hash"]: c for c in commits}
    if len(by_hash) != len(commits):
        raise ValueError("commit list has duplicate hashes")

    indegree = {h: 0 for h in by_hash}
    dependents = {h: [] for h in by_hash}
    for c in commits:
        present_parents = [p for p in c["parents"] if p in by_hash]
        indegree[c["hash"]] = len(present_parents)
        for p in present_parents:
            dependents[p].append(c["hash"])

    heap = [(by_hash[h]["date"], h) for h, d in indegree.items() if d == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        _, h = heapq.heappop(heap)
        order.append(by_hash[h])
        for child in dependents[h]:
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(heap, (by_hash[child]["date"], child))

    if len(order) != len(commits):
        raise ValueError("commit graph has a cycle")
    return order


def _fast_import_person(name, email, date):
    """Format an author/committer line's "name <email> when" portion.

    git fast-import's default date format is "raw": unix seconds followed
    by a UTC offset, e.g. "1234567890 -0800".
    """
    dt = datetime.fromisoformat(date)
    if dt.tzinfo is None:
        raise ValueError("date %r has no UTC offset" % date)
    return "%s <%s> %d %s" % (name, email, int(dt.timestamp()), dt.strftime("%z"))


def to_fast_import(commits, ref="refs/heads/main"):
    """Serialize commit dicts as a git fast-import stream.

    Rebuilds the commit graph (author, date, subject, parents) as a new,
    synthetic history -- useful for producing a throwaway repo with the
    same shape as a real one without copying its actual file contents.
    Each commit gets one file, named after its original hash, so the
    resulting repo has distinct trees to inspect.
    """
    ordered = _topo_order(commits)
    marks = {c["hash"]: i + 1 for i, c in enumerate(ordered)}
    out = []
    for c in ordered:
        person = _fast_import_person(c["author_name"], c["author_email"], c["date"])
        message = c["subject"] + "\n"
        message_bytes = message.encode("utf-8")
        out.append("commit %s\n" % ref)
        out.append("mark :%d\n" % marks[c["hash"]])
        out.append("author %s\n" % person)
        out.append("committer %s\n" % person)
        out.append("data %d\n" % len(message_bytes))
        out.append(message)

        present_parents = [p for p in c["parents"] if p in marks]
        if present_parents:
            out.append("from :%d\n" % marks[present_parents[0]])
            for p in present_parents[1:]:
                out.append("merge :%d\n" % marks[p])

        content_bytes = message.encode("utf-8")
        out.append("M 100644 inline commits/%s.txt\n" % c["hash"])
        out.append("data %d\n" % len(content_bytes))
        out.append(message)
    return "".join(out)


def _read_input(path):
    if path == "-" or path is None:
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_output(path, text):
    if path == "-" or path is None:
        sys.stdout.write(text)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert between git log's delimited output and JSON."
    )
    parser.add_argument(
        "direction",
        choices=("to-json", "from-json", "to-fast-import"),
        help="to-json reads git log output and writes JSON; "
        "from-json reads JSON and writes git log format; "
        "to-fast-import reads JSON and writes a git fast-import stream",
    )
    parser.add_argument(
        "-i", "--input", default="-", help="input file, or - for stdin (default)"
    )
    parser.add_argument(
        "-o", "--output", default="-", help="output file, or - for stdout (default)"
    )
    args = parser.parse_args(argv)

    text = _read_input(args.input)

    if args.direction == "to-json":
        commits = parse_log(text)
        _write_output(args.output, to_jsonl(commits))
    elif args.direction == "from-json":
        commits = from_jsonl(text)
        _write_output(args.output, to_log_format(commits))
    else:
        commits = from_jsonl(text)
        _write_output(args.output, to_fast_import(commits))

    return 0


if __name__ == "__main__":
    sys.exit(main())
