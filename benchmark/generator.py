"""Synthetic chaos incident log generator.

Generates realistic production outage log scenarios across microservices
with ground-truth root causes, affected services, and timelines.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any


def _format_line(
    ts: datetime,
    level: str,
    service: str,
    message: str,
    req_id: str | None = None,
    trace_id: str | None = None,
) -> str:
    """Format a log line using standard ISO timestamp format."""
    meta = []
    if req_id:
        meta.append(f"req-{req_id}")
    if trace_id:
        meta.append(f"trace-{trace_id}")
    meta_str = (" " + " ".join(meta)) if meta else ""
    return f"{ts.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} [{level}] [{service}] {message}{meta_str}"


def generate_db_pool_exhaustion(num_lines: int = 600) -> tuple[list[str], dict[str, Any]]:
    """Scenario 1: DB connection pool exhaustion causing cascading 504s across microservices."""
    rnd = random.Random(42)
    start_ts = datetime(2024, 1, 15, 10, 0, 0)
    lines: list[str] = []

    # Timeline phases
    # Phase 1: 0 - 25% normal traffic
    # Phase 2: 25% - 40% pool saturation starts on db-proxy
    # Phase 3: 40% - 75% peak outage: pool exhausted, checkout fails, 504 on api-gateway
    # Phase 4: 75% - 100% recovery: pool expanded, backlog clears
    p1 = int(num_lines * 0.25)
    p2 = int(num_lines * 0.40)
    p3 = int(num_lines * 0.75)

    services = ["api-gateway", "checkout-service", "inventory-service", "db-proxy", "payment-service"]
    current_ts = start_ts

    for i in range(num_lines):
        current_ts += timedelta(milliseconds=rnd.randint(300, 1500))
        req_id = f"{rnd.randint(0x100000, 0xFFFFFF):x}"
        trace_id = f"{rnd.randint(0x10000000, 0xFFFFFFFF):x}"

        if i < p1:
            # Normal baseline
            svc = rnd.choice(services)
            if svc == "api-gateway":
                msg = rnd.choice(
                    [
                        f"Request received: GET /api/products req-{req_id}",
                        f"Request received: POST /api/checkout req-{req_id}",
                        f"Response sent: 200 OK in {rnd.randint(15, 45)}ms",
                    ]
                )
                lines.append(_format_line(current_ts, "INFO", svc, msg, req_id, trace_id))
            elif svc == "checkout-service":
                msg = rnd.choice(
                    [
                        f"Processing checkout for cart CART-{rnd.randint(100, 999)}",
                        f"Order validated successfully total=${rnd.randint(20, 200)}",
                        "Applying coupon code WELCOME10",
                    ]
                )
                lines.append(_format_line(current_ts, "INFO", svc, msg, req_id, trace_id))
            elif svc == "db-proxy":
                active = rnd.randint(10, 40)
                msg = rnd.choice(
                    [
                        f"Connection acquired from pool (active: {active}/100)",
                        f"Query executed in {rnd.randint(5, 30)}ms: SELECT * FROM orders WHERE id = $1",
                        f"Connection released to pool (idle: {100 - active}/100)",
                    ]
                )
                lines.append(_format_line(current_ts, "DEBUG", svc, msg, req_id, trace_id))
            else:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        svc,
                        f"Service health check OK latency={rnd.randint(2, 10)}ms",
                        req_id,
                        trace_id,
                    )
                )

        elif i < p2:
            # Saturation building
            svc = rnd.choice(["db-proxy", "checkout-service", "api-gateway"])
            if svc == "db-proxy":
                active = min(100, 70 + (i - p1) * 2)
                msg = f"Connection pool warning: active={active}/100 wait_queue={rnd.randint(5, 35)} timeout=5000ms"
                lines.append(_format_line(current_ts, "WARN", svc, msg, req_id, trace_id))
            elif svc == "checkout-service":
                msg = f"Database query latency elevated: took {rnd.randint(2500, 4800)}ms to acquire connection"
                lines.append(_format_line(current_ts, "WARN", svc, msg, req_id, trace_id))
            else:
                msg = f"Response sent: 200 OK in {rnd.randint(2000, 4500)}ms for POST /api/checkout"
                lines.append(_format_line(current_ts, "INFO", svc, msg, req_id, trace_id))

        elif i < p3:
            # Full outage: pool exhausted -> cascading failures
            svc = rnd.choice(["db-proxy", "checkout-service", "api-gateway", "inventory-service"])
            if svc == "db-proxy":
                msg = (
                    "Connection pool exhausted: 100/100 connections active, 58 pending in queue timed out after 5000ms"
                )
                lines.append(_format_line(current_ts, "ERROR", svc, msg, req_id, trace_id))
            elif svc == "checkout-service":
                msg = f"HikariPool-1 - Connection is not available, request timed out after 5002ms: failed to persist order ORD-{rnd.randint(1000, 9999)}"
                lines.append(_format_line(current_ts, "ERROR", svc, msg, req_id, trace_id))
            elif svc == "api-gateway":
                status = rnd.choice(["504 Gateway Timeout", "502 Bad Gateway"])
                msg = f"Upstream service checkout-service failed: HTTP {status} returned to client"
                lines.append(_format_line(current_ts, "ERROR", svc, msg, req_id, trace_id))
            else:
                msg = "Circuit breaker tripped for checkout-service: downstream unavailable"
                lines.append(_format_line(current_ts, "WARN", svc, msg, req_id, trace_id))

        else:
            # Recovery
            svc = rnd.choice(services)
            if svc == "db-proxy" and i == p3:
                lines.append(
                    _format_line(
                        current_ts, "INFO", svc, "Database pool size dynamically resized to max=250 connections"
                    )
                )
            elif svc == "db-proxy":
                lines.append(
                    _format_line(
                        current_ts, "INFO", svc, f"Active pool connections draining: {rnd.randint(20, 60)}/250 active"
                    )
                )
            elif svc == "checkout-service":
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        svc,
                        f"Order processed successfully ORD-{rnd.randint(1000, 9999)} in {rnd.randint(40, 90)}ms",
                        req_id,
                        trace_id,
                    )
                )
            else:
                lines.append(
                    _format_line(
                        current_ts, "INFO", svc, f"Response sent: 200 OK in {rnd.randint(15, 50)}ms", req_id, trace_id
                    )
                )

    ground_truth = {
        "scenario_name": "db_pool_exhaustion",
        "root_cause": "Database connection pool exhaustion on db-proxy causing cascading timeouts",
        "root_cause_keywords": ["pool", "exhaust", "db-proxy", "connection", "hikaripool", "timeout"],
        "expected_failing_services": ["db-proxy", "checkout-service", "api-gateway"],
        "incident_window": (
            (start_ts + timedelta(seconds=p1 * 0.8)).strftime("%Y-%m-%d %H:%M:%S"),
            (start_ts + timedelta(seconds=p3 * 0.8)).strftime("%Y-%m-%d %H:%M:%S"),
        ),
        "incident_start": (start_ts + timedelta(seconds=p1 * 0.8)).strftime("%Y-%m-%d %H:%M:%S"),
        "incident_end": (start_ts + timedelta(seconds=p3 * 0.8)).strftime("%Y-%m-%d %H:%M:%S"),
        "hint": "Checkout failing with 504 Gateway Timeout",
    }
    return lines, ground_truth


def generate_oom_kill(num_lines: int = 500) -> tuple[list[str], dict[str, Any]]:
    """Scenario 2: Memory leak in worker-service leading to kernel OOM killer and pod crash."""
    rnd = random.Random(101)
    start_ts = datetime(2024, 1, 15, 11, 0, 0)
    lines: list[str] = []

    p1 = int(num_lines * 0.25)
    p2 = int(num_lines * 0.55)
    p3 = int(num_lines * 0.80)

    current_ts = start_ts

    for i in range(num_lines):
        current_ts += timedelta(milliseconds=rnd.randint(400, 1800))
        req_id = f"{rnd.randint(0x100000, 0xFFFFFF):x}"
        trace_id = f"{rnd.randint(0x10000000, 0xFFFFFFFF):x}"

        if i < p1:
            # Baseline normal
            if rnd.random() < 0.6:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "worker-service",
                        f"Processing async batch job batch-{rnd.randint(100, 999)}: memory_rss=512MB (48% heap)",
                        req_id,
                        trace_id,
                    )
                )
            elif rnd.random() < 0.8:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "queue-service",
                        f"Dispatched message msg-{req_id} to worker-service queue_depth={rnd.randint(10, 50)}",
                    )
                )
            else:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "api-gateway",
                        f"GET /api/jobs/status 200 OK in {rnd.randint(10, 30)}ms",
                        req_id,
                    )
                )

        elif i < p2:
            # Memory leak escalating
            pct = 60 + int((i - p1) / (p2 - p1) * 35)
            mb = int(1024 * (pct / 25))
            if rnd.random() < 0.65:
                lvl = "WARN" if pct < 85 else "ERROR"
                lines.append(
                    _format_line(
                        current_ts,
                        lvl,
                        "worker-service",
                        f"Memory leak warning: heap consumption at {pct}% ({mb}MB / 4096MB) uncollected dataframe objects",
                        req_id,
                        trace_id,
                    )
                )
            else:
                lines.append(
                    _format_line(
                        current_ts,
                        "WARN",
                        "queue-service",
                        f"Worker heartbeat delayed: ping took {rnd.randint(800, 3200)}ms queue_depth={rnd.randint(100, 350)}",
                    )
                )

        elif i < p3:
            # OOM Kill event & failure
            if i == p2 + 2:
                lines.append(
                    _format_line(
                        current_ts,
                        "FATAL",
                        "kernel",
                        "Out of memory: Killed process 14201 (python) total-vm:4231844kB, anon-rss:3984128kB, file-rss:0kB",
                    )
                )
            elif i == p2 + 5:
                lines.append(
                    _format_line(
                        current_ts,
                        "ERROR",
                        "worker-service",
                        "Container worker-service-7f9b8c terminated with exit code 137 (OOMKilled)",
                    )
                )
            elif rnd.random() < 0.5:
                lines.append(
                    _format_line(
                        current_ts,
                        "ERROR",
                        "queue-service",
                        f"Worker unresponsive, task execution timed out for task-{rnd.randint(1000, 9999)}",
                    )
                )
            else:
                lines.append(
                    _format_line(
                        current_ts,
                        "ERROR",
                        "api-gateway",
                        "POST /api/jobs returned 503 Service Unavailable: no healthy worker instances",
                    )
                )

        else:
            # Pod restarts and recovers
            if i == p3:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "worker-service",
                        "Kubernetes kubelet: Created container worker-service-newpod; initial memory rss=210MB",
                    )
                )
            elif rnd.random() < 0.6:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "worker-service",
                        f"Resumed job processing: batch-{rnd.randint(100, 999)} memory_rss=280MB",
                    )
                )
            else:
                lines.append(
                    _format_line(
                        current_ts, "INFO", "queue-service", f"Queue backlog draining: depth={rnd.randint(5, 40)}"
                    )
                )

    ground_truth = {
        "scenario_name": "oom_kill",
        "root_cause": "Memory leak in worker-service resulting in kernel OOM-killer (exit code 137)",
        "root_cause_keywords": ["oom", "memory", "leak", "killed process", "worker-service", "137", "oomkilled"],
        "expected_failing_services": ["worker-service", "queue-service", "api-gateway"],
        "incident_window": (
            (start_ts + timedelta(seconds=p1 * 0.9)).strftime("%Y-%m-%d %H:%M:%S"),
            (start_ts + timedelta(seconds=p3 * 0.9)).strftime("%Y-%m-%d %H:%M:%S"),
        ),
        "incident_start": (start_ts + timedelta(seconds=p1 * 0.9)).strftime("%Y-%m-%d %H:%M:%S"),
        "incident_end": (start_ts + timedelta(seconds=p3 * 0.9)).strftime("%Y-%m-%d %H:%M:%S"),
        "hint": "Worker service crashed and jobs failing with 503",
    }
    return lines, ground_truth


def generate_bad_deployment(num_lines: int = 500) -> tuple[list[str], dict[str, Any]]:
    """Scenario 3: Faulty release deployment introducing NullPointerException."""
    rnd = random.Random(202)
    start_ts = datetime(2024, 1, 15, 14, 0, 0)
    lines: list[str] = []

    p1 = int(num_lines * 0.25)
    p2 = int(num_lines * 0.75)

    current_ts = start_ts

    for i in range(num_lines):
        current_ts += timedelta(milliseconds=rnd.randint(350, 1600))
        req_id = f"{rnd.randint(0x100000, 0xFFFFFF):x}"
        trace_id = f"{rnd.randint(0x10000000, 0xFFFFFFFF):x}"

        if i < p1:
            # Baseline running v2.4.0
            if rnd.random() < 0.5:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "checkout-service",
                        f"Checkout completed successfully order=ORD-{rnd.randint(1000, 9999)} [release=v2.4.0]",
                        req_id,
                        trace_id,
                    )
                )
            else:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "api-gateway",
                        f"POST /api/checkout 200 OK duration={rnd.randint(35, 75)}ms",
                        req_id,
                        trace_id,
                    )
                )

        elif i == p1:
            # The deployment event
            lines.append(
                _format_line(
                    current_ts,
                    "WARN",
                    "deployment-service",
                    "Deploying release v2.4.1 to checkout-service (traffic shift 100%)",
                )
            )

        elif i == p1 + 1:
            lines.append(
                _format_line(
                    current_ts, "INFO", "checkout-service", "Release v2.4.1 initialized, listening on port 8080"
                )
            )

        elif i < p2:
            # Immediate NPE on every request
            if rnd.random() < 0.65:
                lines.append(
                    _format_line(
                        current_ts,
                        "ERROR",
                        "checkout-service",
                        f"Unhandled Exception: java.lang.NullPointerException at CheckoutHandler.java:142 in handleOrder() order=ORD-{rnd.randint(1000, 9999)}",
                        req_id,
                        trace_id,
                    )
                )
            else:
                lines.append(
                    _format_line(
                        current_ts,
                        "ERROR",
                        "api-gateway",
                        "POST /api/checkout 500 Internal Server Error: checkout-service invocation failed",
                        req_id,
                        trace_id,
                    )
                )

        else:
            # Rollback to v2.4.0
            if i == p2:
                lines.append(
                    _format_line(
                        current_ts,
                        "WARN",
                        "deployment-service",
                        "Rolling back checkout-service: reverting release from v2.4.1 to v2.4.0",
                    )
                )
            elif i == p2 + 1:
                lines.append(
                    _format_line(
                        current_ts, "INFO", "checkout-service", "Release v2.4.0 active; verified config healthy"
                    )
                )
            elif rnd.random() < 0.6:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "checkout-service",
                        f"Checkout completed successfully order=ORD-{rnd.randint(1000, 9999)} [release=v2.4.0]",
                        req_id,
                        trace_id,
                    )
                )
            else:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "api-gateway",
                        f"POST /api/checkout 200 OK duration={rnd.randint(30, 65)}ms",
                        req_id,
                        trace_id,
                    )
                )

    ground_truth = {
        "scenario_name": "bad_deployment",
        "root_cause": "Faulty release v2.4.1 deployed to checkout-service causing NullPointerException at CheckoutHandler.java:142",
        "root_cause_keywords": [
            "v2.4.1",
            "deploy",
            "nullpointerexception",
            "checkouthandler",
            "checkout-service",
            "release",
        ],
        "expected_failing_services": ["checkout-service", "api-gateway"],
        "incident_window": (
            (start_ts + timedelta(seconds=p1 * 0.9)).strftime("%Y-%m-%d %H:%M:%S"),
            (start_ts + timedelta(seconds=p2 * 0.9)).strftime("%Y-%m-%d %H:%M:%S"),
        ),
        "incident_start": (start_ts + timedelta(seconds=p1 * 0.9)).strftime("%Y-%m-%d %H:%M:%S"),
        "incident_end": (start_ts + timedelta(seconds=p2 * 0.9)).strftime("%Y-%m-%d %H:%M:%S"),
        "hint": "Checkout failing with 500 immediately after release deployment",
    }
    return lines, ground_truth


def generate_upstream_outage(num_lines: int = 500) -> tuple[list[str], dict[str, Any]]:
    """Scenario 4: External payment provider 503 triggering retry storm and client thread pool exhaustion."""
    rnd = random.Random(303)
    start_ts = datetime(2024, 1, 15, 16, 0, 0)
    lines: list[str] = []

    p1 = int(num_lines * 0.25)
    p2 = int(num_lines * 0.75)

    current_ts = start_ts

    for i in range(num_lines):
        current_ts += timedelta(milliseconds=rnd.randint(300, 1500))
        req_id = f"{rnd.randint(0x100000, 0xFFFFFF):x}"
        trace_id = f"{rnd.randint(0x10000000, 0xFFFFFFFF):x}"

        if i < p1:
            # Baseline normal payment flow
            if rnd.random() < 0.6:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "payment-service",
                        f"Charge authorized by pay-gateway.ext: txn=txn_{rnd.randint(10000, 99999)} in {rnd.randint(90, 180)}ms",
                        req_id,
                        trace_id,
                    )
                )
            elif rnd.random() < 0.8:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "checkout-service",
                        f"Payment confirmed for order ORD-{rnd.randint(1000, 9999)}",
                        req_id,
                        trace_id,
                    )
                )
            else:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "api-gateway",
                        f"POST /api/pay 200 OK duration={rnd.randint(120, 240)}ms",
                        req_id,
                        trace_id,
                    )
                )

        elif i < p2:
            # Upstream 503 outage & retry storm
            if rnd.random() < 0.4:
                lines.append(
                    _format_line(
                        current_ts,
                        "ERROR",
                        "payment-service",
                        "Upstream gateway pay-gateway.ext returned HTTP 503 Service Unavailable: endpoint overloaded",
                        req_id,
                        trace_id,
                    )
                )
            elif rnd.random() < 0.7:
                attempt = rnd.randint(1, 5)
                lines.append(
                    _format_line(
                        current_ts,
                        "WARN",
                        "payment-service",
                        f"Retry storm: Retrying failed charge attempt {attempt}/5 for req-{req_id} backoff={attempt * 200}ms",
                        req_id,
                        trace_id,
                    )
                )
            elif rnd.random() < 0.85:
                lines.append(
                    _format_line(
                        current_ts,
                        "ERROR",
                        "payment-service",
                        "HttpClient ThreadPoolExecutor saturated: 200/200 active threads, tasks rejected queue_size=500",
                        req_id,
                        trace_id,
                    )
                )
            else:
                lines.append(
                    _format_line(
                        current_ts,
                        "ERROR",
                        "api-gateway",
                        "POST /api/pay 504 Gateway Timeout: payment-service client thread exhaustion",
                        req_id,
                        trace_id,
                    )
                )

        else:
            # Recovery after circuit breaker & upstream recovery
            if i == p2:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "payment-service",
                        "Circuit breaker OPEN for pay-gateway.ext; fast failing traffic to fallback",
                    )
                )
            elif i == p2 + 1:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "payment-service",
                        "pay-gateway.ext health probe succeeded; circuit breaker transitioned to HALF-OPEN",
                    )
                )
            elif rnd.random() < 0.6:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "payment-service",
                        f"Payment successful via pay-gateway.ext txn=txn_{rnd.randint(10000, 99999)} latency={rnd.randint(100, 210)}ms",
                        req_id,
                        trace_id,
                    )
                )
            else:
                lines.append(
                    _format_line(
                        current_ts,
                        "INFO",
                        "api-gateway",
                        f"POST /api/pay 200 OK duration={rnd.randint(130, 260)}ms",
                        req_id,
                        trace_id,
                    )
                )

    ground_truth = {
        "scenario_name": "upstream_outage",
        "root_cause": "External payment provider pay-gateway.ext 503 Service Unavailable triggering retry storm and client thread pool exhaustion",
        "root_cause_keywords": ["pay-gateway", "upstream", "503", "retry", "thread", "payment-service", "exhaust"],
        "expected_failing_services": ["payment-service", "checkout-service", "api-gateway"],
        "incident_window": (
            (start_ts + timedelta(seconds=p1 * 0.8)).strftime("%Y-%m-%d %H:%M:%S"),
            (start_ts + timedelta(seconds=p2 * 0.8)).strftime("%Y-%m-%d %H:%M:%S"),
        ),
        "incident_start": (start_ts + timedelta(seconds=p1 * 0.8)).strftime("%Y-%m-%d %H:%M:%S"),
        "incident_end": (start_ts + timedelta(seconds=p2 * 0.8)).strftime("%Y-%m-%d %H:%M:%S"),
        "hint": "Payment service timing out with 504 errors",
    }
    return lines, ground_truth


class ScenarioGenerator:
    """Helper class to generate benchmark scenarios."""

    @staticmethod
    def generate_db_pool_exhaustion(num_lines: int = 600) -> tuple[list[str], dict[str, Any]]:
        return generate_db_pool_exhaustion(num_lines=num_lines)

    @staticmethod
    def generate_oom_kill(num_lines: int = 500) -> tuple[list[str], dict[str, Any]]:
        return generate_oom_kill(num_lines=num_lines)

    @staticmethod
    def generate_bad_deployment(num_lines: int = 500) -> tuple[list[str], dict[str, Any]]:
        return generate_bad_deployment(num_lines=num_lines)

    @staticmethod
    def generate_upstream_outage(num_lines: int = 500) -> tuple[list[str], dict[str, Any]]:
        return generate_upstream_outage(num_lines=num_lines)

    @classmethod
    def generate_all(cls) -> dict[str, tuple[list[str], dict[str, Any]]]:
        return {
            "db_pool_exhaustion": cls.generate_db_pool_exhaustion(),
            "oom_kill": cls.generate_oom_kill(),
            "bad_deployment": cls.generate_bad_deployment(),
            "upstream_outage": cls.generate_upstream_outage(),
        }
