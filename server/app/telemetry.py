"""Traces (D1.4, D4.3): with OTEL_ENABLED=on HTTP requests and SQL become spans in Jaeger.

Passing the trace context through Kafka headers (publisher -> worker) is yours.
"""

from fastapi import FastAPI

from . import config


def install(app: FastAPI | None = None) -> None:
    if not config.OTEL_ENABLED:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": config.INSTANCE}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{config.OTEL_ENDPOINT}/v1/traces")))
    trace.set_tracer_provider(provider)

    PsycopgInstrumentor().instrument()
    if app is not None:
        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready,metrics")
