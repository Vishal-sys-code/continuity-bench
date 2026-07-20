# Continuity Bench 

> This is an organisation benchmark project for [Metriqual](https://metriqual.com/).
> Continuity Benchmark Paper: [continuity-bench-paper](https://arxiv.org/abs/2607.15899)
> Live Benchmark Run: [mql-continuitybenchmark](https://mql-continuitybench.netlify.app/)

A framework for evaluating the resilience and latency overhead of AI gateways and application-level failover strategies when LLM providers experience outages or degradation.

## The Motivation

When building production applications on top of LLM APIs, outages are an inevitable reality. The standard mitigation strategy is to deploy a routing gateway that automatically fails over to a secondary provider (e.g., shifting from OpenAI to Anthropic) when the primary provider experiences downtime. 

But there is a subtle failure mode: **does the fallback provider actually have the context of the conversation?**

If a multi-turn conversation fails on turn 5, a naive failover that only routes the final user prompt to the fallback provider will result in complete context loss. To maintain continuity, the gateway must forward the *entire conversation history*. However, this introduces a new challenge: **token inflation and latency overhead**.

**Continuity Bench** rigorously measures this exact trade-off.

## Metrics Evaluated

1. **Continuity Preservation Rate (CPR)**: The percentage of failover events where the fallback provider successfully maintains the conversational context and acknowledges the core facts established earlier in the session.
2. **Continuity Latency Overhead (CLO)**: The additional latency incurred by transmitting the full context history to the fallback provider during a failover event, measured against the baseline latency of the primary provider.

---

## Getting Started

### 1. Installation

```bash
git clone https://github.com/your-username/continuity-bench.git
cd continuity-bench
pip install -r requirements.txt
```

### 2. Environment Setup

Configure your API keys for the primary, fallback, and judge LLMs. Create a `.env` file in the root of the repository:

```env
OPENAI_API_KEY="sk-..."
ANTHROPIC_API_KEY="sk-..."
```

---

## Reproducing the Evaluation

The repository includes a fully automated evaluation suite. It spins up the baseline (stateless) and treatment (history-forwarding) proxies, generates simulated traffic, injects synthetic 500 errors, and scores the results using an LLM-as-a-judge.

Run the suite using the provided scripts:

**Linux / macOS:**
```bash
./run_eval.sh
```

**Windows:**
```powershell
.\run_eval.ps1
```

**What happens under the hood?**
The evaluation executes a robust Phase 2 analysis (N=5 independent runs at a concurrency level of 100). This computes statistically significant confidence intervals and captures run-to-run variance under heavy load. Finally, it performs a breakdown analysis of any negative results.

Generated reports are saved to:
- `results/phase2_summary.md`
- `results/breakdown.md`

---

## Known Limitations

- **Synthetic Test Data**: The evaluation relies on synthetic conversation graphs, which may not perfectly capture the long-tail complexity of real-world user interactions.
- **LLM-Judge Scoring**: Context preservation is evaluated by an LLM Judge (`gpt-4o`). This introduces non-determinism and the potential for model-specific biases.
- **Text Modality Only**: The framework currently strictly evaluates text-based conversational continuity and does not cover vision, audio, or broader multi-modal sessions.
- **Proxy Load Testing Caps**: The built-in Python `ThreadingHTTPServer` enforces OS-level caps on its TCP backlog and blocks an entire thread per connection. Under burst load (`concurrency=100`), the proxy may physically reject connections or hit provider Token Per Minute (TPM) limits when forwarding massive histories. This causes evaluation failures (logged as non-preserved context). For true production scaling, the proxy layer should be ported to an asynchronous framework like FastAPI or aiohttp.

## License

MIT License - see the [LICENSE](LICENSE) file for details.
