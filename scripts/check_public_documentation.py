"""Check current public documentation locally; never operate services or workflows."""
import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

from scripts.check_repository_layout import check_layout

ROOT = Path(__file__).resolve().parents[1]
CONFIG = "configs/documentation-checks.json"
LINK = re.compile(r"!?\[[^\]\n]+\]\(([^)\n]+)\)")
FENCE = re.compile(r"(?ms)^```[^\n]*\n.*?^```[^\n]*$")


def local_target(root, document, target):
    if PureWindowsPath(target).drive or "\\" in target:
        raise ValueError("absolute or nonportable local link")
    value = urlsplit(target)
    if value.scheme in {"https", "http", "mailto"}:
        return None  # External links are not fetched or declared verified.
    if value.scheme or value.netloc or value.path.startswith("/"):
        raise ValueError("absolute or unsupported local link")
    path = (document.parent / unquote(value.path)).resolve() if value.path else document.resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("local link escapes repository")
    return path


def check_document(root, relative, private_roots):
    root = Path(root).resolve()
    document = root / relative
    issues, links = [], 0
    try:
        text = document.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {"path": relative, "local_links": 0, "issues": ["document missing or not UTF-8"]}
    if any(ord(c) < 32 and c not in "\n\r\t" for c in text):
        issues.append("unexpected text control character")
    if not any(line.startswith("# ") for line in text.splitlines()):
        # GitHub templates use native issue/PR subheadings.
        if not relative.startswith(".github/") or not any(line.startswith("## ") for line in text.splitlines()):
            issues.append("missing document heading")
    for match in LINK.finditer(FENCE.sub("", text)):
        target = match.group(1).strip().removeprefix("<").removesuffix(">")
        try:
            path = local_target(root, document, target)
            if path is None:
                continue
            links += 1
            if any(path.is_relative_to(root / p) for p in private_roots):
                raise ValueError("public entry links directly to private runtime/archive data")
            if not path.exists():
                raise ValueError("local link target missing")
        except (ValueError, OSError) as exc:
            issues.append(f"{target}: {exc}")
    return {"path": relative, "local_links": links, "issues": issues}


def check_cli_help(specifications):
    results = []
    allowed = {"modelcrew", "modelcrew.dsh_integration", "modelcrew.workflow_mcp"}
    for spec in specifications:
        if spec["module"] not in allowed or spec["args"] not in (["--help"], ["doctor", "--help"], ["environment", "--help"], ["render", "--help"], ["install", "--help"]):
            raise ValueError("only explicit read-only help probes are permitted")
        command = [sys.executable, "-m", spec["module"], *spec["args"]]
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", timeout=60)
        missing = [token for token in spec["expected"] if token not in result.stdout]
        results.append({"module": spec["module"], "args": spec["args"],
                        "returncode": result.returncode, "missing_help_tokens": missing,
                        "status": "passed" if result.returncode == 0 and not missing else "failed"})
    return results


def check_public_documentation(*, check_cli=False):
    config = json.loads((ROOT / CONFIG).read_text(encoding="utf-8"))
    if config["schema_version"] != "1.0.0":
        raise ValueError("unknown documentation configuration version")
    documents = [check_document(ROOT, n, config["private_roots"]) for n in config["documents"]]
    record = json.loads((ROOT / config["archive_record"]).read_text(encoding="utf-8"))
    preservation = record["preservation"]
    original = ROOT / preservation["old_readme"]
    archive_matches = hashlib.sha256(original.read_bytes()).hexdigest() == preservation["old_readme_sha256"]
    g_matches = hashlib.sha256((ROOT / "docs/release/g-stage-user-acceptance-20261119.json").read_bytes()).hexdigest() == preservation["G_acceptance_sha256"]
    raw = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    names = [n for n in raw.decode("utf-8").split("\0") if n and (ROOT / n).exists()]
    policy = json.loads((ROOT / "configs/repository-layout.json").read_text(encoding="utf-8"))
    names += [p.name + "/" for p in ROOT.iterdir() if p.is_dir() and (p.name.startswith("stage-") or p.name in policy["transitional_roots"])]
    layout = check_layout(names, policy, final=True)
    cli = check_cli_help(config["cli_help"]) if check_cli else []
    passed = (all(not d["issues"] for d in documents) and archive_matches and g_matches
              and layout["status"] == "passed" and all(r["status"] == "passed" for r in cli))
    return {"status": "passed" if passed else "failed", "scope": "current user/contributor documentation only",
            "documents": documents, "local_links": sum(d["local_links"] for d in documents),
            "old_readme_bytes_preserved": archive_matches, "G_acceptance_bytes_preserved": g_matches,
            "layout": layout, "cli_help": cli, "cli_help_executed": check_cli,
            "external_links_checked": False, "new_device_verified": False,
            "model_called": False, "business_database_accessed": False, "public_release": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-cli", action="store_true", help="Also run explicitly allowed --help probes; requires workflow dependencies")
    parser.add_argument("--output", type=Path, help="New report path; existing output is never overwritten")
    args = parser.parse_args()
    try:
        result = check_public_documentation(check_cli=args.check_cli)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "passed" else 1
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
