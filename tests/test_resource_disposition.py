"""Release intake coverage must not turn source matching into a license grant."""
import hashlib
import pytest
from scripts.build_resource_disposition import build_disposition


def inputs(tmp_path):
    raw = b"official replacement"
    (tmp_path / "docx").mkdir()
    (tmp_path / "docx/tool.py").write_bytes(raw)
    original = {"source": "modeling", "path": "tools/docx/tool.py", "sha256": "a" * 64,
                "bytes": 12, "status": "restricted"}
    review = {"files": [{"id": "DOC-001", "local_sha256": "a" * 64,
                         "local_relative_path": original["path"],
                         "official_replacement_path": "skills/docx/tool.py"}]}
    manifest = {"license": "Apache-2.0", "source_repository": "official", "commit": "fixed",
                "files": [{"path": "docx/tool.py", "sha256": hashlib.sha256(raw).hexdigest()}]}
    return original, review, manifest


def test_replacement_preserves_mirrored_source_identity_without_grant(tmp_path):
    original, review, manifest = inputs(tmp_path)
    mirrored = dict(original, path="nested/tools/docx/tool.py")
    report = build_disposition({"files": [original, mirrored]}, review, manifest, tmp_path)
    assert len(report["files"]) == 2
    assert report["summary"] == {"authorized_replacement": 2}
    assert all(not row["source_redistribution_approved"] for row in report["files"])
    assert all(row["source_sha256"] == "a" * 64 for row in report["files"])
    assert all(row["replacement"]["sha256"] != "a" * 64 for row in report["files"])


def test_changed_official_file_is_rejected(tmp_path):
    original, review, manifest = inputs(tmp_path)
    (tmp_path / "docx/tool.py").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        build_disposition({"files": [original]}, review, manifest, tmp_path)


def test_unknown_restricted_source_and_duplicate_are_rejected(tmp_path):
    original, review, manifest = inputs(tmp_path)
    with pytest.raises(ValueError, match="missing prior review"):
        build_disposition({"files": [original]}, {"files": []}, manifest, tmp_path)
    with pytest.raises(ValueError, match="Duplicate source identity"):
        build_disposition({"files": [original, original]}, review, manifest, tmp_path)


def test_unlicensed_knowledge_stays_pending_and_maintenance_is_tracked(tmp_path):
    original, review, manifest = inputs(tmp_path)
    knowledge = dict(original, path="assets/algorithm.md", status="review_required")
    maintenance = dict(knowledge, path=".github/workflows/upstream.yml")
    report = build_disposition({"files": [knowledge, maintenance]}, review, manifest, tmp_path)
    assert [row["disposition"] for row in report["files"]] == ["pending", "not_runtime_resource"]
    assert not any(row["source_redistribution_approved"] for row in report["files"])
