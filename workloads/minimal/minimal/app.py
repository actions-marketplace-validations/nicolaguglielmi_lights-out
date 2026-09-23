"""The minimal workload: exists to prove the seam, not to be realistic
(docs/adr/0030 §6). No database, no frontend. Same libraries as the app's
own metrics.py/flags.py (the template ADR 0030 §6 names), inlined here
since the whole service is a few routes.
"""

import os

import prometheus_client
from fastapi import FastAPI, HTTPException, Response
from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider
from openfeature.evaluation_context import EvaluationContext
from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource

APP_VERSION = os.environ.get("APP_VERSION", "dev")

_resource = Resource.create({"service.name": "minimal", "service.version": APP_VERSION})
_provider = MeterProvider(resource=_resource, metric_readers=[PrometheusMetricReader()])
metrics.set_meter_provider(_provider)

api.set_provider_and_wait(FlagdProvider())
_client = api.get_client()
_context = EvaluationContext(attributes={"version": APP_VERSION})


def outage_enabled() -> bool:
    return _client.get_boolean_value("outage", default_value=False, evaluation_context=_context)


app = FastAPI(title="minimal")
FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,metrics")


@app.get("/ping")
def ping():
    if outage_enabled():
        raise HTTPException(status_code=501, detail="outage")
    return {"ok": True}


@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/metrics")
def metrics_endpoint():
    return Response(
        content=prometheus_client.generate_latest(),
        media_type=prometheus_client.CONTENT_TYPE_LATEST,
    )
