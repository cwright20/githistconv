import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from githistconv import (
    FIELD_SEP,
    RECORD_SEP,
    from_jsonl,
    parse_log,
    to_fast_import,
    to_jsonl,
    to_log_format,
)

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


def _commit(hash_, parents, date="2026-01-05T10:00:00-08:00", subject="a commit"):
    return {
        "hash": hash_,
        "author_name": "Jane Doe",
        "author_email": "jane@example.com",
        "date": date,
        "parents": parents,
        "subject": subject,
    }


class ToFastImportTests(unittest.TestCase):
    def test_root_commit_has_no_from_line(self):
        stream = to_fast_import([_commit("abc123", [])])
        self.assertIn("mark :1", stream)
        self.assertNotIn("from", stream)

    def test_linear_history_chains_marks_in_order(self):
        commits = [
            _commit("def456", ["abc123"], date="2026-01-05T10:00:00-08:00"),
            _commit("abc123", [], date="2026-01-04T09:00:00-08:00"),
        ]
        stream = to_fast_import(commits)
        # abc123 has no parents in the set, so it must be assigned mark :1
        # and come first; def456 follows it with "from :1".
        self.assertLess(stream.index("mark :1"), stream.index("mark :2"))
        self.assertIn("from :1", stream)

    def test_merge_commit_gets_merge_line(self):
        commits = [
            _commit("base", []),
            _commit("left", ["base"], date="2026-01-05T10:00:00-08:00"),
            _commit("right", ["base"], date="2026-01-05T11:00:00-08:00"),
            _commit("merged", ["left", "right"], date="2026-01-06T10:00:00-08:00"),
        ]
        stream = to_fast_import(commits)
        self.assertIn("merge :", stream)

    def test_parent_outside_commit_set_is_dropped_not_an_error(self):
        stream = to_fast_import([_commit("abc123", ["not-in-the-set"])])
        self.assertNotIn("from", stream)

    def test_duplicate_hash_raises(self):
        with self.assertRaises(ValueError):
            to_fast_import([_commit("abc123", []), _commit("abc123", [])])

    def test_author_line_uses_raw_date_format(self):
        stream = to_fast_import([_commit("abc123", [])])
        self.assertIn("author Jane Doe <jane@example.com> 1767636000 -0800", stream)

    def test_data_byte_counts_match_payload(self):
        stream = to_fast_import([_commit("abc123", [], subject="fix parser bug")])
        lines = stream.split("\n")
        data_idx = lines.index("data 15")
        self.assertEqual(lines[data_idx + 1], "fix parser bug")


if __name__ == "__main__":
    unittest.main()
