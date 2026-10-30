"""Settings from environment variables (compose.yaml, .env); one image runs every process."""

import os


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


INSTANCE = os.environ.get("INSTANCE", "local")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:5432/app")
POOL_MIN = _int("POOL_MIN", 1)
POOL_SIZE = _int("POOL_SIZE", 10)
POOL_TIMEOUT_S = _float("POOL_TIMEOUT_S", 2.0)
STATEMENT_TIMEOUT_MS = _int("STATEMENT_TIMEOUT_MS", 2000)

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9094")
GROUP_ID = os.environ.get("GROUP_ID", INSTANCE)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
EXTERNAL_URL = os.environ.get("EXTERNAL_URL", "http://localhost:8090")
FLAGS_URL = os.environ.get("FLAGS_URL", "http://localhost:8099")
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "http://localhost:8180/realms/project")
OIDC_INTERNAL_URL = os.environ.get("OIDC_INTERNAL_URL", OIDC_ISSUER)
CLIENT_ORIGIN = os.environ.get("CLIENT_ORIGIN", "http://localhost:8081")

OTEL_ENABLED = os.environ.get("OTEL_ENABLED", "off") == "on"
OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

# experiment modes: what each value changes is yours to write
INVARIANT_MODE = os.environ.get("INVARIANT_MODE", "protected")
RATE_LIMIT_PER_MIN = _int("RATE_LIMIT_PER_MIN", 120)
JWT_REVOCATION = os.environ.get("JWT_REVOCATION", "on") == "on"

PROBLEM_BASE = os.environ.get("PROBLEM_BASE", "https://example.edu/problems/")

FAULTS = os.environ.get("FAULTS", "off") == "on"
FAULT_DIR = os.environ.get("FAULT_DIR", "/faults")
