import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from githistconv import FIELD_SEP, RECORD_SEP, from_jsonl, parse_log, to_jsonl, to_log_format

SAMPLE_LOG = FIELD_SEP.join(
    [
        "abc123",
        "Jane Doe",
        "jane@example.com",
        "2026-01-05T10:00:00-08:00",
        "def456",
        "fix off-by-one in parser",
    ]
) + RECORD_SEP + "\n" + FIELD_SEP.join(
    [
        "def456",
        "Jane Doe",
        "jane@example.com",
        "2026-01-04T09:00:00-08:00",
        "",
        "initial commit",
    ]
) + RECORD_SEP + "\n"


class ParseLogTests(unittest.TestCase):
    def test_parses_fields(self):
        commits = parse_log(SAMPLE_LOG)
        self.assertEqual(len(commits), 2)
        first = commits[0]
        self.assertEqual(first["hash"], "abc123")
        self.assertEqual(first["author_name"], "Jane Doe")
        self.assertEqual(first["parents"], ["def456"])
        self.assertEqual(first["subject"], "fix off-by-one in parser")

    def test_root_commit_has_no_parents(self):
        commits = parse_log(SAMPLE_LOG)
        self.assertEqual(commits[1]["parents"], [])

    def test_rejects_malformed_record(self):
        with self.assertRaises(ValueError):
            parse_log("only" + FIELD_SEP + "two" + RECORD_SEP)


class RoundTripTests(unittest.TestCase):
    def test_log_to_json_to_log(self):
        commits = parse_log(SAMPLE_LOG)
        jsonl = to_jsonl(commits)
        restored = from_jsonl(jsonl)
        self.assertEqual(commits, restored)
        log_again = to_log_format(restored)
        self.assertEqual(parse_log(log_again), commits)


if __name__ == "__main__":
    unittest.main()
