#!/usr/bin/env python3
"""Hermes hook test logger.

- Writes each hook invocation as JSONL to a configurable log file.
- Supports log level control.
- Retries webhook POST on failure (exponential backoff + jitter).
- Can run as a drop-in hook command and read payload from stdin.
"""

from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _to_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _to_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    v = _env(name, str(int(default))).strip().lower()
    return v in ("1", "true", "yes", "on", "y")


def _level_name(s: str) -> int:
    level = str(s).upper()
    return getattr(logging, level, logging.INFO)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write hermes hook payload to JSON log with retry")
    parser.add_argument("hook", nargs="?", default=_env("HERMES_HOOK_NAME", "unknown-hook"), help="Hook name")
    parser.add_argument("--log-file", default=_env("HERMES_HOOK_LOG_FILE", str(Path.home() / ".hermes" / "logs" / "hermes-hook-test.log")), help="Target log file")
    parser.add_argument("--log-level", default=_env("HERMES_HOOK_LOG_LEVEL", "INFO"), help="DEBUG|INFO|WARNING|ERROR")
    parser.add_argument("--max-retries", type=int, default=_to_int("HERMES_HOOK_MAX_RETRIES", 3), help="Retry count for webhook")
    parser.add_argument("--initial-delay", type=float, default=_to_float("HERMES_HOOK_INITIAL_DELAY", 1.0), help="First retry delay seconds")
    parser.add_argument("--max-delay", type=float, default=_to_float("HERMES_HOOK_MAX_DELAY", 15.0), help="Max delay cap")
    parser.add_argument("--backoff", type=float, default=_to_float("HERMES_HOOK_BACKOFF", 2.0), help="Exponential backoff factor")
    parser.add_argument("--jitter", type=float, default=_to_float("HERMES_HOOK_JITTER", 0.3), help="Jitter ratio [0,1)")
    parser.add_argument("--webhook-url", default=_env("HERMES_HOOK_WEBHOOK_URL", ""), help="Optional webhook POST target")
    parser.add_argument("--timeout", type=float, default=_to_float("HERMES_HOOK_REQUEST_TIMEOUT", 5.0), help="HTTP timeout seconds")
    parser.add_argument("--strict", action="store_true", default=_bool("HERMES_HOOK_STRICT_FAIL", False), help="Exit 1 when webhook ultimately fails")
    parser.add_argument("--no-json", action="store_true", default=_bool("HERMES_HOOK_FORCE_PLAIN", False), help="Write plain text instead of json per line")
    return parser.parse_args()


def setup_logger(log_file: Path, level: int) -> logging.Logger:
    logger = logging.getLogger("hermes-hook-test")
    logger.setLevel(level)

    # remove duplicated handlers when hook called frequently in same process
    for h in list(logger.handlers):
        logger.removeHandler(h)

    log_dir = log_file.parent
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_file,
        maxBytes=_to_int("HERMES_HOOK_LOG_MAX_BYTES", 5 * 1024 * 1024),
        backupCount=_to_int("HERMES_HOOK_LOG_BACKUP_COUNT", 3),
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)

    if _bool("HERMES_HOOK_STDOUT", False):
        std = logging.StreamHandler(sys.stderr)
        std.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(std)

    return logger


def read_payload() -> str:
    data = sys.stdin.read()
    if data:
        return data.strip()
    return ""


def try_post(url: str, payload_obj: dict, timeout: float, logger: logging.Logger) -> bool:
    data = json.dumps(payload_obj, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        code = resp.getcode()
        body = resp.read(1024)
        logger.debug("webhook response code=%s body=%s", code, body.decode(errors="ignore"))
        return 200 <= code < 300


def post_with_retry(url: str, payload: dict, max_retries: int, initial_delay: float, max_delay: float, backoff: float, jitter: float, timeout: float, logger: logging.Logger) -> bool:
    attempt = 0
    while True:
        attempt += 1
        try:
            if try_post(url, payload, timeout, logger):
                logger.info("webhook success hook=%s attempt=%s url=%s", payload.get("hook"), attempt, url)
                return True
            logger.warning("webhook got non-2xx (attempt=%s). retrying", attempt)
        except urllib.error.URLError as e:
            logger.warning("webhook failed (attempt=%s/%s): %s", attempt, max_retries + 1, e)
        except Exception as e:
            logger.exception("webhook unexpected error attempt=%s: %s", attempt, e)

        if attempt > max_retries:
            logger.error("webhook give up hook=%s after %s attempts", payload.get("hook"), attempt)
            return False

        delay = min(initial_delay * (backoff ** (attempt - 1)), max_delay)
        jitter_sec = delay * max(0.0, min(jitter, 0.99)) * random.random()
        logger.debug("sleep %.3fs before retry", delay + jitter_sec)
        time.sleep(delay + jitter_sec)


def main() -> int:
    args = parse_args()

    level = _level_name(args.log_level)
    log_path = Path(args.log_file).expanduser()
    logger = setup_logger(log_path, level)

    payload_text = read_payload()

    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hook": args.hook,
        "level": args.log_level.upper(),
        "argv": sys.argv[1:],
        "payload_text": payload_text or None,
    }

    if payload_text:
        try:
            event["payload_json"] = json.loads(payload_text)
        except json.JSONDecodeError:
            logger.debug("payload is not JSON, keep raw text")

    if args.no_json:
        logger.log(level, "hook=%s payload=%r", args.hook, payload_text)
    else:
        logger.log(level, json.dumps(event, ensure_ascii=False))

    hook_ok = True
    if args.webhook_url:
        hook_ok = post_with_retry(
            url=args.webhook_url,
            payload=event,
            max_retries=args.max_retries,
            initial_delay=args.initial_delay,
            max_delay=args.max_delay,
            backoff=args.backoff,
            jitter=args.jitter,
            timeout=args.timeout,
            logger=logger,
        )

    if hook_ok:
        return 0
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
