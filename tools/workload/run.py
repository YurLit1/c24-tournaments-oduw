"""Run your HTTP scenario many times and record what the client saw (Python 3.14, standard library).

A scenario is your Python file with a function scenario(ctx) (example: tools/workload/
scenario.example.py); the optional validate(bases, settings) checks the settings before the run.
Run from the project root:

    uv run --no-project --python 3.14 python tools/workload/run.py tools/workload/my-scenario.py \\
        --base api=http://localhost:8080 --env token=API_TOKEN --set resource_id=r1 \\
        --runs 1 --pause 1 --out runs/demo-01
    uv run --no-project --python 3.14 python tools/workload/run.py tools/workload/my-scenario.py \\
        --base api=http://localhost:8080 --env token=API_TOKEN --set resource_id=r1 \\
        --duration 60 --rate 20 --concurrency 10 --out runs/load-01

--rate is scenario starts per second, not HTTP requests. When all --concurrency workers are
busy, the start is skipped (counted as skipped_starts), never queued. Results: requests.csv
and summary.json in the new --out folder; see README.md for the meaning of every field.
Exit code: 0 all scenarios passed, 1 some failed or were stopped, 2 bad settings, 130 Ctrl+C.
"""

import argparse
import importlib.util
import math
import os
import sys
import threading
import time
import urllib.parse
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from types import ModuleType
from typing import Any

from client import Context, ScenarioStopped
from results import Results

EXIT_INTERRUPTED = 130


def positive(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return number


def non_negative(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be finite and not negative")
    return number


def assignments(values: list[str]) -> dict[str, str]:
    """NAME=VALUE arguments as a dictionary; names must be unique and values non-empty."""
    result: dict[str, str] = {}
    for value in values:
        name, separator, content = value.partition("=")
        if not separator or not name or not content or name in result:
            raise ValueError("expected unique NAME=VALUE arguments")
        result[name] = content
    return result


def read_bases(values: list[str]) -> dict[str, str]:
    bases = assignments(values)
    if not bases:
        raise ValueError("supply at least one --base NAME=URL")
    for url in bases.values():
        parsed = urllib.parse.urlsplit(url)
        plain = parsed.scheme in ("http", "https") and parsed.hostname
        extras = parsed.username or parsed.password or parsed.query or parsed.fragment
        if not plain or extras:
            raise ValueError("base must be an HTTP(S) URL without credentials, query or fragment")
    return bases


def read_settings(values: list[str], from_environment: list[str]) -> dict[str, str]:
    """--set values plus --env values taken from environment variables (for tokens)."""
    settings = assignments(values)
    for name, variable in assignments(from_environment).items():
        if name in settings:
            raise ValueError(f"setting {name} occurs in both --set and --env")
        settings[name] = os.environ[variable]
    return settings


def load_scenario(path: Path) -> ModuleType:
    """Import the scenario file; it is executable code, so run only files you trust."""
    spec = importlib.util.spec_from_file_location("workload_scenario", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load scenario")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    if not callable(getattr(module, "scenario", None)):
        raise TypeError("scenario file must define scenario(ctx)")
    return module


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("scenario", type=Path)

    limit = parser.add_mutually_exclusive_group()
    limit.add_argument("--runs", type=int, help="number of scenario starts (default 1)")
    limit.add_argument(
        "--duration", type=positive, help="seconds admitting new scenarios; active ones then finish"
    )

    parser.add_argument(
        "--rate", type=positive, default=1, help="target scenario starts per second, not HTTP requests"
    )
    parser.add_argument("--concurrency", type=int, default=1, help="scenarios running at once")
    parser.add_argument("--timeout", type=positive, default=5, help="HTTP socket timeout, seconds")
    parser.add_argument("--scenario-timeout", type=positive, default=30, help="time of one scenario, seconds")
    parser.add_argument(
        "--pause", type=non_negative, default=0, help="pause after each HTTP response, seconds"
    )
    parser.add_argument("--seed", type=int, default=7, help="seed of ctx.random")

    parser.add_argument("--base", action="append", default=[], metavar="NAME=URL")
    parser.add_argument("--set", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--env", action="append", default=[], metavar="NAME=ENVIRONMENT_VARIABLE")
    parser.add_argument(
        "--out", type=Path, required=True, help="new output folder; an existing one is refused"
    )
    args = parser.parse_args(argv)

    if args.concurrency < 1 or (args.runs is not None and args.runs < 1):
        parser.error("runs and concurrency must be positive integers")
    if args.out.exists():
        parser.error(f"{args.out} exists: choose a new output folder")

    try:
        args.bases = read_bases(args.base)
        args.settings = read_settings(args.set, args.env)
        args.module = load_scenario(args.scenario.resolve())
        if callable(getattr(args.module, "validate", None)):
            args.module.validate(args.bases, args.settings)
    except (ValueError, TypeError, OSError, KeyError) as error:
        parser.error(str(error))

    return args


def execute(
    scenario: Callable[[Any], None],
    factory: Callable[[int], Any],
    results: Results,
    *,
    runs: int | None,
    duration: float | None,
    rate: float,
    concurrency: int,
    stop: threading.Event,
) -> dict[str, Any]:
    """Start scenarios at `rate` per second; a start finding all workers busy is skipped, not queued."""
    start = time.monotonic()
    until = start + duration if duration is not None else math.inf
    pending: set[Future[None]] = set()
    launched = skipped = 0
    interrupted = False
    next_start = start

    def invoke(index: int) -> None:
        try:
            scenario(factory(index))
        except ScenarioStopped:
            results.scenario("stopped")
        except Exception as error:
            results.scenario("failed")
            # no message: it may hold a token
            print(f"scenario {index}: {type(error).__name__}", file=sys.stderr)
        else:
            results.scenario("passed")

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        try:
            while not stop.is_set() and time.monotonic() < until and (runs is None or launched < runs):
                pending = {future for future in pending if not future.done()}
                delay = min(next_start, until) - time.monotonic()
                if delay > 0:
                    stop.wait(delay)
                    continue

                if len(pending) < concurrency:
                    pending.add(pool.submit(invoke, launched))
                    launched += 1
                else:
                    skipped += 1
                next_start = time.monotonic() + 1 / rate

            while pending:
                _, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
        except KeyboardInterrupt:
            interrupted = True
            stop.set()  # running scenarios see it at their next ctx call

    return results.finish(time.monotonic() - start, skipped, interrupted)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        results = Results(args.out)
    except OSError as error:
        print(f"cannot create {args.out}: {error}", file=sys.stderr)
        return 2

    stop = threading.Event()

    def make_context(index: int) -> Context:
        return Context(
            index,
            bases=args.bases,
            settings=args.settings,
            seed=args.seed,
            timeout=args.timeout,
            scenario_timeout=args.scenario_timeout,
            pause=args.pause,
            stop=stop,
            results=results,
        )

    summary = execute(
        args.module.scenario,
        make_context,
        results,
        runs=None if args.duration else (args.runs or 1),
        duration=args.duration,
        rate=args.rate,
        concurrency=args.concurrency,
        stop=stop,
    )

    print(
        f"scenarios={summary['scenarios']} requests={summary['requests']} skipped_starts={summary['skipped_starts']}"
    )
    print(f"results: {args.out}")

    if summary["interrupted"]:
        return EXIT_INTERRUPTED
    return int(bool(summary["scenarios"].get("failed") or summary["scenarios"].get("stopped")))


if __name__ == "__main__":
    raise SystemExit(main())
