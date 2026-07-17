# Methodology Finding: The Failover "Retry Storm"

During the Phase 2 high-concurrency stress tests (`concurrency=100`), we uncovered a critical failure mode inherent to naive multi-provider failover systems, which we term a **Retry Storm** (or failover thundering herd).

## The Mechanism
When a primary LLM provider (e.g., OpenAI) experiences an outage or bottleneck, traffic is instantly routed to a secondary fallback provider (e.g., Anthropic or Gemini). If the fallback provider has a strict rate limit (e.g., a free tier with 5 or 15 Requests Per Minute) and the system is operating at high concurrency, the fallback provider will immediately return `429 Too Many Requests` (often surfaced by proxies as `502 Bad Gateway`).

In a naive architecture with a fixed-interval retry loop (e.g., retrying every 2 seconds on failure), the system enters a destructive cycle:
1. All 100 concurrent threads failover simultaneously.
2. The fallback provider accepts a few requests and immediately rate-limits the rest.
3. The remaining 90+ threads sleep for exactly 2 seconds.
4. They wake up simultaneously and hammer the fallback API again.
5. This cycle repeats continuously, generating thousands of requests per minute against the fallback provider.

## The Impact
This behavior permanently locks out the fallback provider. The rate limits are never allowed to reset because the provider is under a constant, synchronized DDoS-style bombardment from the evaluation harness. Eventually, the sustained connection attempts exhaust available sockets, leading to systemic `ConnectionRefusedError` crashes that take down the local proxy servers.

## The Solution
To build a resilient failover chain, fixed-interval retries are insufficient. Multi-provider systems must implement **Exponential Backoff with Jitter**. 
By introducing randomized exponential delays (e.g., `sleep(base * 2^retry + jitter)`), the concurrent threads desynchronize. This allows the strict rate-limit windows on the fallback provider to recover, preventing cascading failures and ensuring that the queue can drain cleanly, albeit slowly. 

Our empirical results confirm that implementing exponential backoff completely stabilizes queue wait times (~800ms) and eliminates proxy crashes, even under maximum sustained concurrency (N=100 slots).
