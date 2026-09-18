import math

import pytest
from pydantic import ValidationError

from sandbox.server.model.music import ResourceRef, parse_music_submission


def request_payload(**overrides):
    value = {
        "code_input": {"userId": "alice", "workflow_id": "wf-1"},
        "operation": "generate",
        "request": {
            "id": "song-1",
            "style": "piano pop",
            "lyrics": "[Verse]\nhello",
            "cot": "full",
            "seed": 831001,
        },
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize("seed", [-1, 2**63, True])
def test_seed_is_strict_and_bounded(seed):
    value = request_payload()
    value["request"]["seed"] = seed
    with pytest.raises(ValidationError):
        parse_music_submission("yue2_task", value)


@pytest.mark.parametrize("scale", [math.nan, math.inf, 21])
def test_cfg_scale_is_finite_and_bounded(scale):
    value = request_payload()
    value["request"]["cfg_scale"] = scale
    with pytest.raises(ValidationError):
        parse_music_submission("yue2_task", value)


def test_unknown_and_cross_operation_fields_are_rejected():
    value = request_payload(source_task_id="music_other")
    with pytest.raises(ValidationError):
        parse_music_submission("yue2_task", value)
    value = request_payload()
    value["request"]["unknown"] = 1
    with pytest.raises(ValidationError):
        parse_music_submission("yue2_task", value)
    with pytest.raises(ValidationError):
        parse_music_submission("sheetsage2_task", value)


def test_abc_rules_and_resource_shape():
    value = request_payload()
    value["request"].update({"cot": "melody", "abc": 'X:1\n"C" CDEF'})
    with pytest.raises(ValidationError):
        parse_music_submission("yue2_task", value)
    value = request_payload(abc_source={"asset_id": "asset_abc"})
    value["request"]["abc"] = "X:1\nK:C\nCDEF"
    with pytest.raises(ValidationError):
        parse_music_submission("yue2_task", value)
    with pytest.raises(ValidationError):
        ResourceRef(asset_id="a", task_id="t", result_source_name="audio")


def test_plan_matches_upstream_abc_and_cot_rules():
    value = request_payload(operation="plan")
    value["request"]["abc"] = "X:1\nK:C\nCDEF"
    assert parse_music_submission("yue2_task", value).operation == "plan"
    value["request"]["cot"] = "off"
    with pytest.raises(ValidationError):
        parse_music_submission("yue2_task", value)
