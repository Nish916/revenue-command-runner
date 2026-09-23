"""Revenue Command Dashboard

Provides a simple programmatic interface (and optional CLI) to summarise the
configuration files used by the Revenue Command Runner.  The dashboard reads
the JSON files located in the ``config`` directory and produces a high‑level
summary that can be displayed in CI logs or integrated into other tools.

The module is deliberately lightweight and has no external dependencies beyond
the Python standard library.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def _config_dir() -> Path:
    """
    Return the absolute path to the repository's ``config`` directory.
    The function works regardless of the current working directory.
    """
    # ``src/dashboard.py`` -> repo root -> config
    return Path(__file__).resolve().parents[1] / "config"


def _load_json(file_name: str) -> Any:
    """
    Load a JSON file from the config directory.

    Parameters
    ----------
    file_name: str
        Name of the JSON file (e.g., ``sources.json``).

    Returns
    -------
    Any
        The parsed JSON content.
    """
    path = _config_dir() / file_name
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _summarise_sources(sources: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Produce a simple count of sources by their ``status`` field.

    Parameters
    ----------
    sources: List[Dict[str, Any]]
        List of source objects loaded from ``sources.json``.

    Returns
    -------
    Dict[str, int]
        Mapping from status name to the number of sources with that status.
    """
    summary: Dict[str, int] = {}
    for src in sources:
        status = src.get("status", "unknown")
        summary[status] = summary.get(status, 0) + 1
    return summary


def _summarise_intent_signals(signals: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Produce a count of intent signals by their ``type`` field.

    Parameters
    ----------
    signals: List[Dict[str, Any]]
        List of intent signal objects loaded from ``intent-signals.json``.

    Returns
    -------
    Dict[str, int]
        Mapping from signal type to the number of occurrences.
    """
    summary: Dict[str, int] = {}
    for sig in signals:
        typ = sig.get("type", "unknown")
        summary[typ] = summary.get(typ, 0) + 1
    return summary


def generate_dashboard() -> Dict[str, Any]:
    """
    Build the dashboard data structure.

    The returned dictionary contains two top‑level keys:

    * ``sources`` – a mapping of source status → count.
    * ``intent_signals`` – a mapping of signal type → count.

    Returns
    -------
    Dict[str, Any]
        The dashboard representation.
    """
    sources_raw = _load_json("sources.json")
    signals_raw = _load_json("intent-signals.json")

    if not isinstance(sources_raw, list):
        raise ValueError("sources.json must contain a JSON array")
    if not isinstance(signals_raw, list):
        raise ValueError("intent-signals.json must contain a JSON array")

    dashboard = {
        "sources": _summarise_sources(sources_raw),
        "intent_signals": _summarise_intent_signals(signals_raw),
    }
    return dashboard


def _pretty_print(dashboard: Dict[str, Any]) -> None:
    """
    Print the dashboard in a human‑readable table format.
    """
    print("=== Revenue Command Dashboard ===")
    print("\nSources by status:")
    for status, count in sorted(dashboard["sources"].items()):
        print(f"  {status:20}: {count}")

    print("\nIntent signals by type:")
    for typ, count in sorted(dashboard["intent_signals"].items()):
        print(f"  {typ:20}: {count}")


def main(argv: List[str] | None = None) -> int:
    """
    Entry point for the ``python -m src.dashboard`` command.

    Parameters
    ----------
    argv: List[str] | None
        Optional argument list; defaults to ``sys.argv[1:]``.

    Returns
    -------
    int
        Exit status (0 for success, non‑zero for failure).
    """
    try:
        dashboard = generate_dashboard()
        _pretty_print(dashboard)
        return 0
    except Exception as exc:  # pragma: no cover – defensive
        print(f"Error generating dashboard: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
