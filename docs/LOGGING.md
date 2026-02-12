
# LOGGING STANDARDS

- Use `logging.getLogger(__name__)` in modules; do not use `print()` for runtime output.
- Configure logging once in entrypoints using `logging_utils.configure_logging()`.
- Default logging level is `INFO`. Use `DEBUG` for detailed per-item output, `WARNING` for recoverable issues, and `ERROR`/`CRITICAL` for failures.
- When handling exceptions, use `logger.exception(...)` to capture stack traces.
- CLI endpoints must expose:
  - `--log-level` (`debug`, `info`, `warning`, `error`, `critical`) to set an explicit level.
  - `-v/--verbose` and `-q/--quiet` to adjust level relative to `INFO` (more `-v` = more detail, more `-q` = less detail).
  - `--log-level` overrides `-v/--quiet` when provided.