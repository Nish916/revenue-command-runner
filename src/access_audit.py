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
    "dealwork": ("https://dealwork.ai", {
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
        return {"status": data["status"], "jobs_completed": data["jobsCompleted"], "services_returned": len(data["services"])}
    if endpoint == "wallet":
        require(integer(payload.get("balanceCents")) and isinstance(payload.get("transactions"), list))
        return {"balance_cents": payload["balanceCents"], "currency": "USD", "transactions_returned": len(payload["transactions"])}
    if endpoint == "connect":
        keys = ("connected", "onboarded", "chargesEnabled", "payoutsEnabled")
        require(all(type(payload.get(key)) is bool for key in keys))
        return {key: payload[key] for key in keys}
    require(endpoint == "jobs" and isinstance(payload.get("jobs"), list))
    return {"records_returned": len(payload["jobs"])}


def audit(home=None, getter=None):
    home, getter = Path.home() if home is None else Path(home), fetch if getter is None else getter
    report = {"checked_at": datetime.now(timezone.utc).isoformat(),
              "semantics": "Reported balances and counts; not proof of organic income or withdrawability.",
              "providers": {}}
    for provider, (_, paths) in ROUTES.items():
        token, credential_error = credentials(provider, home)
        endpoints = {}
        for endpoint in paths:
            status, payload, error = (None, None, credential_error) if credential_error else getter(provider, endpoint, token)
            result = {"http_status": status, "state": "UNKNOWN"}
            if error or status != 200:
                result["reason"] = error or "HTTP_ERROR"
            else:
                try:
                    result["data"] = normalize(provider, endpoint, payload)
                    result["state"] = "AUTHENTICATED_READ_VERIFIED"
                except (ValueError, TypeError, InvalidOperation):
                    result["reason"] = "INVALID_RESPONSE"
            endpoints[endpoint] = result
        state = "AUTHENTICATED_READ_VERIFIED" if all(r["state"] == "AUTHENTICATED_READ_VERIFIED" for r in endpoints.values()) else "UNKNOWN"
        report["providers"][provider] = {"state": state, "endpoints": endpoints}
    return report


def save(report, output):
    output = Path(output).expanduser()
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.parent.chmod(0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=output.parent, prefix=".access-audit-", delete=False) as stream:
            temporary = stream.name
            os.fchmod(stream.fileno(), 0o600)
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="~/.openwork/access-audit.json")
    args = parser.parse_args()
    report = audit()
    try:
        save(report, args.output)
    except Exception:
        print("Snapshot could not be saved; no account details printed.")
        return 2
    for provider, data in report["providers"].items():
        checks = ", ".join(f"{name}:{item['http_status'] or '-'}:{item['state']}" for name, item in data["endpoints"].items())
        print(f"{provider}: {data['state']} ({checks})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
