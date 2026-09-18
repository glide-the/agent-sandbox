import asyncio
import json
import venv
from pathlib import Path

from sandbox.processors.music_runtime import ProcessResult
from sandbox.processors.music_utility_processor import (
    MusicListenProcessor,
    MusicScoreProcessor,
)
from sandbox.processors.yue2_processor import YuE2Processor
from sandbox.server.model.music import (
    MusicListenSubmission,
    MusicScoreSubmission,
    YuE2Submission,
)


def test_fake_yue_process_exercises_environment_and_publication(tmp_path):
    env = tmp_path / "fake-env"
    venv.EnvBuilder(with_pip=False).create(env)
    cwd = tmp_path / "YuE"
    scripts = cwd / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / "run_yue2.py"
    script.write_text(
        "import json, pathlib, sys\n"
        "args=sys.argv\n"
        "out=pathlib.Path(args[args.index('--output')+1])\n"
        "out.mkdir(parents=True)\n"
        "(out/'audio.flac').write_bytes(b'synthetic_fixture')\n"
        "(out/'run.json').write_text(json.dumps("
        "{'complete': True, 'synthetic_fixture': True, 'prefix': sys.prefix}))\n"
    )
    model = tmp_path / "model"
    vae = tmp_path / "vae"
    model.mkdir()
    vae.mkdir()
    processor = YuE2Processor(
        cwd=str(cwd),
        environment=str(env),
        task_root=str(tmp_path / "tasks"),
        model_path=str(model),
        vae_path=str(vae),
        timeout_seconds=10,
    )
    submission = YuE2Submission.model_validate(
        {
            "code_input": {"userId": "alice", "workflow_id": "wf"},
            "operation": "generate",
            "request": {"style": "pop", "lyrics": "hello", "seed": 7},
            "_service": {
                "task_id": "music_fake",
                "owner_id": "alice",
                "request_digest": "r",
                "execution_profile_digest": "p",
            },
        }
    )
    result = asyncio.run(processor(submission, "music_fake", {}))
    assert result["delivery_status"] == "ready"
    assert result["runtime"]["python"] == str(env / "bin" / "python")
    report = json.loads(Path(result["report"]).read_text())
    assert report["prefix"] == str(env)
    assert result["artifacts"][0]["sha256"]


def test_strip_chords_maps_to_upstream_positional_cli(tmp_path, monkeypatch):
    env = tmp_path / "fake-env"
    venv.EnvBuilder(with_pip=False).create(env)
    cwd = tmp_path / "YuE"
    (cwd / "scripts").mkdir(parents=True)
    (cwd / "scripts" / "abc_tools.py").write_text("")
    model = tmp_path / "model"
    vae = tmp_path / "vae"
    model.mkdir()
    vae.mkdir()
    source = tmp_path / "source.abc"
    source.write_text("X:1\nK:C\nCDEF")
    seen = {}

    async def fake_process(**kwargs):
        seen["argv"] = kwargs["argv"]
        output = Path(kwargs["argv"][5])
        output.write_text("X:1\nK:C\nCDEF")
        return ProcessResult(kwargs["argv"], 0, False, "", "")

    monkeypatch.setattr(
        "sandbox.processors.yue2_processor.run_model_process", fake_process
    )
    processor = YuE2Processor(
        cwd=str(cwd),
        environment=str(env),
        task_root=str(tmp_path / "tasks"),
        model_path=str(model),
        vae_path=str(vae),
    )
    submission = YuE2Submission.model_validate(
        {
            "code_input": {"userId": "alice", "workflow_id": "wf"},
            "operation": "score_check",
            "check": {
                "action": "strip_chords",
                "source": {"asset_id": "asset_source"},
                "voices": "Vocal",
            },
            "_service": {
                "task_id": "music_strip",
                "owner_id": "alice",
                "request_digest": "r",
                "execution_profile_digest": "p",
            },
        }
    )
    result = asyncio.run(
        processor(submission, "music_strip", {"score_source": str(source)})
    )
    assert seen["argv"][3] == "strip-chords"
    assert seen["argv"][4] == str(source)
    assert seen["argv"][6:] == ["--keep-voice", "Vocal"]
    assert result["outcome"] == "complete"


def test_music_score_processor_maps_to_abc_tools(tmp_path, monkeypatch):
    env = tmp_path / "fake-env"
    venv.EnvBuilder(with_pip=False).create(env)
    cwd = tmp_path / "yue2-music"
    (cwd / "scripts").mkdir(parents=True)
    (cwd / "scripts" / "abc_tools.py").write_text("")
    source = tmp_path / "source.abc"
    source.write_text("X:1\nK:C\nCDEF")
    seen = {}

    async def fake_process(**kwargs):
        seen["argv"] = kwargs["argv"]
        output = Path(kwargs["argv"][5])
        output.write_text("X:1\nK:C\nCDEF")
        return ProcessResult(kwargs["argv"], 0, False, "", "")

    monkeypatch.setattr(
        "sandbox.processors.music_utility_processor.run_model_process", fake_process
    )
    processor = MusicScoreProcessor(
        cwd=str(cwd),
        environment=str(env),
        task_root=str(tmp_path / "tasks"),
    )
    submission = MusicScoreSubmission.model_validate(
        {
            "code_input": {"userId": "alice", "workflow_id": "wf"},
            "operation": "score_check",
            "check": {
                "action": "strip_chords",
                "source": {"asset_id": "asset_source"},
                "voices": "Vocal",
            },
            "_service": {
                "task_id": "music_score",
                "owner_id": "alice",
                "request_digest": "r",
                "execution_profile_digest": "p",
            },
        }
    )
    result = asyncio.run(
        processor(submission, "music_score", {"score_source": str(source)})
    )
    assert seen["argv"][2].endswith("scripts/abc_tools.py")
    assert seen["argv"][3:] == [
        "strip-chords",
        str(source),
        str(tmp_path / "tasks" / "music_score" / "work" / "native" / "score.abc"),
        "--keep-voice",
        "Vocal",
    ]
    assert result["outcome"] == "complete"


def test_music_listen_processor_publishes_server_side_bundle(tmp_path):
    env = tmp_path / "fake-env"
    venv.EnvBuilder(with_pip=False).create(env)
    cwd = tmp_path / "yue2-music"
    scripts = cwd / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "listen.py").write_text(
        "import json, pathlib, sys\n"
        "out=pathlib.Path(sys.argv[sys.argv.index('--output')+1])\n"
        "out.mkdir(parents=True)\n"
        "(out/'index.html').write_text('<html>comparison</html>')\n"
        "(out/'manifest.json').write_text(json.dumps({'schema':'fixture'}))\n"
    )
    source_a = tmp_path / "source-a"
    source_b = tmp_path / "source-b"
    source_a.mkdir()
    source_b.mkdir()
    processor = MusicListenProcessor(
        cwd=str(cwd),
        environment=str(env),
        task_root=str(tmp_path / "tasks"),
        timeout_seconds=10,
    )
    submission = MusicListenSubmission.model_validate(
        {
            "code_input": {"userId": "alice", "workflow_id": "wf"},
            "operation": "listen",
            "source_task_ids": ["music_a", "music_b"],
            "_service": {
                "task_id": "music_listen",
                "owner_id": "alice",
                "request_digest": "r",
                "execution_profile_digest": "p",
            },
        }
    )
    result = asyncio.run(
        processor(
            submission,
            "music_listen",
            {"source_tasks": [str(source_a), str(source_b)]},
        )
    )
    assert result["outcome"] == "complete"
    assert {item["result_source_name"] for item in result["artifacts"]} == {
        "comparison",
        "comparison_bundle",
        "comparison_manifest",
    }
