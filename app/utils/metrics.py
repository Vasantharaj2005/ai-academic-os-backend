"""Prometheus metrics configuration."""

from prometheus_client import Counter, Histogram, Gauge, Summary
import time
from functools import wraps


# HTTP Metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# AI Generation Metrics
course_generations_total = Counter(
    "course_generations_total",
    "Total course generation requests",
    ["status"]  # success | failure
)

course_generation_duration_seconds = Histogram(
    "course_generation_duration_seconds",
    "Course generation duration",
    buckets=[10, 30, 60, 120, 300, 600]
)

agent_calls_total = Counter(
    "agent_calls_total",
    "Total agent invocations",
    ["agent_name", "status"]
)

agent_duration_seconds = Histogram(
    "agent_duration_seconds",
    "Agent processing duration",
    ["agent_name"],
    buckets=[1, 5, 10, 30, 60, 120]
)

llm_calls_total = Counter(
    "llm_calls_total",
    "Total LLM API calls",
    ["provider", "model", "status"]
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens used",
    ["provider", "model", "type"]  # type: prompt | completion
)

# Database Metrics
db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
)

# Active connections
active_connections = Gauge("active_connections", "Active WebSocket/long-poll connections")
active_generation_tasks = Gauge("active_generation_tasks", "Currently running generation tasks")


def setup_metrics() -> None:
    """Initialize metrics - can be extended with push gateway config."""
    pass


def track_agent_call(agent_name: str):
    """Decorator to track agent calls."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                agent_calls_total.labels(agent_name=agent_name, status="success").inc()
                return result
            except Exception as e:
                agent_calls_total.labels(agent_name=agent_name, status="failure").inc()
                raise
            finally:
                duration = time.time() - start
                agent_duration_seconds.labels(agent_name=agent_name).observe(duration)
        return wrapper
    return decorator