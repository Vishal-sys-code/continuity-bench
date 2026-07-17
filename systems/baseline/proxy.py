#!/usr/bin/env python3
"""
systems/baseline/proxy.py — Naive stateless failover proxy
============================================================

An OpenAI-compatible HTTP proxy that routes chat completion requests
to a primary provider (OpenAI or Anthropic).  On a simulated provider
failure (triggered by the fault_injector), it retries against the
fallback provider using **ONLY the current user message** — no prior
conversation history is forwarded.

This represents the "worst-case" failover strategy: the fallback
provider has zero context about earlier turns, and must answer the
probe question cold.

Endpoints:
    POST /v1/chat/completions   — OpenAI-compatible chat completions
    GET  /health                — health check

Environment variables:
    OPENAI_API_KEY      — required
    ANTHROPIC_API_KEY   — required
    PRIMARY_PROVIDER    — "openai" (default) or "anthropic"
    BASELINE_PORT       — port to listen on (default: 8001)

Usage:
    python -m systems.baseline.proxy
"""

from __future__ import annotations

import json
import os
import sys
import time
import yaml
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Optional

# Add project root to path for imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from systems.providers import (
    Provider,
    ProviderResponse,
    create_provider,
    get_provider_names,
)
from fault_injector.injector import FaultInjector, create_injector
from bench_logging.logger import BenchLogger, generate_request_id


# ─── Proxy configuration ───────────────────────────────────────────────────────

DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "providers.yaml"
DEFAULT_PRIMARY = os.environ.get("PRIMARY_PROVIDER", "openai")
DEFAULT_PORT = int(os.environ.get("BASELINE_PORT", "8001"))
LOG_DIR = _PROJECT_ROOT / "bench_logging"


class BaselineProxy:
    """Stateless failover proxy — retries with current message only.

    On failure of the primary provider, this proxy constructs a new
    messages[] array containing only the latest user message and sends
    it to the fallback provider.  All prior context is lost.

    Parameters
    ----------
    primary : str | None
        Name of the primary provider ("openai" or "anthropic"). If None, loaded from config.
    config_path : Path | str | None
        Path to providers.yaml configuration.
    fault_injector : FaultInjector | None
        Optional fault injector for simulated failures.
    logger : BenchLogger | None
        Optional structured logger.
    """

    def __init__(
        self,
        primary: str | None = None,
        config_path: Path | str | None = None,
        fault_injector: FaultInjector | None = None,
        logger: BenchLogger | None = None,
    ) -> None:
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        
        # Load from config or use defaults
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                conf = yaml.safe_load(f) or {}
                self.primary_name = primary or conf.get("primary", DEFAULT_PRIMARY)
                self.fallback_names = conf.get("fallbacks", ["openai"])
        else:
            self.primary_name = primary or DEFAULT_PRIMARY
            self.fallback_names = ["openai"]

        self.primary: Provider = create_provider(self.primary_name)
        # Only instantiate the providers we actually need (primary + fallbacks)
        needed = set([self.primary_name] + self.fallback_names)
        self.providers_dict: dict[str, Provider] = {}
        for name in needed:
            try:
                self.providers_dict[name] = create_provider(name)
            except Exception as e:
                print(f"Warning: Could not create provider '{name}': {e}")
        
        self.injector = fault_injector or create_injector()
        self.logger = logger or BenchLogger(
            log_dir=LOG_DIR, system_name="baseline"
        )

    @staticmethod
    def _get_fallback(primary: str) -> str:
        """Return the other provider as fallback if no config."""
        providers = get_provider_names()
        for p in providers:
            if p != primary:
                return p
        raise ValueError(f"No fallback available for primary '{primary}'")

    def handle_chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        conversation_id: str = "unknown",
        turn_index: int = 0,
    ) -> dict[str, Any]:
        """Process a single chat completion request with failover.

        The failover strategy is STATELESS: on primary failure, only the
        current (latest) user message is sent to the fallback provider.

        Returns
        -------
        dict
            OpenAI-compatible response object.
        """
        request_id = generate_request_id()
        failed_over = False
        failure_mode: Optional[str] = None
        provider_used = self.primary_name
        response_text = ""
        latency_ms = 0.0
        error_msg: Optional[str] = None
        success = False

        t_start = time.perf_counter()

        # ── Step 1: Check if fault injector triggers a failure ──
        failure_event = self.injector.get_failure_event(conversation_id, turn_index)
        if failure_event:
            failure = self.injector.get_failure(conversation_id, turn_index)
            failure_mode = failure_event.mode.value
            assigned_fallback = failure_event.fallback_provider

            # ── Step 2: BASELINE FAILOVER — current message only ──
            failed_over = True

            # Extract only the last user message
            last_user_msg = self._extract_last_user_message(messages)
            failover_messages = [{"role": "user", "content": last_user_msg}]

            # Use the assigned fallback if specified in the manifest, else cycle through fallbacks
            fallback_sequence = [assigned_fallback] if assigned_fallback else self.fallback_names
            success = False
            for provider_used in fallback_sequence:
                if provider_used not in self.providers_dict:
                    continue
                    
                fallback_provider = self.providers_dict[provider_used]
                try:
                    result = fallback_provider.chat(
                        messages=failover_messages,
                        model=None,  # use fallback's default model
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    response_text = result.text
                    latency_ms = result.latency_ms
                    model_used = result.model
                    success = True
                    error_msg = None
                    break
                except Exception as e:
                    latency_ms = (time.perf_counter() - t_start) * 1000
                    error_msg = f"Fallback ({provider_used}) also failed: {e}"
                    response_text = ""
                    model_used = ""
            
            if not success:
                # All fallbacks failed
                pass
        else:
            # ── No fault — call primary normally ──
            try:
                result = self.primary.chat(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                response_text = result.text
                latency_ms = result.latency_ms
                model_used = result.model
            except Exception as e:
                # Actual primary failure (not simulated)
                failed_over = True
                failure_mode = "real_exception"

                # Extract only the last user message
                last_user_msg = self._extract_last_user_message(messages)
                failover_messages = [{"role": "user", "content": last_user_msg}]
                
                success = False
                for provider_used in self.fallback_names:
                    if provider_used not in self.providers_dict:
                        continue
                    fallback_provider = self.providers_dict[provider_used]
                    try:
                        result = fallback_provider.chat(
                            messages=failover_messages,
                            model=None,
                            temperature=temperature,
                            max_tokens=max_tokens,
                        )
                        response_text = result.text
                        latency_ms = result.latency_ms
                        model_used = result.model
                        success = True
                        error_msg = None
                        break
                    except Exception as fallback_e:
                        latency_ms = (time.perf_counter() - t_start) * 1000
                        error_msg = f"Fallback ({provider_used}) also failed: {fallback_e}"
                        response_text = ""
                        model_used = ""
                
                if not success and not self.fallback_names:
                    latency_ms = (time.perf_counter() - t_start) * 1000
                    error_msg = f"Primary failed (real): {e} and no fallbacks available."
                    response_text = ""
                    model_used = model or ""

        # ── Step 3: Log the event ──
        self.logger.log_request(
            request_id=request_id,
            conversation_id=conversation_id,
            turn_index=turn_index,
            provider=provider_used,
            model=model_used if not error_msg else "",
            failed_over=failed_over,
            failover_from=self.primary_name if failed_over else None,
            failure_mode=failure_mode,
            latency_ms=latency_ms,
            response_text=response_text,
            error=error_msg,
        )

        # ── Step 4: Return OpenAI-compatible response ──
        return self._format_response(
            request_id=request_id,
            response_text=response_text,
            model=model_used if not error_msg else (model or ""),
            error=error_msg,
        )

    @staticmethod
    def _extract_last_user_message(messages: list[dict[str, str]]) -> str:
        """Extract the content of the last user message."""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return msg.get("content", "")
        return ""

    @staticmethod
    def _format_response(
        *,
        request_id: str,
        response_text: str,
        model: str,
        error: Optional[str] = None,
    ) -> dict[str, Any]:
        """Format an OpenAI-compatible chat completion response."""
        if error:
            return {
                "id": request_id,
                "object": "chat.completion",
                "error": {"message": error, "type": "proxy_error"},
            }

        return {
            "id": request_id,
            "object": "chat.completion",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_text,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {},  # Omitted — we don't aggregate provider usage
        }


# ─── HTTP server ────────────────────────────────────────────────────────────────

import threading

_proxy_instance: BaselineProxy | None = None
from collections import defaultdict
_conversation_locks = defaultdict(threading.Lock)
_conv_lock_mutex = threading.Lock()

def get_conversation_lock(conversation_id: str) -> threading.Lock:
    with _conv_lock_mutex:
        return _conversation_locks[conversation_id]

class BaselineHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the baseline proxy."""

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "system": "baseline"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/v1/chat/completions":
            self._handle_chat_completions()
        else:
            self._send_json(404, {"error": "not found"})

    def _handle_chat_completions(self) -> None:
        global _proxy_instance
        if _proxy_instance is None:
            _proxy_instance = BaselineProxy()

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            request = json.loads(body)

            messages = request.get("messages", [])
            model = request.get("model")
            temperature = request.get("temperature", 0.0)
            max_tokens = request.get("max_tokens", 1024)
            conversation_id = request.get("conversation_id", "unknown")
            turn_index = request.get("turn_index", 0)

            conv_lock = get_conversation_lock(conversation_id)
            with conv_lock:
                result = _proxy_instance.handle_chat_completion(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    conversation_id=conversation_id,
                    turn_index=turn_index,
                )

            status = 200 if "error" not in result else 502
            self._send_json(status, result)

        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON"})
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._send_json(500, {"error": str(e)})

    def _send_json(self, status: int, body: dict) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode("utf-8"))
        except ConnectionError:
            pass

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default stderr logging — we use our own logger."""
        pass


class ThreadedProxyServer(ThreadingHTTPServer):
    request_queue_size = 200

def serve(
    port: int = DEFAULT_PORT,
    primary: str | None = None,
    config_path: str | None = None,
    fault_injector: FaultInjector | None = None,
) -> None:
    """Start the baseline proxy HTTP server."""
    global _proxy_instance
    _proxy_instance = BaselineProxy(
        primary=primary, config_path=config_path, fault_injector=fault_injector
    )

    server = ThreadedProxyServer(("0.0.0.0", port), BaselineHandler)
    print(f"✓ Baseline proxy listening on http://0.0.0.0:{port}")
    print(f"  Primary: {_proxy_instance.primary_name}")
    print(f"  Fallbacks: {', '.join(_proxy_instance.fallback_names)}")
    print(f"  Strategy: STATELESS (current message only)")
    print(f"  Logs: {_proxy_instance.logger.log_path}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹  Baseline proxy stopped.")
        server.server_close()


# ─── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Baseline (stateless) failover proxy"
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help="Port to listen on"
    )
    parser.add_argument(
        "--primary",
        type=str,
        default=None,
        choices=get_provider_names(),
        help="Primary provider (overrides config if set)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--failure-rate",
        type=float,
        default=0.3,
        help="Fault injection failure rate (0.0–1.0)",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Fault injection seed"
    )
    parser.add_argument(
        "--sweep-mode",
        type=str,
        choices=["early", "mid", "late"],
        default=None,
        help="Deterministic sweep mode. Overrides failure-rate.",
    )
    parser.add_argument(
        "--manifest",
        type=str,
        default=None,
        help="Path to experiment manifest JSON for fixed failures",
    )
    args = parser.parse_args()

    if args.port == 8002:
        print("FATAL ERROR: You are trying to start the BASELINE proxy on port 8002. You must use systems.treatment.proxy for port 8002!")
        sys.exit(1)

    if args.manifest:
        from fault_injector import load_manifest, FaultInjector
        schedule = load_manifest(args.manifest)
        injector = FaultInjector(seed=args.seed, fixed_schedule=schedule)
    elif args.sweep_mode:
        import json
        from fault_injector import generate_sweep_schedule, FaultInjector
        conv_path = _PROJECT_ROOT / "testsuite" / "conversations.json"
        with open(conv_path, "r", encoding="utf-8") as f:
            conversations = json.load(f)
        schedule = generate_sweep_schedule(conversations, sweep_mode=args.sweep_mode, seed=args.seed)
        injector = FaultInjector(seed=args.seed, fixed_schedule=schedule)
    else:
        injector = create_injector(seed=args.seed, failure_rate=args.failure_rate)

    serve(port=args.port, primary=args.primary, config_path=args.config, fault_injector=injector)

