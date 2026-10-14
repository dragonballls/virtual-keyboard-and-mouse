import json

import pytest

import video_learning
from video_learning import (
    MAX_FRAME_FILE_BYTES,
    MAX_RECORDING_EVENTS,
    MAX_RECORDING_FILE_BYTES,
    MAX_VIDEO_FRAMES,
    _sample_recording_frames,
    analyze_recording,
)


def _jpeg_bytes():
    return b"\xff\xd8" + b"test-jpeg-data" + b"\xff\xd9"


def test_recording_frame_sample_is_capped_at_six_and_handles_one_frame(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    for index in range(12):
        (frames / f"frame-{index:04d}.jpg").write_bytes(_jpeg_bytes())

    images, offsets = _sample_recording_frames(tmp_path, max_frames=100)
    assert len(images) == MAX_VIDEO_FRAMES
    assert len(offsets) == len(images)

    one_image, one_offset = _sample_recording_frames(tmp_path, max_frames=1)
    assert len(one_image) == 1
    assert one_offset == [3]


def test_oversized_and_invalid_screenshot_files_are_skipped(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "frame-0000.jpg").write_bytes(b"not a JPEG")
    huge = frames / "frame-0001.jpg"
    with huge.open("wb") as stream:
        stream.truncate(MAX_FRAME_FILE_BYTES + 1)

    images, offsets = _sample_recording_frames(tmp_path)
    assert images == []
    assert offsets == []


def test_analyze_recording_sends_at_most_48_allowlisted_events_and_six_frames(tmp_path, monkeypatch):
    frames = tmp_path / "frames"
    frames.mkdir()
    for index in range(10):
        (frames / f"frame-{index:04d}.jpg").write_bytes(_jpeg_bytes())
    actions = [
        {"type": "key_down", "key": "w", "t": float(i), "untrusted": "must not be sent"}
        for i in range(125)
    ]
    (tmp_path / "recording.json").write_text(json.dumps({
        "duration_seconds": 125,
        "action_count": len(actions),
        "actions": actions,
    }), encoding="utf-8")

    captured = {}
    def fake_provider(provider, key, model, system, prompt, images_b64=()):
        captured.update(provider=provider, prompt=prompt, images=list(images_b64))
        return "review complete"

    monkeypatch.setattr(video_learning, "ask_provider", fake_provider)
    result = analyze_recording(str(tmp_path), "Gemini", "test-key", "test-model")
    assert result == "review complete"
    assert len(captured["images"]) == MAX_VIDEO_FRAMES
    sample_text = captured["prompt"].split("Sampled events: ", 1)[1].split("\nAttached screenshots:", 1)[0]
    sampled = json.loads(sample_text)
    assert len(sampled) == MAX_RECORDING_EVENTS
    assert all(set(event) <= {"type", "t", "key", "button", "x", "y"} for event in sampled)
    assert "untrusted" not in captured["prompt"]
    assert r"\n" not in captured["prompt"]


def test_invalid_event_values_are_excluded_from_cloud_prompt(tmp_path, monkeypatch):
    (tmp_path / "recording.json").write_text(json.dumps({
        "actions": [
            {"type": "key_down", "key": "password", "t": 0},
            {"type": "key_down", "key": ["not", "a", "key"], "t": 0},
            {"type": "mouse_click", "button": ["left"], "x": 1, "y": 2},
            {"type": "key_down", "key": "w", "t": "not-a-time"},
            {"type": "mouse_click", "button": "left", "x": -1, "y": 2},
            {"type": "key_up", "key": "w", "t": 1},
        ],
    }), encoding="utf-8")

    captured = {}
    def fake_provider(provider, key, model, system, prompt, images_b64=()):
        captured["prompt"] = prompt
        return "review complete"

    monkeypatch.setattr(video_learning, "ask_provider", fake_provider)
    analyze_recording(str(tmp_path), "Gemini", "test-key", "test-model")
    sampled_text = captured["prompt"].split("Sampled events: ", 1)[1].split("\nAttached screenshots:", 1)[0]
    sampled = json.loads(sampled_text)
    assert sampled == [
        {"type": "key_down", "key": "w"},
        {"type": "key_up", "key": "w", "t": 1.0},
    ]


def test_non_object_or_corrupt_recordings_fail_closed(tmp_path):
    file = tmp_path / "recording.json"
    file.write_text("[]", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unsupported format"):
        analyze_recording(str(tmp_path), "Gemini", "key", "model")

    file.write_text("{broken", encoding="utf-8")
    with pytest.raises(RuntimeError, match="valid UTF-8 JSON"):
        analyze_recording(str(tmp_path), "Gemini", "key", "model")


def test_oversized_recording_metadata_is_rejected(tmp_path):
    file = tmp_path / "recording.json"
    with file.open("wb") as stream:
        stream.truncate(MAX_RECORDING_FILE_BYTES + 1)
    with pytest.raises(RuntimeError, match="12 MB limit"):
        analyze_recording(str(tmp_path), "Gemini", "key", "model")


def test_empty_recording_without_screenshots_is_rejected(tmp_path):
    (tmp_path / "recording.json").write_text(json.dumps({"actions": []}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="no usable input events or screenshots"):
        analyze_recording(str(tmp_path), "Gemini", "key", "model")
