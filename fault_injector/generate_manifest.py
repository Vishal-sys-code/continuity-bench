#!/usr/bin/env python3
"""
fault_injector/generate_manifest.py — Generate fixed experiment manifest
========================================================================

Reads the conversations from testsuite/conversations.json and the list
of fallback providers from config/providers.yaml, and generates a fixed
failure schedule assigning a specific failure turn and a specific
fallback provider to each conversation.

This ensures that paired proxy runs evaluate the exact same failure
condition and target provider.
"""

import argparse
import json
import random
from pathlib import Path
import yaml
import sys

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

def main():
    parser = argparse.ArgumentParser(description="Generate experiment manifest")
    parser.add_argument("--sweep-mode", type=str, choices=["early", "mid", "late"], default="late",
                        help="Turn to target for failure")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output", type=str, default=str(_PROJECT_ROOT / "config" / "experiment_manifest.json"))
    args = parser.parse_args()

    # Load conversations
    conv_path = _PROJECT_ROOT / "testsuite" / "conversations.json"
    if not conv_path.exists():
        print(f"Error: {conv_path} not found. Run 'python -m testsuite.generate' first.", file=sys.stderr)
        sys.exit(1)
        
    with open(conv_path, "r", encoding="utf-8") as f:
        conversations = json.load(f)

    # Load providers config
    config_path = _PROJECT_ROOT / "config" / "providers.yaml"
    fallbacks = ["anthropic", "openai"]  # defaults
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            conf = yaml.safe_load(f) or {}
            fallbacks = conf.get("fallbacks", fallbacks)

    if not fallbacks:
        print("Error: No fallbacks configured in providers.yaml", file=sys.stderr)
        sys.exit(1)

    rng = random.Random(args.seed)
    
    # We can reuse the existing sweep schedule logic to pick the turn and mode,
    # then just augment it with a randomly picked fallback provider.
    from fault_injector.injector import generate_sweep_schedule
    schedule = generate_sweep_schedule(conversations, sweep_mode=args.sweep_mode, seed=args.seed)
    
    manifest_data = []
    for event in schedule:
        fallback = rng.choice(fallbacks)
        manifest_data.append({
            "conversation_id": event.conversation_id,
            "failure_turn": event.turn_index,
            "mode": event.mode.value,
            "fallback_provider": fallback
        })
        
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)
        
    print(f"Generated manifest with {len(manifest_data)} events to {out_path}")

if __name__ == "__main__":
    main()
