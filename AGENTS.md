# Claude Code Guidelines

## Contributing

Always write a commit message to commit.txt after changes. If a commit message already exists add to it. You can update
the commit title if it is necessary. Make sure the git commit message conforms to the Git standard:

> Commit summary that is short enough for git
>
> Long message detailing everything. There is no text limit.
> In fact, more (if terse) if better.

If the commit message becomes large, suggest to the user that they should commit the code.

## Standards

Project-wide conventions live in `STANDARDS.md`. Do not duplicate those rules elsewhere; link to them instead.

## Rescanning Single Photos

To rescan a single photo after making code changes, use:

```bash
# By photo hash (8 hex characters):
venv/bin/python bnr.py scan --rescan 6dde41fd

# By 1-based index (photo number in database order):
venv/bin/python bnr.py scan --rescan 47
```

This is useful for testing detection changes on specific photos without rescanning the entire album.
