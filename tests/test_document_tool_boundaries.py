"""NexusMORE adapter treats missing outputs, timeouts and tampering as failures."""
import json
import subprocess
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from modelcrew import document_tools as tools


@pytest.mark.parametrize("failure", ["timeout", "nonzero", "no_output", "invalid_json", "changed_input"])
def test_failed_tool_cannot_publish_success_receipt(tmp_path, monkeypatch, failure):
    source = tmp_path / "attachment.pdf"
    source.write_bytes(b"synthetic-input-not-a-real-pdf")
    before = tools.sha(source)
    output = tmp_path / "check"
    def execute(command, **options):
        staged = output / "input.pdf"
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 0.01, output=b"partial", stderr=b"interrupted")
        if failure == "changed_input":
            staged.write_bytes(b"changed")
        if failure in ("nonzero", "changed_input"):
            (output / "fields.json").write_text("[]", encoding="utf-8")
        if failure == "invalid_json":
            (output / "fields.json").write_text("not-json", encoding="utf-8")
        return subprocess.CompletedProcess(command, 9 if failure == "nonzero" else 0, b"log", b"error")
    monkeypatch.setattr(tools.subprocess, "run", execute)
    result = tools.run("pdf_fields", source, output, timeout=0.01)
    assert result["status"] in ("failed", "timeout")
    assert tools.sha(source) == before
    assert json.loads((output / "receipt.json").read_text(encoding="utf-8"))["status"] == result["status"]


def test_official_comment_definitions_roundtrip_xml_and_invalid_reply_keeps_input(tmp_path):
    pytest.importorskip("defusedxml", reason="Install the declared documents dependencies for official comment validation")
    tools.verify_bundle()
    word = tmp_path / "word"
    word.mkdir()
    document = word / "document.xml"
    document.write_text('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>', encoding="utf-8")
    script = Path(tools.BASE) / "upstream/docx/scripts/comment.py"
    text, author = "核对 <边界> & 单位", '研究者 & "甲"'
    completed = subprocess.run([sys.executable, str(script), str(tmp_path), text,
                                "--author", author, "--id", "42"], capture_output=True, timeout=20)
    assert completed.returncode == 0, completed.stderr
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    comment = ET.parse(word / "comments.xml").getroot().find(ns + "comment")
    assert comment.attrib[ns + "author"] == author
    assert "".join(comment.itertext()).strip() == text
    before = {p.name: tools.sha(p) for p in word.iterdir()}
    rejected = subprocess.run([sys.executable, str(script), str(tmp_path), "reply", "--parent", "9999"],
                              capture_output=True, timeout=20)
    assert rejected.returncode != 0
    assert {p.name: tools.sha(p) for p in word.iterdir()} == before


@pytest.mark.parametrize("tool", ["xlsx_recalculate", "latex_to_docx", "accept_changes"])
def test_unregistered_execution_is_explicitly_rejected_without_creating_output(tmp_path, tool):
    output = tmp_path / "unsupported"
    with pytest.raises(ValueError, match="Unknown document tool"):
        tools.run(tool, tmp_path / "missing-input", output)
    assert not output.exists()
