import copy
import json

import pytest


@pytest.fixture
def workflow_file(tmp_path):
    """Minimal API graph; no locally exported workflow or reference audio required."""
    path = tmp_path / "qwen3-workflow.json"
    path.write_text(json.dumps({
        "19": {"class_type": "LoadAudio", "inputs": {"audio": "original.wav"}},
        "31": {"class_type": "TDQwen3TTSVoiceClone", "inputs": {
            "text": "Original text", "language": "Chinese", "ref_text": "Reference",
            "ref_audio": ["19", 0],
        }},
    }), encoding="utf-8")
    return str(path)


def test_build_qwen3_td_tts_workflow_patches_nodes(workflow_file):
    from landppt.services.comfyui_tts_client import load_workflow_template, build_qwen3_td_tts_workflow

    template = load_workflow_template(workflow_file)
    original = copy.deepcopy(template)

    wf = build_qwen3_td_tts_workflow(
        template,
        text="你好，世界",
        ref_audio_filename="ref.wav",
        language="zh",
        ref_text="",
    )

    assert wf["19"]["inputs"]["audio"] == "ref.wav"
    assert wf["31"]["inputs"]["text"] == "你好，世界"
    assert wf["31"]["inputs"]["language"] == "Chinese"
    assert wf["31"]["inputs"]["ref_text"] == ""

    # Ensure the template is not mutated.
    assert template == original


def test_build_qwen3_td_tts_workflow_language_english(workflow_file):
    from landppt.services.comfyui_tts_client import load_workflow_template, build_qwen3_td_tts_workflow

    template = load_workflow_template(workflow_file)
    wf = build_qwen3_td_tts_workflow(
        template,
        text="Hello world",
        ref_audio_filename="ref.flac",
        language="en",
        ref_text="",
    )

    assert wf["31"]["inputs"]["language"] == "English"

