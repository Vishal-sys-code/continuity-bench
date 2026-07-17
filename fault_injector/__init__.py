# continuity-bench :: fault_injector
"""Deterministic failure injection for failover testing."""

from fault_injector.injector import (
    FaultInjector,
    FaultInjector as Injector,
    FailureEvent,
    FailureMode,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
    create_injector,
    generate_sweep_schedule,
    load_manifest,
)

__all__ = [
    "FaultInjector",
    "Injector",
    "FailureEvent",
    "FailureMode",
    "ProviderError",
    "ProviderTimeoutError",
    "RateLimitError",
    "create_injector",
    "generate_sweep_schedule",
    "load_manifest",
]
