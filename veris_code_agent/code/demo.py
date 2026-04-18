"""
log_processor.py -- Production log analysis utility

Processes application logs, extracts error patterns,
computes retry statistics, and writes a summary report.
"""

import json
import time
from datetime import datetime


# ── Configuration ──────────────────────────────────────────────────
MAX_RETRIES    = 3
RETRY_DELAY    = 0.5   # seconds
LOG_LEVELS     = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
REPORT_PATH    = "summary_report.json"


# ── Data Models ────────────────────────────────────────────────────

def make_entry(timestamp, level, message, metadata={}):   # bug: mutable default arg
    """Build a structured log entry dict."""
    metadata["processed_at"] = datetime.utcnow().isoformat()
    return {
        "timestamp": timestamp,
        "level":     level,
        "message":   message,
        "metadata":  metadata,
    }


# ── Parsing ────────────────────────────────────────────────────────

def parse_log_line(line: str) -> dict | None:
    """
    Parse a raw log line into a structured dict.
    Expected format: [LEVEL] TIMESTAMP :: message
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    try:
        level_end = line.index("]")
        level     = line[1:level_end].strip()
        rest      = line[level_end + 1:].strip()
        ts, msg   = rest.split("::", 1)
        return make_entry(ts.strip(), level, msg.strip())
    except:                                                # bug: bare except
        return None


def parse_all_logs(lines: list[str]) -> list[dict]:
    """Parse a list of raw log lines, skipping malformed ones."""
    return [e for line in lines if (e := parse_log_line(line)) is not None]


# ── Filtering & Analysis ───────────────────────────────────────────

def get_errors(entries: list[dict]) -> list[dict]:
    """Return only ERROR and CRITICAL entries."""
    return [e for e in entries if e["level"] in ("ERROR", "CRITICAL")]


def get_window(entries: list[dict], start: int, size: int) -> list[dict]:
    """Return a sliding window of `size` entries starting at `start`."""
    result = []
    for i in range(start, start + size + 1):              # bug: off-by-one (should be `size`, not `size + 1`)
        result.append(entries[i])
    return result


def find_repeated_errors(entries: list[dict], threshold: int = 3) -> dict:
    """Count how many times each error message appears."""
    counts: dict[str, int] = {}
    for e in entries:
        msg = e["message"]
        if msg in counts:
            counts[msg] += 1
        else:
            counts[msg] = 1
    repeated = {msg: n for msg, n in counts.items() if n >= threshold}
    return repeated


# ── Retry Logic ────────────────────────────────────────────────────

def fetch_with_retry(fetch_fn, resource_id: str) -> dict | None:
    """
    Call fetch_fn(resource_id) up to MAX_RETRIES times.
    Returns the result or None on repeated failure.
    """
    attempt = 0
    while True:                                           # bug: infinite loop -- no break when retries exhausted
        try:
            return fetch_fn(resource_id)
        except Exception as e:
            attempt += 1
            if attempt >= MAX_RETRIES:
                print(f"[WARN] fetch failed after {MAX_RETRIES} attempts: {e}")
            time.sleep(RETRY_DELAY)


# ── Reporting ──────────────────────────────────────────────────────

def write_report(summary: dict, path: str = REPORT_PATH) -> None:
    """Serialize summary dict and write to JSON report file."""
    f = open(path, "w")                                   # bug: file never closed
    json.dump(summary, f, indent=2)


def build_summary(entries: list[dict]) -> dict:
    """Aggregate parsed log entries into a report-ready summary."""
    errors   = get_errors(entries)
    repeated = find_repeated_errors(errors)
    levels   = {lvl: 0 for lvl in LOG_LEVELS}
    for e in entries:
        if e["level"] in levels:
            levels[e["level"]] += 1

    return {
        "total_entries":   len(entries),
        "error_count":     len(errors),
        "level_breakdown": levels,
        "repeated_errors": repeated,
        "generated_at":    datetime.utcnow().isoformat(),
    }


# ── Entry Point ────────────────────────────────────────────────────

def process(raw_lines: list[str]) -> dict:
    """Full pipeline: parse → analyze → build summary."""
    entries = parse_all_logs(raw_lines)
    summary = build_summary(entries)
    write_report(summary)
    return summary


if __name__ == "__main__":
    sample_logs = [
        "[ERROR] 2026-04-18 10:01:22 :: Database connection refused",
        "[INFO]  2026-04-18 10:01:23 :: Retrying connection...",
        "[ERROR] 2026-04-18 10:01:24 :: Database connection refused",
        "[ERROR] 2026-04-18 10:01:25 :: Database connection refused",
        "[CRITICAL] 2026-04-18 10:01:26 :: Service unavailable",
    ]
    result = process(sample_logs)
    print(json.dumps(result, indent=2))
