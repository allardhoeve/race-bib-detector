# Claude Code Guidelines

## Contributing

Always write a commit message to commit.txt after changes. If a commit message already exists add to it. You can update
the commit title if it is necessary.

If the commit message becomes large, suggest to the user that they should commit the code.

## Standards

Project-wide conventions live in `STANDARDS.md`. Do not duplicate those rules elsewhere; link to them instead.

## Rescanning Single Photos

To rescan a single photo after making code changes, use:

```bash
# By photo hash (8 hex characters):
venv/bin/python scan_album.py 6dde41fd

# By 1-based index (photo number in database order):
venv/bin/python scan_album.py 47
```

This is useful for testing detection changes on specific photos without rescanning the entire album.
