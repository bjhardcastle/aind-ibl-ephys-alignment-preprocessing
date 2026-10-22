"""Opt-in conversion metric extensions: configuration, resolution, plumbing."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError

from aind_ibl_ephys_alignment_preprocessing import ephys
from aind_ibl_ephys_alignment_preprocessing._constants import CONVERSION_METRICS
from aind_ibl_ephys_alignment_preprocessing.discovery import prepare_result_dirs
from aind_ibl_ephys_alignment_preprocessing.types import PipelineConfig

FAKE_MODULE = "fake_conversion_activity"


def _config(tmp_path: Path, **kwargs) -> PipelineConfig:
    return PipelineConfig(
        data_root=tmp_path / "data",
        results_root=tmp_path / "results",
        neuroglancer_file=Path("ng.json"),
        manifest_csv=Path("manifest.csv"),
        **kwargs,
    )


@pytest.fixture
def fake_metric(monkeypatch: pytest.MonkeyPatch) -> object:
    """Point ``raw_activity`` at an importable stand-in for the conversion module."""
    sentinel = object()
    module = ModuleType(FAKE_MODULE)
    module.raw_activity = lambda: sentinel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, FAKE_MODULE, module)
    monkeypatch.setitem(CONVERSION_METRICS, "raw_activity", (FAKE_MODULE, "raw_activity"))
    return sentinel


@pytest.fixture
def missing_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate a conversion release that does not provide ``raw_activity``."""
    monkeypatch.setitem(CONVERSION_METRICS, "raw_activity", ("no_such_conversion_module", "raw_activity"))


def test_config_defaults_to_no_extra_metrics(tmp_path):
    assert _config(tmp_path).extra_metrics == ()


def test_config_accepts_known_and_rejects_unknown_or_repeated(tmp_path):
    assert _config(tmp_path, extra_metrics=("raw_activity",)).extra_metrics == ("raw_activity",)
    with pytest.raises(ValidationError, match="Unknown conversion metrics"):
        _config(tmp_path, extra_metrics=("rawActivity",))
    with pytest.raises(ValidationError, match="Duplicate"):
        _config(tmp_path, extra_metrics=("raw_activity", "raw_activity"))


def test_no_request_leaves_extract_continuous_signature_unchanged():
    """Conversion releases without ``extra_metrics`` must still be callable."""
    assert ephys.extra_metric_kwargs(()) == {}


def test_requested_metric_is_configured_from_conversion(fake_metric):
    assert ephys.build_extra_metrics(("raw_activity",)) == (fake_metric,)
    assert ephys.extra_metric_kwargs(["raw_activity"]) == {"extra_metrics": (fake_metric,)}


def test_unavailable_metric_fails_with_clear_message(missing_metric):
    with pytest.raises(RuntimeError, match="raw_activity.*does not provide"):
        ephys.build_extra_metrics(("raw_activity",))
    with pytest.raises(ValueError, match="Unknown conversion metric"):
        ephys.build_extra_metrics(("nope",))


@pytest.fixture
def stream_inputs(tmp_path, monkeypatch):
    """A sorted session on disk and recording conversion calls."""
    import aind_ephys_ibl_gui_conversion.ephys as conversion

    sorted_name = "ecephys_1_sorted_2025-01-01"
    data_root = tmp_path / "data"
    (data_root / sorted_name).mkdir(parents=True)
    calls: dict[str, list] = {"continuous": [], "spikes": []}
    monkeypatch.setattr(conversion, "extract_continuous", lambda *a, **k: calls["continuous"].append(k))
    monkeypatch.setattr(conversion, "extract_spikes", lambda *a, **k: calls["spikes"].append(k))
    out = prepare_result_dirs("1", tmp_path / "results")
    return sorted_name, data_root, out, calls


@pytest.mark.parametrize("requested", [(), ("raw_activity",)])
def test_stream_runner_passes_only_requested_metrics(stream_inputs, fake_metric, requested):
    sorted_name, data_root, out, calls = stream_inputs
    ephys.run_ephys_for_stream(sorted_name, "ecephys_1", "ProbeA", None, out, data_root, extra_metrics=requested)
    (kwargs,) = calls["continuous"]
    if requested:
        assert kwargs["extra_metrics"] == (fake_metric,)
    else:
        assert "extra_metrics" not in kwargs


def test_stream_runner_fails_before_extraction_when_metric_missing(stream_inputs, missing_metric):
    sorted_name, data_root, out, calls = stream_inputs
    with pytest.raises(RuntimeError, match="does not provide"):
        ephys.run_ephys_for_stream(
            sorted_name, "ecephys_1", "ProbeA", None, out, data_root, extra_metrics=("raw_activity",)
        )
    assert calls == {"continuous": [], "spikes": []}


def test_cli_parses_comma_separated_extra_metrics(tmp_path, monkeypatch):
    from aind_ibl_ephys_alignment_preprocessing import pipeline
    from aind_ibl_ephys_alignment_preprocessing.scripts import run

    configs = []
    monkeypatch.setattr(pipeline, "run_pipeline", configs.append)
    argv = ["aind-ibl-preprocess", "--data-root", str(tmp_path), "--results-root", str(tmp_path)]
    argv += ["--neuroglancer", "ng.json", "--manifest", "manifest.csv"]
    monkeypatch.setattr(sys, "argv", [*argv, "--extra-metrics", " raw_activity, "])
    run.main()
    monkeypatch.setattr(sys, "argv", argv)
    run.main()
    assert [config.extra_metrics for config in configs] == [("raw_activity",), ()]


@pytest.mark.parametrize("available", [True, False])
def test_preflight_reports_metric_availability(tmp_path, request, available):
    from aind_ibl_ephys_alignment_preprocessing.validation import PipelineValidator

    request.getfixturevalue("fake_metric" if available else "missing_metric")
    validator = PipelineValidator(_config(tmp_path, extra_metrics=("raw_activity",)), skip_resource_checks=True)
    validator.validate_inputs()
    (result,) = [r for r in validator.results if r.item == "extra_metrics"]
    assert result.passed is available


def test_preflight_ignores_metrics_when_ephys_skipped(tmp_path, missing_metric):
    from aind_ibl_ephys_alignment_preprocessing.validation import PipelineValidator

    config = _config(tmp_path, extra_metrics=("raw_activity",), skip_ephys=True)
    validator = PipelineValidator(config, skip_resource_checks=True)
    validator.validate_inputs()
    assert not [r for r in validator.results if r.item == "extra_metrics"]
