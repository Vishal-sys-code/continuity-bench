# continuity-bench :: bench_logging
"""Instrumentation and metrics collection.

Named 'bench_logging' to avoid shadowing Python's stdlib 'logging' module.
"""

from bench_logging.logger import BenchLogger, generate_request_id

__all__ = ["BenchLogger", "generate_request_id"]
