#!/usr/bin/env python3
"""
harness/runner.py — Drives the synthetic testsuite against a proxy
===================================================================

Simulates users interacting with the proxy endpoints by replaying
the multi-turn conversations from `testsuite/conversations.json`.

Usage:
    python -m harness.runner --proxy http://localhost:8001 --concurrency 5
"""

import argparse
import asyncio
import json
import os
import sys
import time
import random
from pathlib import Path

import httpx

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

async def play_conversation(
    client: httpx.AsyncClient,
    proxy_url: str,
    conv: dict,
) -> tuple[str, float]:
    """Replay a single conversation turn-by-turn.
    Returns:
        tuple of (conversation_id, harness_latency_ms)
    """
    conv_id = conv["id"]
    turns = conv["turns"]
    
    # We maintain our own local view of the conversation history.
    # We send this up to the proxy on every turn.
    messages = []
    
    # Fast-forward optimization: The proxy is stateless and relies on the messages array
    # we send it. Instead of sequentially hitting the API for every single filler turn
    # and paying the latency/rate-limit cost, we can construct the full history locally
    # and only send the final probe request.
    
    probe_idx = conv["probe_turn_index"]
    harness_latency_ms = 0.0
    
    for turn_idx, turn in enumerate(turns):
        messages.append({"role": turn["role"], "content": turn["content"]})
        
        # Only hit the proxy for the final probe turn
        if turn_idx == probe_idx:
            payload = {
                "messages": messages,
                "model": "gpt-4o-mini",
                "temperature": 0.0,
                "conversation_id": conv_id,
                "turn_index": turn_idx,
            }
            
            for attempt in range(6): # Retry enough to survive OS TCP backlog drops
                try:
                    t_start = time.perf_counter()
                    response = await client.post(
                        f"{proxy_url.rstrip('/')}/v1/chat/completions",
                        json=payload,
                        timeout=300.0
                    )
                    harness_latency_ms = (time.perf_counter() - t_start) * 1000
                    
                    # 429 and 50x are considered transient
                    if response.status_code in (429, 502, 503, 504) and attempt < 5:
                        backoff = min(30.0, (2 ** attempt) + random.uniform(0, 1))
                        print(f"Transient error {response.status_code} for {conv_id}. Retrying in {backoff:.1f}s...")
                        await asyncio.sleep(backoff)
                        continue
                        
                    response.raise_for_status()
                    data = response.json()
                    
                    if "error" in data:
                        assistant_text = f"[ERROR] {data['error'].get('message', 'Unknown')}"
                    else:
                        assistant_text = data["choices"][0]["message"]["content"]
                    break
                        
                except (httpx.TimeoutException, httpx.ReadTimeout) as e:
                    harness_latency_ms = (time.perf_counter() - t_start) * 1000
                    if attempt < 5:
                        backoff = min(30.0, (2 ** attempt) + random.uniform(0, 1))
                        print(f"Timeout for {conv_id}. Retrying in {backoff:.1f}s...")
                        await asyncio.sleep(backoff)
                        continue
                    assistant_text = f"[TIMEOUT] {e}"
                    break
                except httpx.HTTPError as e:
                    harness_latency_ms = (time.perf_counter() - t_start) * 1000
                    if attempt < 5:
                        status = getattr(e, 'response', None)
                        code = status.status_code if status else 'Connection Drop'
                        body = status.text if status else ''
                        backoff = min(30.0, (2 ** attempt) + random.uniform(0, 1))
                        print(f"HTTPError {code} for {conv_id}. Retrying in {backoff:.1f}s... Body: {body[:200]}")
                        await asyncio.sleep(backoff)
                        continue
                    assistant_text = f"[HTTP ERROR] {e}"
                    break
            
            messages.append({"role": "assistant", "content": assistant_text})
            break # We only care about the final response
            
    return conv_id, harness_latency_ms


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy", type=str, required=True, help="Proxy URL (e.g., http://localhost:8001)")
    parser.add_argument("--concurrency", type=int, default=5, help="Number of concurrent conversations")
    parser.add_argument("--conversations", type=str, default=str(_PROJECT_ROOT / "testsuite" / "conversations.json"))
    args = parser.parse_args()
    
    try:
        with open(args.conversations, "r", encoding="utf-8") as f:
            conversations = json.load(f)
    except FileNotFoundError:
        print(f"Error: {args.conversations} not found. Run the generator first.")
        sys.exit(1)
        
    print(f"Loaded {len(conversations)} conversations.")
    print(f"Targeting proxy: {args.proxy} (Concurrency: {args.concurrency})")
    
    sem = asyncio.Semaphore(args.concurrency)
    
    async def bounded_play(client, conv):
        async with sem:
            conv_id, lat = await play_conversation(client, args.proxy, conv)
            print(f"✓ Completed {conv_id} ({lat:.1f}ms)")

    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=600.0) as client:
        tasks = [asyncio.create_task(bounded_play(client, conv)) for conv in conversations]
        await asyncio.gather(*tasks)
        
    elapsed = time.perf_counter() - t0
    print(f"Finished {len(conversations)} conversations in {elapsed:.1f}s.")

if __name__ == "__main__":
    asyncio.run(main())
