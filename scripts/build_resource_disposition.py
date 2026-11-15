"""Build a source-by-source release review ledger; never grants source rights."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_disposition(inventory, review, manifest, tool_root):
    official = {item["path"]: item for item in manifest["files"]}
    rows = []
    seen = set()
    for index, item in enumerate(inventory["files"], 1):
        identity = (item["source"], item["path"])
        if identity in seen:
            raise ValueError("Duplicate source identity")
        seen.add(identity)
        row = {"id": f"resource-{index:03d}", "source": item["source"],
               "source_path": item["path"], "source_sha256": item["sha256"],
               "bytes": item["bytes"], "source_license_status": item["status"],
               "source_redistribution_approved": False, "disposition": "pending",
               "runtime_role": "knowledge_or_tool_review_required", "replacement": None,
               "next_action": "F5: establish permission or independently replace; F2/F6: integrate and verify"}
        if item["status"] == "restricted":
            matches = [entry for entry in review["files"] if entry["local_sha256"] == item["sha256"]]
            exact = [entry for entry in matches if entry["local_relative_path"] == item["path"]]
            if exact:
                matches = exact
            if not matches:
                raise ValueError("Restricted file missing prior review")
            row["review_ids"] = [entry["id"] for entry in matches]
            replacements = {entry["official_replacement_path"] for entry in matches}
            if None not in replacements:
                # Select an explicit corresponding tool path, retaining all evidence IDs.
                suffix = item["path"].split("tools/", 1)[-1]
                candidates = sorted(replacements)
                selected = next((path for path in candidates if path == "skills/" + suffix), candidates[0])
                relative = selected.removeprefix("skills/")
                entry = official[relative]
                target = tool_root / relative
                if digest(target) != entry["sha256"]:
                    raise ValueError("Official replacement hash mismatch")
                row.update(disposition="authorized_replacement", runtime_role="document_tool",
                           replacement={"package_path": "src/modelcrew/resources/document-tools/upstream/" + relative,
                                        "sha256": entry["sha256"], "license": manifest["license"],
                                        "repository": manifest["source_repository"], "commit": manifest["commit"]},
                           next_action="F5: retain upstream notices; F6: verify routing and execution coverage")
            else:
                row["runtime_role"] = "document_tool_extension"
                row["next_action"] = "F5: authorize or independently replace local extension; do not copy restricted source"
        elif (item["source"] == "modeling" and
              (item["path"].startswith((".github/", "imgs/", "tests/", "dsh-plugin/"))
               and not item["path"].startswith("dsh-plugin/math-modeling-agent/skills/"))):
            row.update(disposition="not_runtime_resource", runtime_role="upstream_maintenance_demo_or_host_adapter",
                       next_action="Retain inventory identity; exclude from runtime; no permission inferred for public archive")
        elif item["source"] == "modeling" and item["path"] in {
                ".gitignore", "CHANGELOG.md", "VERSION", "scripts/sync_dsh_plugin.py", "tools/update_star_history.py"}:
            row.update(disposition="not_runtime_resource", runtime_role="upstream_maintenance",
                       next_action="Exclude from runtime; preserve source identity without redistribution approval")
        rows.append(row)
    return {"schema_version": "1.0.0", "status": "initial_review_not_release_approval",
            "source_redistribution_approved": False, "full_knowledge_builtin": False,
            "scope": "All files in the frozen 251-file intake, including nested copies; not all project dependencies",
            "summary": dict(Counter(row["disposition"] for row in rows)), "files": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / "src/modelcrew/resources/document-tools/manifest.json"
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = build_disposition(load(args.inventory), load(args.review), load(manifest_path),
                               manifest_path.parent / "upstream")
    result["evidence"] = [{"role": role, "sha256": digest(path)} for role, path in
                          [("frozen_intake", args.inventory), ("prior_tool_review", args.review),
                           ("official_tool_manifest", manifest_path)]]
    output = args.output.resolve()
    if not output.is_relative_to(root):
        parser.error("Output must remain inside the workspace")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"files": len(result["files"]), "summary": result["summary"]}))


if __name__ == "__main__":
    main()
