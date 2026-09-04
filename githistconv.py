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
import json
import sys

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
        choices=("to-json", "from-json"),
        help="to-json reads git log output and writes JSON; "
        "from-json reads JSON and writes git log format",
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
    else:
        commits = from_jsonl(text)
        _write_output(args.output, to_log_format(commits))

    return 0


if __name__ == "__main__":
    sys.exit(main())
