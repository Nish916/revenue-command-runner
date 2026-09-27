#!/usr/bin/env python3
"""Refresh a public Agent402 listing at most daily; never infer revenue."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from access_audit import MAX_BODY, NoRedirect, TIMEOUT, deadline, save

ORIGIN = "https://nexuseval.vercel.app"
MANIFEST = ORIGIN + "/.well-known/x402"
REGISTER = "https://agent402.tools/api/index/register"
INDEX = "https://agent402.tools/api/index"
COLLECTIONS = {"resources", "origins", "items", "data", "entries", "results", "index", "merchants", "agents", "services", "endpoints", "sellers", "tools"}
URL_FIELDS = {"origin", "url", "resource", "resourceUrl", "resource_url", "endpoint", "baseUrl", "base_url"}


def request(method, url):
    status = None
    if (method, url) not in {("GET", MANIFEST), ("POST", REGISTER), ("GET", INDEX)}:
        return None, None, "DISALLOWED_REQUEST"
    body = json.dumps({"origin": ORIGIN}).encode() if method == "POST" else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        req = Request(url, data=body, headers=headers, method=method)
        with deadline(), build_opener(NoRedirect()).open(req, timeout=TIMEOUT) as response:
            status = response.status
            if status != 200:
                return status, None, "HTTP_ERROR"
            content = response.read(MAX_BODY + 1)
            if len(content) > MAX_BODY:
                return status, None, "RESPONSE_TOO_LARGE"
            return status, json.loads(content), None
    except HTTPError as error:
        status = error.code
        try:
            error.close()
        except Exception:
            pass
        return status, None, "REDIRECT_REJECTED" if 300 <= status < 400 else "HTTP_ERROR"
    except Exception:
        return status, None, "READ_FAILED"


def matches_origin(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme == "https" and parsed.netloc.lower() == "nexuseval.vercel.app"
    except ValueError:
        return False


def contains_origin(value):
    if isinstance(value, str):
        return matches_origin(value)
    if isinstance(value, list):
        return any(contains_origin(item) for item in value)
    if isinstance(value, dict):
        return any((key in URL_FIELDS and matches_origin(item)) or
                   (key in COLLECTIONS and contains_origin(item))
                   for key, item in value.items())
    return False


def index_presence(payload):
    """Only inspect recognized index collections, never an arbitrary text echo."""
    if isinstance(payload, list):
        return "CONFIRMED" if contains_origin(payload) else "NOT_CONFIRMED"
    if isinstance(payload, dict):
        states = [index_presence(value) for key, value in payload.items() if key in COLLECTIONS]
        if "CONFIRMED" in states:
            return "CONFIRMED"
        if "NOT_CONFIRMED" in states:
            return "UNKNOWN" if payload.get("complete") is False else "NOT_CONFIRMED"
    return "UNKNOWN"


def read_result(status, payload, error):
    result = {"http_status": status, "state": "UNKNOWN"}
    if error or status != 200:
        result["reason"] = error or "HTTP_ERROR"
    elif not isinstance(payload, (dict, list)):
        result["reason"] = "UNRECOGNIZED_JSON"
    else:
        result["state"] = "CONFIRMED"
    return result


def refresh(now=None, requester=None):
    now = now or datetime.now(timezone.utc)
    requester = requester or request
    status, payload, error = requester("GET", MANIFEST)
    manifest = read_result(status, payload, error)
    if manifest["state"] == "CONFIRMED" and isinstance(payload, dict):
        for key in ("resources", "endpoints"):
            if isinstance(payload.get(key), list):
                manifest["resource_count"] = len(payload[key])
                break
    registration = {"http_status": None, "state": "UNKNOWN", "reason": "MANIFEST_NOT_VERIFIED"}
    if manifest["state"] == "CONFIRMED":
        status, payload, error = requester("POST", REGISTER)
        registration = {"http_status": status, "state": "UNKNOWN"}
        if error or status != 200:
            registration["reason"] = error or "HTTP_ERROR"
        elif isinstance(payload, dict) and type(payload.get("listed")) is bool:
            registration["listed"] = payload["listed"]
            registration["state"] = "CONFIRMED" if payload["listed"] else "NOT_CONFIRMED"
        else:
            registration["reason"] = "NO_BOOLEAN_LISTED_ACKNOWLEDGEMENT"
    status, payload, error = requester("GET", INDEX)
    index = read_result(status, payload, error)
    if index["state"] == "CONFIRMED":
        index["state"] = index_presence(payload)
        if isinstance(payload, dict):
            if type(payload.get("complete")) is bool:
                index["complete"] = payload["complete"]
            for source, destination in (("page", "checked_page"), ("pages", "total_pages")):
                value = payload.get(source)
                if type(value) is int and value >= 0:
                    index[destination] = value
        if index["state"] == "UNKNOWN":
            index["reason"] = "PARTIAL_INDEX" if index.get("complete") is False else "UNRECOGNIZED_INDEX"
    return {"checked_at": now.isoformat(), "manifest": manifest,
            "registration": registration, "index": index,
            "listing_state": index["state"],
            "semantics": "Index presence only; no proof of usage, customers, income, or settlement."}


def recently_attempted(output, now):
    try:
        with Path(output).expanduser().open("rb") as stream:
            raw = stream.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            return False
        checked = datetime.fromisoformat(json.loads(raw)["checked_at"])
        age = (now - checked).total_seconds()
        return 0 <= age < 24 * 60 * 60
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="~/.openwork/agent402-refresh.json")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if recently_attempted(args.output, now):
        print("Agent402 refresh skipped: previous attempt is less than 24 hours old.")
        return 0
    report = refresh(now)
    try:
        save(report, args.output)
    except Exception:
        print("Agent402 refresh snapshot could not be saved.")
        return 2
    print(f"Agent402 index presence: {report['listing_state']}; registration acknowledgement: {report['registration']['state']}.")
    return 0  # HTTP failures remain in the snapshot; other scheduled audits continue.


if __name__ == "__main__":
    raise SystemExit(main())
