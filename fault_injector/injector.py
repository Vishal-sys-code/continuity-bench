#!/usr/bin/env python3
"""
fault_injector/injector.py — Deterministic failure injection
=============================================================

Provides a configurable fault injection layer that simulates provider
failures during multi-turn conversations. The injector is deterministic:
given the same seed, it produces the same failure schedule, enabling
reproducible experiments.

Failure modes:
    - TIMEOUT    : simulates a provider timeout (raises TimeoutError)
    - API_ERROR  : simulates a 500/503 provider error (raises ProviderError)
    - RATE_LIMIT : simulates a 429 rate-limit hit (raises RateLimitError)

Usage:
    injector = FaultInjector(seed=42, failure_rate=0.3)
    if injector.should_fail(conversation_id="conv-001", turn_index=3):
        raise injector.get_failure(conversation_id="conv-001", turn_index=3)
"""

from __future__ import annotations

import enum
import hashlib
import random
from dataclasses import dataclass, field
from typing import Optional


# ─── Custom exceptions ─────────────────────────────────────────────────────────

class ProviderError(Exception):
    """Simulated provider-side error (5xx)."""

    def __init__(self, message: str = "Simulated provider error (503)", status_code: int = 503):
        self.status_code = status_code
        super().__init__(message)


class RateLimitError(Exception):
    """Simulated rate-limit error (429)."""

    def __init__(self, message: str = "Simulated rate limit exceeded (429)", retry_after: float = 1.0):
        self.retry_after = retry_after
        super().__init__(message)


class ProviderTimeoutError(Exception):
    """Simulated provider timeout."""

    def __init__(self, message: str = "Simulated provider timeout", timeout_seconds: float = 30.0):
        self.timeout_seconds = timeout_seconds
        super().__init__(message)


# ─── Failure modes ──────────────────────────────────────────────────────────────

class FailureMode(enum.Enum):
    TIMEOUT = "timeout"
    API_ERROR = "api_error"
    RATE_LIMIT = "rate_limit"


# ─── Failure schedule entry ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class FailureEvent:
    """A planned failure event."""
    conversation_id: str
    turn_index: int
    mode: FailureMode
    fallback_provider: Optional[str] = None


# ─── Fault injector ────────────────────────────────────────────────────────────

@dataclass
class FaultInjector:
    """Deterministic fault injector for provider failover testing.

    Parameters
    ----------
    seed : int
        Random seed for deterministic failure scheduling.
    failure_rate : float
        Probability of failure per (conversation, turn) pair (0.0–1.0).
    failure_modes : list[FailureMode] | None
        Which failure modes to sample from. Defaults to all modes.
    fixed_schedule : list[FailureEvent] | None
        If provided, use this explicit schedule instead of probabilistic
        injection. Overrides failure_rate.
    """

    seed: int = 42
    failure_rate: float = 0.3
    failure_modes: list[FailureMode] = field(
        default_factory=lambda: list(FailureMode),
    )
    fixed_schedule: Optional[list[FailureEvent]] = None

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)
        # Pre-build a lookup set for fixed schedules
        self._fixed_lookup: set[tuple[str, int]] = set()
        self._fixed_modes: dict[tuple[str, int], FailureMode] = {}
        self._fixed_providers: dict[tuple[str, int], str] = {}
        if self.fixed_schedule:
            for event in self.fixed_schedule:
                key = (event.conversation_id, event.turn_index)
                self._fixed_lookup.add(key)
                self._fixed_modes[key] = event.mode
                if event.fallback_provider:
                    self._fixed_providers[key] = event.fallback_provider

    def _deterministic_hash(self, conversation_id: str, turn_index: int) -> float:
        """Produce a deterministic float in [0, 1) from (conv_id, turn, seed).

        Uses SHA-256 so the distribution is uniform and independent of
        Python's hash() seed randomisation.
        """
        raw = f"{self.seed}:{conversation_id}:{turn_index}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        # Take first 8 hex chars → 32-bit int → normalise to [0, 1)
        return int(digest[:8], 16) / 0xFFFFFFFF

    def should_fail(self, conversation_id: str, turn_index: int) -> bool:
        """Decide whether this (conversation, turn) should experience a failure.

        If a fixed_schedule is set, checks membership.  Otherwise uses
        the deterministic hash against failure_rate.
        """
        if self.fixed_schedule is not None:
            return (conversation_id, turn_index) in self._fixed_lookup

        return self._deterministic_hash(conversation_id, turn_index) < self.failure_rate

    def get_failure_mode(self, conversation_id: str, turn_index: int) -> FailureMode:
        """Return the failure mode for a given (conversation, turn).

        Deterministic: same inputs → same mode.
        """
        if self.fixed_schedule is not None:
            key = (conversation_id, turn_index)
            if key in self._fixed_modes:
                return self._fixed_modes[key]

        # Deterministic selection based on hash
        raw = f"{self.seed}:mode:{conversation_id}:{turn_index}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        idx = int(digest[:8], 16) % len(self.failure_modes)
        return self.failure_modes[idx]

    def get_failure_event(self, conversation_id: str, turn_index: int) -> Optional[FailureEvent]:
        """Return the complete failure event if a failure is scheduled, including assigned fallback."""
        if not self.should_fail(conversation_id, turn_index):
            return None
            
        mode = self.get_failure_mode(conversation_id, turn_index)
        fallback = None
        if self.fixed_schedule is not None:
            key = (conversation_id, turn_index)
            fallback = self._fixed_providers.get(key)
            
        return FailureEvent(
            conversation_id=conversation_id,
            turn_index=turn_index,
            mode=mode,
            fallback_provider=fallback
        )

    def get_failure(self, conversation_id: str, turn_index: int) -> Exception:
        """Return the appropriate exception for a planned failure.

        Raises
        ------
        ValueError
            If called for a (conversation, turn) that is not scheduled to fail.
        """
        if not self.should_fail(conversation_id, turn_index):
            raise ValueError(
                f"No failure scheduled for ({conversation_id}, turn {turn_index})"
            )

        mode = self.get_failure_mode(conversation_id, turn_index)

        if mode == FailureMode.TIMEOUT:
            return ProviderTimeoutError()
        elif mode == FailureMode.API_ERROR:
            return ProviderError()
        elif mode == FailureMode.RATE_LIMIT:
            return RateLimitError()
        else:
            return ProviderError(f"Unknown failure mode: {mode}")

    def get_failure_schedule(
        self,
        conversation_ids: list[str],
        max_turn_index: int = 10,
    ) -> list[FailureEvent]:
        """Preview the full failure schedule for a set of conversations.

        Useful for logging / debugging which turns will be injected.
        """
        if self.fixed_schedule is not None:
            return list(self.fixed_schedule)

        events: list[FailureEvent] = []
        for conv_id in conversation_ids:
            for turn_idx in range(max_turn_index + 1):
                if self.should_fail(conv_id, turn_idx):
                    mode = self.get_failure_mode(conv_id, turn_idx)
                    events.append(FailureEvent(conv_id, turn_idx, mode))
        return events


# ─── Convenience factory ────────────────────────────────────────────────────────

def create_injector(
    seed: int = 42,
    failure_rate: float = 0.3,
    failure_modes: list[FailureMode] | None = None,
    fixed_schedule: list[FailureEvent] | None = None,
) -> FaultInjector:
    """Create a fault injector with the given configuration."""
    modes = failure_modes or list(FailureMode)
    return FaultInjector(seed=seed, failure_rate=failure_rate, failure_modes=modes, fixed_schedule=fixed_schedule)

def generate_sweep_schedule(
    conversations: list[dict],
    sweep_mode: str,
    seed: int = 42,
    failure_modes: list[FailureMode] | None = None,
) -> list[FailureEvent]:
    """Generate a fixed failure schedule sweeping across early/mid/late turns.
    
    Parameters
    ----------
    conversations : list[dict]
        List of conversation objects (must contain 'id' and 'turns' or 'probe_turn_index').
    sweep_mode : str
        'early' : target the first turn (index 0).
        'mid'   : target a middle turn (index total_turns // 2).
        'late'  : target the final turn (probe turn, index total_turns - 1).
    seed : int
        Seed for deterministic failure mode selection.
    failure_modes : list[FailureMode] | None
        Modes to sample from.
        
    Returns
    -------
    list[FailureEvent]
        A schedule that can be passed to FaultInjector(fixed_schedule=...).
    """
    modes = failure_modes or list(FailureMode)
    rng = random.Random(seed)
    
    schedule = []
    for conv in conversations:
        conv_id = conv["id"]
        
        if "probe_turn_index" in conv:
            max_idx = conv["probe_turn_index"]
        else:
            max_idx = len(conv.get("turns", [])) - 1
            
        if max_idx < 0:
            continue
            
        if sweep_mode == "early":
            target_turn = 0
        elif sweep_mode == "mid":
            target_turn = max(0, max_idx // 2)
        elif sweep_mode == "late":
            target_turn = max_idx
        else:
            raise ValueError(f"Unknown sweep_mode: {sweep_mode}")
            
        # Deterministically pick a failure mode for this event
        digest = hashlib.sha256(f"{seed}:sweep:{conv_id}:{target_turn}".encode()).hexdigest()
        mode = modes[int(digest[:8], 16) % len(modes)]
        
        schedule.append(FailureEvent(conv_id, target_turn, mode))
    return schedule

def load_manifest(manifest_path: Path | str) -> list[FailureEvent]:
    """Load a fixed failure schedule from a manifest JSON file."""
    import json
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    schedule = []
    for entry in data:
        mode_str = entry.get("mode", FailureMode.API_ERROR.value)
        try:
            mode = FailureMode(mode_str)
        except ValueError:
            mode = FailureMode.API_ERROR
            
        schedule.append(FailureEvent(
            conversation_id=entry["conversation_id"],
            turn_index=entry["failure_turn"],
            mode=mode,
            fallback_provider=entry.get("fallback_provider")
        ))
    return schedule

