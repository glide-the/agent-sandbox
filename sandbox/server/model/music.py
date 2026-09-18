"""Strict request models for the two model-bound music tasks."""

from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MusicCodeInput(StrictModel):
    userId: str = Field(min_length=1, max_length=200)
    workflow_id: str = Field(min_length=1, max_length=200)


class ResourceRef(StrictModel):
    asset_id: str | None = None
    task_id: str | None = None
    result_source_name: str | None = None

    @model_validator(mode="after")
    def validate_reference(self):
        uploaded = bool(self.asset_id)
        task_output = bool(self.task_id and self.result_source_name)
        if uploaded == task_output:
            raise ValueError(
                "provide either asset_id or task_id with result_source_name"
            )
        if bool(self.task_id) != bool(self.result_source_name):
            raise ValueError("task_id and result_source_name must be provided together")
        return self


_CHORD_SYMBOL = re.compile(
    r'"[A-G](?:#|b)?(?:m|min|maj|dim|aug|sus|add)?(?:\d+)?(?:/[A-G](?:#|b)?)?"'
)


class NativeSongRequest(StrictModel):
    id: str = "song"
    style: str
    tags: str | None = None
    lyrics: str
    cot: Literal["full", "melody", "off"] = "full"
    seed: StrictInt = 831001
    abc: str | None = None
    cfg_scale: float | None = None

    @model_validator(mode="after")
    def validate_native_contract(self):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,179}", self.id):
            raise ValueError("id has an invalid format")
        if not 0 <= self.seed < 2**63:
            raise ValueError("seed must be an integer in [0, 2**63)")
        if self.cfg_scale is not None and (
            not math.isfinite(self.cfg_scale) or not 0 <= self.cfg_scale <= 20
        ):
            raise ValueError("cfg_scale must be finite and in [0, 20]")
        if self.tags is not None:
            if self.style and self.tags != self.style:
                raise ValueError("style and tags must match when both are supplied")
            self.style = self.tags
            self.tags = None
        if self.abc is not None and not self.abc.strip():
            raise ValueError("abc must be non-empty when supplied")
        if self.cot == "off" and self.abc is not None:
            raise ValueError("cot=off does not accept ABC input")
        if self.cot == "melody" and self.abc and _CHORD_SYMBOL.search(self.abc):
            raise ValueError("cot=melody requires ABC without chord symbols")
        return self


class TranscriptionOptions(StrictModel):
    task: Literal["full", "melody-full", "melody-vocal"] = "full"
    max_seconds: float | None = Field(default=None, gt=0)


class ScoreCheckOptions(StrictModel):
    action: Literal["inspect", "strip_chords", "compare"]
    source: ResourceRef
    after: ResourceRef | None = None
    voices: Literal["both", "Vocal", "Ins"] = "both"
    allow_tempo_change: bool = False

    @model_validator(mode="after")
    def validate_compare(self):
        if self.action == "compare" and self.after is None:
            raise ValueError("compare requires an after resource")
        if self.action != "compare" and self.after is not None:
            raise ValueError("after is only valid for compare")
        return self


class ServiceMetadata(StrictModel):
    task_id: str
    owner_id: str
    request_digest: str
    execution_profile_digest: str
    resolved_resources: dict[str, str | list[str]] = Field(default_factory=dict)


class SubmissionBase(StrictModel):
    code_input: MusicCodeInput
    service: ServiceMetadata | None = Field(default=None, alias="_service")


class YuE2Submission(SubmissionBase):
    operation: Literal["generate", "plan", "all_modes", "decode", "score_check"]
    request: NativeSongRequest | None = None
    abc_source: ResourceRef | None = None
    source_task_id: str | None = None
    check: ScoreCheckOptions | None = None

    @model_validator(mode="after")
    def validate_operation(self):
        if self.operation in {"generate", "plan", "all_modes"} and self.request is None:
            raise ValueError(f"{self.operation} requires request")
        if self.operation == "decode" and not self.source_task_id:
            raise ValueError("decode requires source_task_id")
        if self.operation == "score_check" and self.check is None:
            raise ValueError("score_check requires check")
        if (
            self.request
            and self.request.abc is not None
            and self.abc_source is not None
        ):
            raise ValueError("request.abc and abc_source are mutually exclusive")
        if self.request and self.request.cot == "off" and self.abc_source is not None:
            raise ValueError("cot=off does not accept ABC input")
        if self.operation not in {"generate", "plan"} and self.abc_source is not None:
            raise ValueError("abc_source is only valid for generate or plan")
        if self.operation == "all_modes" and self.request and self.request.abc:
            raise ValueError("all_modes only accepts text request input")
        if self.operation == "plan" and self.request and self.request.cot == "off":
            raise ValueError("plan does not support cot=off")
        if self.operation == "decode" and any(
            (self.request, self.abc_source, self.check)
        ):
            raise ValueError("decode only accepts source_task_id")
        if self.operation == "score_check" and any(
            (self.request, self.abc_source, self.source_task_id)
        ):
            raise ValueError("score_check only accepts check options")
        if self.operation in {"generate", "plan", "all_modes"} and any(
            (self.source_task_id, self.check)
        ):
            raise ValueError(f"{self.operation} contains fields for another operation")
        return self


class SheetSage2Submission(SubmissionBase):
    operation: Literal["transcribe"]
    audio_asset_id: str = Field(min_length=1)
    transcription: TranscriptionOptions = Field(default_factory=TranscriptionOptions)


class MusicScoreSubmission(SubmissionBase):
    operation: Literal["score_check"]
    check: ScoreCheckOptions


class MusicListenSubmission(SubmissionBase):
    operation: Literal["listen"]
    source_task_ids: list[str] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_sources(self):
        if any(not task_id.strip() for task_id in self.source_task_ids):
            raise ValueError("source task ids must not be empty")
        if len(set(self.source_task_ids)) != len(self.source_task_ids):
            raise ValueError("source task ids must be unique")
        return self


MUSIC_TASK_MODELS = {
    "yue2_task": YuE2Submission,
    "sheetsage2_task": SheetSage2Submission,
    "music_score_task": MusicScoreSubmission,
    "music_listen_task": MusicListenSubmission,
}


def parse_music_submission(task_name: str, value: dict):
    model = MUSIC_TASK_MODELS.get(task_name)
    if model is None:
        raise ValueError(f"unsupported music task: {task_name}")
    return model.model_validate(value)
