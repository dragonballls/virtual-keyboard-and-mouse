from knowledge_store import list_references, load_reference_context, save_reference
from recorder import app_data_dir


def test_only_saved_notes_become_local_knowledge(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert list_references() == []
    save_reference("Demo", "recording", "The UI changed after a click.")
    refs = list_references()
    assert len(refs) == 1
    assert refs[0]["user_approved"] is True
    assert "The UI changed" in load_reference_context()


def test_knowledge_context_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    save_reference("Long", "video", "a" * 5000)
    assert len(load_reference_context(max_chars=250)) <= 250


def test_corrupt_knowledge_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    path = app_data_dir() / "knowledge" / "references.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken", encoding="utf-8")
    assert list_references() == []
    assert load_reference_context() == ""
