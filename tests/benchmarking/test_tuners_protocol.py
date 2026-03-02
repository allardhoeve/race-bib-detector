"""Tests for benchmarking.tuners.protocol (task-060)."""

from __future__ import annotations

import pytest


def test_tuner_result_round_trips():
    """TunerResult serialises to dict and back."""
    from benchmarking.tuners.protocol import TunerResult

    result = TunerResult(
        params={"FACE_DNN_CONFIDENCE_MIN": 0.3},
        metrics={"face_f1": 0.85, "face_precision": 0.80, "face_recall": 0.90},
    )
    data = result.model_dump()
    assert data["params"] == {"FACE_DNN_CONFIDENCE_MIN": 0.3}
    assert data["metrics"]["face_f1"] == 0.85

    restored = TunerResult.model_validate(data)
    assert restored == result


def test_tuner_result_rejects_missing_fields():
    """TunerResult without required fields raises ValidationError."""
    from benchmarking.tuners.protocol import TunerResult

    with pytest.raises(Exception):
        TunerResult(params={"a": 1})  # type: ignore[call-arg]

    with pytest.raises(Exception):
        TunerResult(metrics={"f1": 0.5})  # type: ignore[call-arg]


def test_grid_tuner_satisfies_protocol():
    """GridTuner is a structural subtype of the Tuner protocol."""
    from benchmarking.tuners.grid import GridTuner
    from benchmarking.tuners.protocol import Tuner

    # runtime_checkable protocol → isinstance check
    tuner = GridTuner(param_grid={"A": [1, 2]})
    assert isinstance(tuner, Tuner)
