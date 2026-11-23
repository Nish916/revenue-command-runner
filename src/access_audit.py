#!/usr/bin/env python3
"""Read existing worker accounts only; wallet balances are not earned-income proof."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import signal
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

TIMEOUT = 10
MAX_BODY = 1_048_576
ROUTES = {
    "dealwork": ("https://api.dealwork.ai", {
        "wallet": "/api/v1/wallet/balance",
        "contracts": "/api/v1/contracts?role=worker&per_page=50",
        "pending_requests": "/api/v1/listings/requests/pending"}),
    "toku": ("https://www.toku.agency", {
        "agent": "/api/agents/me", "wallet": "/api/agents/wallet",
        "connect": "/api/agents/connect", "jobs": "/api/jobs?role=worker"})}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Redirect rejected", headers, fp)


@contextmanager
def deadline():
    """Unix CLI wall-clock deadline, including response-body reads."""
    def expired(signum, frame):
        raise TimeoutError()
    started = time.monotonic()
    previous_handler = signal.signal(signal.SIGALRM, expired)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, TIMEOUT)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0]:
            signal.setitimer(signal.ITIMER_REAL,
                            max(0.001, previous_timer[0] - (time.monotonic() - started)),
                            previous_timer[1])


def fetch(provider, endpoint, token):
    status = None
    try:
        origin, paths = ROUTES[provider]
        request = Request(origin + paths[endpoint], method="GET", headers={
            "Authorization": "Bearer " + token, "Accept": "application/json"})
        with deadline(), build_opener(NoRedirect()).open(request, timeout=TIMEOUT) as response:
            status = response.status
            if status != 200:
                return status, None, "HTTP_ERROR"
            body = response.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                return status, None, "RESPONSE_TOO_LARGE"
            return status, json.loads(body), None
    except HTTPError as error:
        status = error.code
        try:
            error.close()
        except Exception:
            pass
        return status, None, "REDIRECT_REJECTED" if 300 <= status < 400 else "HTTP_ERROR"
    except Exception:
        return status, None, "READ_FAILED"  # Never render exceptions or response bodies.


def credentials(provider, home):
    try:
        path = home / (".openwork/credentials.json" if provider == "dealwork" else ".toku-worker/api_key")
        with path.open("rb") as stream:
            content = stream.read(16385)
        if len(content) > 16384:
            raise ValueError()
        if provider == "dealwork":
            config = json.loads(content)
            if config.get("baseUrl", ROUTES[provider][0]).rstrip("/") != ROUTES[provider][0]:
                return None, "UNAPPROVED_ORIGIN"
            token = config.get("apiKey")
        else:
            token = content.decode("utf-8").strip()
        if not isinstance(token, str) or not re.fullmatch(r"[!-~]{1,8192}", token):
            raise ValueError()
        return token, None
    except FileNotFoundError:
        return None, "CREDENTIALS_MISSING"
    except Exception:
        return None, "CREDENTIALS_INVALID"


def require(condition):
    if not condition:
        raise ValueError()


def integer(value):
    return type(value) is int


def normalize(provider, endpoint, payload):
    require(isinstance(payload, dict))
    if provider == "dealwork":
        data = payload.get("data")
        if endpoint != "wallet":
            require(isinstance(data, list))
            return {"records_returned": len(data)}  # A page count, never a total.
        require(isinstance(data, dict))
        for name in ("available", "locked"):
            require(isinstance(data.get(name), str))
            require(Decimal(data[name]).is_finite())
        require(data.get("currency") == "USD")
        return {key: data[key] for key in ("available", "locked", "currency")}
    if endpoint == "agent":
        data = payload.get("agent")
        require(isinstance(data, dict))
        require(isinstance(data.get("status"), str) and bool(re.fullmatch(r"[a-zA-Z_ -]{1,40}", data["status"])))
        require(integer(data.get("jobsCompleted")) and data["jobsCompleted"] >= 0)
        require(isinstance(data.get("services"), list))
        return {"status": data["status"], "jobsCompleted": data["jobsCompleted"], "services_count": len(data["services"])}
    if endpoint == "wallet":
        data = payload.get("wallet")
        require(isinstance(data, dict))
        for name in ("balance", "pending"):
            require(isinstance(data.get(name), str))
            require(Decimal(data[name]).is_finite())
        require(data.get("currency") == "USD")
        return {key: data[key] for key in ("balance", "pending", "currency")}
    if endpoint in ("jobs", "connect"):
        data = payload.get("jobs") if endpoint == "jobs" else payload.get("connections")
        if data is None and endpoint == "connect":
            data = payload.get("data")
        require(isinstance(data, list))
        return {"records_returned": len(data)}
    raise ValueError()


def audit_main():
    parser = argparse.ArgumentParser(description="Access Audit CLI")
    parser.add_argument("--provider", choices=list(ROUTES.keys()), required=True)
    parser.add_argument("--endpoint", choices=list(ROUTES["dealwork"].keys()), required=True)
    parser.add_argument("--home", type=Path, default=Path.home())
    args = parser.parse_args()

    if args.endpoint not in ROUTES[args.provider][1]:
        print(json.dumps({"status": 400, "error": "INVALID_ENDPOINT"}))
        return

    token, err = credentials(args.provider, args.home)
    if err:
        print(json.dumps({"status": 401, "error": err}))
        return

    status, payload, err = fetch(args.provider, args.endpoint, token)
    if err:
        print(json.dumps({"status": status if status else 500, "error": err}))
        return

    try:
        normalized = normalize(args.provider, args.endpoint, payload)
        print(json.dumps({"status": status, "data": normalized}))
    except Exception:
        print(json.dumps({"status": status, "error": "NORMALIZATION_FAILED"}))


if __name__ == "__main__":
    audit_main()