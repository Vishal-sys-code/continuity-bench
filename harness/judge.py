#!/usr/bin/env python3
"""
harness/judge.py — LLM-as-a-judge for context preservation scoring
===================================================================

Reads the proxy logs (baseline or treatment) and the original
testsuite conversations to score whether the final model response
successfully answered the probe question by preserving the required fact.

Uses a separate LLM (`gpt-4o`) exclusively for judging. Outputs a binary 
score and a one-sentence justification to the specified output JSONL file.

Includes a calibration suite to sanity-check the judge's agreement rate 
against human-labeled ground truth before running on the full evaluation set.

Usage:
    # Run calibration sanity check (20 hand-labeled examples)
    python -m harness.judge --calibrate

    # Run full scoring
    python -m harness.judge --logs bench_logging/baseline_log.jsonl \
                            --conversations testsuite/conversations.json \
                            --output results/baseline_judgments.jsonl
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import openai
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Use an explicitly different model for the judge
JUDGE_MODEL = "gpt-4o"

class JudgeScore(BaseModel):
    preserved: bool
    reasoning: str

# ─── Calibration Set ────────────────────────────────────────────────────────────
# 20 hand-labeled examples covering various edge cases: exact matches, 
# paraphrasing, hallucinations, refusals, and proxy errors.

CALIBRATION_SET = [
    {"expected": "Elara Thornfield", "probe": "Who is the project lead?", "response": "The project lead is Elara Thornfield.", "label": True},
    {"expected": "Elara Thornfield", "probe": "Who is the project lead?", "response": "I believe you mentioned the lead is Elara.", "label": True},
    {"expected": "Elara Thornfield", "probe": "Who is the project lead?", "response": "The project lead is Sarah.", "label": False},
    {"expected": "Elara Thornfield", "probe": "Who is the project lead?", "response": "I'm sorry, you didn't mention who the project lead is.", "label": False},
    {"expected": "42-8901", "probe": "What is the passcode?", "response": "The passcode to the vault is 42-8901, as you noted earlier.", "label": True},
    {"expected": "42-8901", "probe": "What is the passcode?", "response": "It's 42-8901.", "label": True},
    {"expected": "42-8901", "probe": "What is the passcode?", "response": "The passcode is 428901.", "label": True}, # tolerant of formatting
    {"expected": "42-8901", "probe": "What is the passcode?", "response": "[HTTP ERROR] connection reset", "label": False},
    {"expected": "42-8901", "probe": "What is the passcode?", "response": "I don't have access to passcodes.", "label": False},
    {"expected": "June 14, 2029", "probe": "When is the launch?", "response": "The launch date is scheduled for June 14, 2029.", "label": True},
    {"expected": "June 14, 2029", "probe": "When is the launch?", "response": "We are launching on the 14th of June, 2029.", "label": True},
    {"expected": "June 14, 2029", "probe": "When is the launch?", "response": "The launch is in June 2029.", "label": False}, # missing specific day
    {"expected": "June 14, 2029", "probe": "When is the launch?", "response": "I cannot predict the future.", "label": False},
    {"expected": "blue aesthetics", "probe": "What design style do I prefer?", "response": "You prefer blue aesthetics for your interfaces.", "label": True},
    {"expected": "blue aesthetics", "probe": "What design style do I prefer?", "response": "You like a blue-themed aesthetic.", "label": True},
    {"expected": "blue aesthetics", "probe": "What design style do I prefer?", "response": "You prefer a minimalist, dark mode aesthetic.", "label": False},
    {"expected": "chronosync", "probe": "What is the name of our fictional drive?", "response": "It is called a chronosync drive.", "label": True},
    {"expected": "chronosync", "probe": "What is the name of our fictional drive?", "response": "The drive is known as chrono-sync.", "label": True},
    {"expected": "chronosync", "probe": "What is the name of our fictional drive?", "response": "It's a hyperdrive.", "label": False},
    {"expected": "chronosync", "probe": "What is the name of our fictional drive?", "response": "[ERROR] Provider rate limit exceeded.", "label": False},
]

# ─── Judge Logic ────────────────────────────────────────────────────────────────

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5))
async def score_response(
    client: openai.AsyncOpenAI,
    expected_fact: str,
    probe_question: str,
    actual_response: str
) -> tuple[bool | None, str]:
    """Use an LLM to judge if the response contains the expected fact."""
    
    # Fast heuristic for exact substring matches
    if expected_fact.lower() in actual_response.lower():
        return True, f"Exact substring match for the fact '{expected_fact}' found."
        
    if not actual_response or "[ERROR]" in actual_response or "[HTTP ERROR]" in actual_response:
        return False, "Proxy or provider error occurred during failover."

    system_prompt = (
        "You are an expert evaluation judge. Your task is to determine whether "
        "an AI assistant successfully answered a probe question by recalling a "
        "specific fact from earlier in the conversation.\n"
        "Return preserved=true if the assistant's answer correctly incorporates "
        "the Expected Fact (even if paraphrased slightly or formatted differently). "
        "Return preserved=false if the assistant apologizes, says it doesn't know, "
        "hallucinates a different fact, or misses critical details."
    )
    
    user_prompt = (
        f"Expected Fact: {expected_fact}\n"
        f"Probe Question: {probe_question}\n\n"
        f"Assistant's Actual Response:\n<response>\n{actual_response}\n</response>"
    )
    
    try:
        completion = await client.beta.chat.completions.parse(
            model=JUDGE_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format=JudgeScore,
            temperature=0.0,
        )
        score = completion.choices[0].message.parsed
        return score.preserved, score.reasoning
    except Exception as e:
        print(f"Error calling judge LLM: {e}")
        # Explicitly raise exception to trigger tenacity retry
        raise
        
async def safe_score_response(
    client: openai.AsyncOpenAI,
    expected_fact: str,
    probe_question: str,
    actual_response: str
) -> tuple[bool | None, str]:
    """Wraps score_response to catch the final exception after all retries fail."""
    try:
        return await score_response(client, expected_fact, probe_question, actual_response)
    except Exception as e:
        print(f"Judge completely failed after retries: {e}")
        return None, f"Judge error: {e}"

# ─── Calibration Runner ─────────────────────────────────────────────────────────

async def run_calibration():
    print(f"Running calibration sanity check against {len(CALIBRATION_SET)} hand-labeled examples...")
    print(f"Judge Model: {JUDGE_MODEL}\n")
    
    client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"), timeout=120.0, max_retries=5)
    correct = 0
    
    for idx, item in enumerate(CALIBRATION_SET):
        predicted, reasoning = await safe_score_response(
            client, 
            item["expected"], 
            item["probe"], 
            item["response"]
        )
        
        match = predicted == item["label"]
        if match:
            correct += 1
            status = "✅ MATCH"
        else:
            status = "❌ MISMATCH"
            
        print(f"Ex {idx+1:02d} | {status} | Label: {item['label']} | Pred: {predicted}")
        print(f"        Reasoning: {reasoning}")
        
    agreement = (correct / len(CALIBRATION_SET)) * 100
    print(f"\nCalibration Agreement Rate: {agreement:.1f}% ({correct}/{len(CALIBRATION_SET)})")
    
    if agreement < 90.0:
        print("⚠️  Warning: Agreement rate is below 90%. You may need to tune the judge prompt.")
    else:
        print("✓ Calibration passed. The judge is ready for the full evaluation set.")

# ─── Main Runner ────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibrate", action="store_true", help="Run the calibration sanity check and exit")
    parser.add_argument("--logs", type=str, help="Path to proxy JSONL log file")
    parser.add_argument("--conversations", type=str, default=str(_PROJECT_ROOT / "testsuite" / "conversations.json"))
    parser.add_argument("--output", type=str, help="Path to output scored JSONL")
    args = parser.parse_args()

    if args.calibrate:
        await run_calibration()
        sys.exit(0)

    if not args.logs or not args.output:
        print("Error: --logs and --output are required unless --calibrate is used.")
        parser.print_help()
        sys.exit(1)

    # 1. Load conversations to get expectations
    try:
        with open(args.conversations, "r", encoding="utf-8") as f:
            conversations = json.load(f)
    except FileNotFoundError:
        print(f"Error: {args.conversations} not found.")
        sys.exit(1)
        
    conv_map = {c["id"]: c for c in conversations}

    # 2. Extract final turn responses from proxy logs
    final_responses = {}
    try:
        with open(args.logs, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                conv_id = entry["conversation_id"]
                turn_idx = entry["turn_index"]
                
                # Check if this is the final probe turn for this conversation
                if conv_id in conv_map and turn_idx == conv_map[conv_id]["probe_turn_index"]:
                    final_responses[conv_id] = entry
    except FileNotFoundError:
        print(f"Error: {args.logs} not found. Run the runner first.")
        sys.exit(1)

    print(f"Found {len(final_responses)} final probe responses out of {len(conversations)} conversations.")

    # 3. Score using LLM
    client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"), timeout=120.0, max_retries=5)
    sem = asyncio.Semaphore(10) # max concurrency for judge
    
    scored_results = []
    
    async def process(conv_id, entry):
        conv = conv_map[conv_id]
        expected = conv["expected_fact"]
        
        # the probe question is the content of the final user turn
        probe_question = conv["turns"][conv["probe_turn_index"]]["content"]
        actual_response = entry["response_text"]
        
        async with sem:
            preserved, reasoning = await safe_score_response(client, expected, probe_question, actual_response)
            
        result = {
            "conversation_id": conv_id,
            "system": entry.get("system", "unknown"),
            "failed_over": entry.get("failed_over", False),
            "expected_fact": expected,
            "actual_response": actual_response,
            "preserved": preserved,
            "reasoning": reasoning
        }
        scored_results.append(result)
        print(f"[{entry.get('system')}] {conv_id} — Preserved: {preserved}")
        
    tasks = [asyncio.create_task(process(cid, entry)) for cid, entry in final_responses.items()]
    await asyncio.gather(*tasks)
    
    # 4. Save results
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for r in scored_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            
    print(f"✓ Scored {len(scored_results)} responses. Saved judgments to {args.output}")

if __name__ == "__main__":
    asyncio.run(main())
