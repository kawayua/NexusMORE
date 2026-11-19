"""Current documentation checks need no credentials, research inputs or live host."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_public_documentation as docs


def test_current_documentation_and_preservation():
    report = docs.check_public_documentation()
    assert report["status"] == "passed"
    assert report["local_links"] > 0
    assert report["old_readme_bytes_preserved"]
    assert report["G_acceptance_bytes_preserved"]
    assert not report["cli_help_executed"]
    assert not report["model_called"]
    assert not report["business_database_accessed"]
    assert not report["new_device_verified"]
    assert not report["public_release"]


def document(root, text):
    path = root / "docs/guide.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_link_is_reported(tmp_path):
    document(tmp_path, "# Guide\n\n[missing](not-there.md)\n")
    result = docs.check_document(tmp_path, "docs/guide.md", [])
    assert result["local_links"] == 1
    assert "target missing" in result["issues"][0]


def test_private_attachment_link_is_rejected_even_if_present(tmp_path):
    private = tmp_path / "runs/input.json"
    private.parent.mkdir()
    private.write_text("{}")
    document(tmp_path, "# Guide\n\n[private](../runs/input.json)\n")
    result = docs.check_document(tmp_path, "docs/guide.md", ["runs"])
    assert "private runtime/archive" in result["issues"][0]


def test_code_samples_are_not_interpreted_as_live_links(tmp_path):
    document(tmp_path, "# Guide\n\n```text\n[example](not-there.md)\n```\n")
    result = docs.check_document(tmp_path, "docs/guide.md", [])
    assert result["local_links"] == 0 and result["issues"] == []


def test_local_links_count_and_external_links_are_not_fetched(tmp_path):
    document(tmp_path, "# Guide\n\n[local](guide.md) [external](https://example.invalid/)\n")
    result = docs.check_document(tmp_path, "docs/guide.md", [])
    assert result["local_links"] == 1 and result["issues"] == []


def test_control_character_in_sample_is_reported(tmp_path):
    document(tmp_path, "# Guide\n\n```text\ninvalid\vpath\n```\n")
    assert "control character" in docs.check_document(tmp_path, "docs/guide.md", [])["issues"][0]


@pytest.mark.parametrize("target", ["../../outside.md", "/tmp/example.md", "C:/private/file.md", "C:relative.md", "file:///private/file.md", "//remote/share", r"..\private.md"])
def test_local_links_cannot_escape_or_depend_on_machine_paths(tmp_path, target):
    path = document(tmp_path, "# Guide\n")
    with pytest.raises(ValueError):
        docs.local_target(tmp_path, path, target)


def test_only_help_probes_can_be_executed():
    with pytest.raises(ValueError, match="read-only help"):
        docs.check_cli_help([{"module": "modelcrew.workflow_mcp", "args": ["migrate"], "expected": []}])


def test_help_parameter_drift_is_reported(monkeypatch):
    monkeypatch.setattr(docs.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="usage: example"))
    result = docs.check_cli_help([{"module": "modelcrew", "args": ["doctor", "--help"], "expected": ["--services"]}])
    assert result[0]["status"] == "failed"
    assert result[0]["missing_help_tokens"] == ["--services"]
