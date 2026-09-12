# githistconv

`git log` is built for reading in a terminal. As soon as you want to do
anything programmatic with commit history — feed it into a script, diff
two branches' metadata, archive it separately from the repo — you're stuck
parsing human-oriented text. Commit subjects can contain almost any
character, so there's no safe delimiter to split on unless you pick one
yourself when you invoke `git log`.

`githistconv` uses ASCII's actual field/record separator bytes (0x1f and
0x1e) for that, since they essentially never show up in real commit data,
and converts the result to line-delimited JSON and back.

## Usage

Get git log output in the expected format:

```sh
git log --date=iso-strict \
    --format='%H%x1f%an%x1f%ae%x1f%ad%x1f%P%x1f%s%x1e' > history.log
```

Convert it to JSON:

```sh
python githistconv.py to-json -i history.log -o history.jsonl
```

Each line of `history.jsonl` is one commit:

```json
{"hash": "abc1234", "author_name": "Jane Doe", "author_email": "jane@example.com", "date": "2026-01-05T10:00:00-08:00", "parents": ["def5678"], "subject": "fix off-by-one in parser"}
```

Convert it back to the delimited log format:

```sh
python githistconv.py from-json -i history.jsonl -o history.log
```

Both subcommands default to stdin/stdout, so they pipe:

```sh
git log --date=iso-strict --format='%H%x1f%an%x1f%ae%x1f%ad%x1f%P%x1f%s%x1e' \
    | python githistconv.py to-json \
    | jq 'select(.parents | length > 1)'
```

That last example filters the JSON down to merge commits with `jq`, which
would be painful to do reliably against raw `git log` text.

You can also turn a `history.jsonl` file into a
[`git fast-import`](https://git-scm.com/docs/git-fast-import) stream. This
rebuilds the commit graph -- author, date, subject, parents -- as new,
synthetic commits with placeholder file contents. It's meant for building a
throwaway repo that has the same shape as a real one (same branching, same
number of commits) without copying any of the original files:

```sh
python githistconv.py to-fast-import -i history.jsonl -o history.fi
git init synthetic-repo && cd synthetic-repo && git fast-import < ../history.fi
```

Commits whose parent hash isn't in the input become roots in the rebuilt
history instead of raising an error, so a filtered or truncated `history.jsonl`
still imports cleanly.

## Status

Early. The core parse/serialize round trip and the fast-import export work
and are tested. Remaining work:

- `--format` flag to pick which fields get parsed/emitted, instead of the
  fixed six
- a CSV output mode
- multi-line commit bodies, not just the subject
- packaging as an installable console script

## License

MIT, see LICENSE.
