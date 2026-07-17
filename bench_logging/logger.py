#!/usr/bin/env python3
"""
logging/logger.py — JSON-lines structured logging for continuity-bench
=======================================================================

Provides a consistent logging interface that writes every proxy
request/response to a JSON-lines (.jsonl) file.

Log schema (one JSON object per line):
    {
        "timestamp":            str,   # ISO-8601 with timezone
        "request_id":           str,   # unique per-request UUID
        "conversation_id":      str,   # e.g. "conv-042"
        "turn_index":           int,   # 0-based index into turns[]
        "provider":             str,   # "openai" | "anthropic"
        "model":                str,   # actual model used
        "failed_over":          bool,  # true if this was a failover retry
        "failover_from":        str?,  # original provider that failed (if failed_over)
        "failure_mode":         str?,  # "timeout" | "api_error" | "rate_limit"
        "latency_ms":           float, # total request latency
        "time_to_first_token_ms": float?, # TTFT (null if non-streaming)
        "response_text":        str,   # full assistant response
        "error":                str?,  # error message if request failed
        "system":               str,   # "baseline" | "treatment"
    }

Usage:
    logger = BenchLogger(log_dir="logging/", system_name="baseline")
    logger.log_request(
        request_id="req-001",
        conversation_id="conv-042",
        turn_index=3,
        provider="openai",
        model="gpt-4o",
        failed_over=False,
        latency_ms=450.2,
        response_text="Hello!",
    )
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return f"req-{uuid.uuid4().hex[:12]}"


class BenchLogger:
    """Thread-safe JSON-lines logger for continuity-bench proxy traffic.

    Parameters
    ----------
    log_dir : str | Path
        Directory to write log files into.
    system_name : str
        Identifier for the proxy system ("baseline" or "treatment").
    log_filename : str | None
        Override the log filename. Defaults to "{system_name}_log.jsonl".
    """

    def __init__(
        self,
        log_dir: str | Path,
        system_name: str,
        log_filename: str | None = None,
    ) -> None:
        self.log_dir = Path(log_dir)
        self.system_name = system_name
        self.log_filename = log_filename or f"{system_name}_log.jsonl"
        self._lock = threading.Lock()

        # Ensure the log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self.log_dir / self.log_filename

    @property
    def log_path(self) -> Path:
        """Return the full path to the log file."""
        return self._log_path

    def _write_entry(self, entry: dict[str, Any]) -> None:
        """Atomically append a JSON-lines entry to the log file."""
        line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line)

    def log_request(
        self,
        *,
        request_id: str,
        conversation_id: str,
        turn_index: int,
        provider: str,
        model: str = "",
        failed_over: bool = False,
        failover_from: Optional[str] = None,
        failure_mode: Optional[str] = None,
        latency_ms: float = 0.0,
        time_to_first_token_ms: Optional[float] = None,
        response_text: str = "",
        error: Optional[str] = None,
    ) -> dict[str, Any]:
        """Log a single request/response event.

        Returns the logged entry dict for testing convenience.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "conversation_id": conversation_id,
            "turn_index": turn_index,
            "provider": provider,
            "model": model,
            "failed_over": failed_over,
            "failover_from": failover_from,
            "failure_mode": failure_mode,
            "latency_ms": round(latency_ms, 2),
            "time_to_first_token_ms": (
                round(time_to_first_token_ms, 2)
                if time_to_first_token_ms is not None
                else None
            ),
            "response_text": response_text,
            "error": error,
            "system": self.system_name,
        }

        self._write_entry(entry)
        return entry

    def read_logs(self) -> list[dict[str, Any]]:
        """Read all log entries from the log file. Useful for analysis."""
        if not self._log_path.exists():
            return []

        entries: list[dict[str, Any]] = []
        with open(self._log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def clear(self) -> None:
        """Clear the log file."""
        with self._lock:
            if self._log_path.exists():
                self._log_path.unlink()
