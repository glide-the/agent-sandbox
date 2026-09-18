import asyncio
import json
import venv
from pathlib import Path

from sandbox.processors.music_runtime import ProcessResult
from sandbox.processors.yue2_processor import YuE2Processor
from sandbox.server.model.music import YuE2Submission


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
