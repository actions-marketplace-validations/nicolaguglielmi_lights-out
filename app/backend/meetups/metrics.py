"""OTel FastAPI metrics exported as Prometheus text, stable HTTP semconv (docs/adr/0007)."""

import os

import prometheus_client
from fastapi import FastAPI
from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource


def setup_metrics(app: FastAPI) -> None:
    resource = Resource.create(
        {
            "service.name": "meetups",
            "service.version": os.environ.get("APP_VERSION", "dev"),
        }
    )
    provider = MeterProvider(
        resource=resource, metric_readers=[PrometheusMetricReader()]
    )
    metrics.set_meter_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,metrics")


def metrics_text() -> bytes:
    return prometheus_client.generate_latest()


CONTENT_TYPE = prometheus_client.CONTENT_TYPE_LATEST
