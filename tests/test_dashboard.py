import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

# The module under test
from src import dashboard


@pytest.fixture
def temp_config(tmp_path: Path) -> Path:
    """
    Create a temporary ``config`` directory with minimal JSON files required
    for the dashboard.  The fixture returns the path to the temporary repo root
    (i.e. the directory that contains the ``config`` folder).
    """
    repo_root = tmp_path / "repo"
    config_dir = repo_root / "config"
    config_dir.mkdir(parents=True)

    # Minimal sources.json – three entries with different statuses
    sources = [
        {"name": "source_a", "status": "active"},
        {"name": "source_b", "status": "inactive"},
        {"name": "source_c", "status": "active"},
    ]
    (config_dir / "sources.json").write_text(json.dumps(sources), encoding="utf-8")

    # Minimal intent-signals.json – two types
    signals = [
        {"id": 1, "type": "lead"},
        {"id": 2, "type": "lead"},
        {"id": 3, "type": "opportunity"},
    ]
    (config_dir / "intent-signals.json").write_text(json.dumps(signals), encoding="utf-8")

    return repo_root


def test_generate_dashboard_uses_temp_config(monkeypatch: pytest.MonkeyPatch, temp_config: Path):
    """
    Verify that ``generate_dashboard`` correctly reads the temporary JSON files
    and produces the expected summary.
    """
    # Patch the internal function that resolves the config directory to point at
    # our temporary location.
    monkeypatch.setattr(dashboard, "_config_dir", lambda: temp_config / "config")

    result: Dict[str, Any] = dashboard.generate_dashboard()

    # Expected aggregation
    expected_sources: Dict[str, int] = {"active": 2, "inactive": 1}
    expected_signals: Dict[str, int] = {"lead": 2, "opportunity": 1}

    assert result["sources"] == expected_sources
    assert result["intent_signals"] == expected_signals


def test_dashboard_raises_on_missing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """
    If a required config file is missing, ``generate_dashboard`` should raise
    ``FileNotFoundError``.
    """
    # Create an empty config directory (no JSON files)
    empty_config = tmp_path / "empty_repo" / "config"
    empty_config.mkdir(parents=True)

    monkeypatch.setattr(dashboard, "_config_dir", lambda: empty_config)

    with pytest.raises(FileNotFoundError):
        dashboard.generate_dashboard()
