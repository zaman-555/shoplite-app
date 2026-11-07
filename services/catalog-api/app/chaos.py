"""Fault-injection helpers. Both flags are inactive when set to 0."""

LATENCY_SAMPLE_RATE = 0.30


def should_inject_latency(latency_ms: int, sample: float) -> bool:
    return latency_ms > 0 and sample < LATENCY_SAMPLE_RATE


def should_inject_error(error_rate: float, sample: float) -> bool:
    return error_rate > 0 and sample < error_rate
