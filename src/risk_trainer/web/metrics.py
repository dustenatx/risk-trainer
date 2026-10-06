"""CloudWatch custom metrics as embedded metric format (EMF) log lines (PRD R15).

In Lambda, each line written to the log group becomes a metric; there is no PutMetricData call.
There are no dimensions, so each name is one custom metric (the always-free allowance is 10).
"""

import json
import logging
import time
from enum import StrEnum

from risk_trainer.web.logging import request_id_var

METRICS_LOGGER = "risk_trainer.metrics"
logger = logging.getLogger(METRICS_LOGGER)


class Metric(StrEnum):
    ATTEMPTS = "Attempts"
    RATE_LIMITED = "RateLimited"
    RATE_LIMIT_UNAVAILABLE = "RateLimitUnavailable"


def emf_line(namespace: str, metric: Metric, now_ms: int | None = None) -> str:
    """One EMF document counting a single event. Holds no request data except the request ID."""
    document = {
        "_aws": {
            "Timestamp": now_ms if now_ms is not None else int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": namespace,
                    "Dimensions": [[]],
                    "Metrics": [{"Name": metric.value, "Unit": "Count"}],
                }
            ],
        },
        metric.value: 1,
        "request_id": request_id_var.get(),
    }
    return json.dumps(document, separators=(",", ":"))


class Metrics:
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace

    def count(self, metric: Metric) -> None:
        logger.info(emf_line(self.namespace, metric))
