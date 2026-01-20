#!/usr/bin/env python3
"""Append a structured finding entry to the shared ledgers.

Usage:
    python add_finding.py --type bug --entry '{"title": "Memory leak", ...}' --agent claude-3.5-sonnet

Optional flags:
    --entry-id FIN-001         # roadmap entry id (stored as entry_id)
    --file-path runs/CORE-001/run-2026-01-19-001/findings.json
"""

import json
import argparse
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
FINDINGS_DIR = BASE_DIR.parent / "findings"

TYPE_FILE_OVERRIDES = {
    "bug": FINDINGS_DIR / "bugs.json",
    "strength": FINDINGS_DIR / "strengths.json",
    "improvement": FINDINGS_DIR / "improvements.json",
}

TYPE_PREFIXES = {
    "bug": "BUG",
    "security": "SEC",
    "performance": "PERF",
    "reliability": "REL",
    "silent_failure": "SIL",
    "log_issue": "LOG",
    "observability": "OBS",
    "dx": "DX",
    "improvement": "IMP",
    "documentation": "DOC",
    "feature_request": "FRQ",
    "strength": "STR",
}


def generate_id(entry_type: str, existing_ids: list[str]) -> str:
    prefix = TYPE_PREFIXES.get(entry_type, "FND")
    max_num = 0
    for eid in existing_ids:
        if eid.startswith(prefix + "-"):
            try:
                num = int(eid.split("-")[1])
                if num > max_num:
                    max_num = num
            except (ValueError, IndexError):
                pass
    new_num = max_num + 1
    return f"{prefix}-{new_num:03d}"


def load_findings(filepath: Path) -> dict:
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"metadata": {}, "items": []}


def save_findings(filepath: Path, data: dict) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def append_entry(entry: dict, file_path: Path) -> dict:
    data = load_findings(file_path)
    collection_key = "items" if "items" in data else "findings"
    findings_list = data.setdefault(collection_key, [])
    existing_ids = [e.get("id", "") for e in findings_list]

    generated_id = generate_id(entry["type"], existing_ids)
    entry["id"] = generated_id
    findings_list.append(deepcopy(entry))
    save_findings(file_path, data)
    return {"id": generated_id, "file": str(file_path.resolve())}


def resolve_destination(entry_type: str, override: str | None) -> Path:
    if override:
        return Path(override)
    if entry_type in TYPE_FILE_OVERRIDES:
        return TYPE_FILE_OVERRIDES[entry_type]
    raise ValueError(
        f"No default ledger for type '{entry_type}'. Provide --file-path explicitly."
    )


def add_entry(
    entry_type: str,
    entry_json: str,
    agent: str,
    destination_file: Path,
    entry_id: str | None = None,
) -> dict:
    entry = json.loads(entry_json)
    entry.setdefault("type", entry_type)
    entry["agent"] = agent
    entry["created_at"] = datetime.utcnow().isoformat() + "Z"
    if entry_id:
        entry["entry_id"] = entry_id

    result = append_entry(entry, destination_file)

    return {
        "id": result["id"],
        "status": "success",
        "files": [result["file"]],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Append a structured finding entry to a JSON ledger"
    )
    parser.add_argument(
        "--entry",
        "-e",
        required=True,
        help="JSON string of the entry to add",
    )
    parser.add_argument(
        "--agent",
        "-a",
        required=True,
        help="Agent model identifier",
    )
    parser.add_argument(
        "--type",
        "-t",
        required=True,
        choices=sorted(TYPE_PREFIXES.keys()),
        help="Finding type (see reporting schema)",
    )
    parser.add_argument(
        "--entry-id",
        help="Roadmap entry id to associate with this finding",
    )
    parser.add_argument(
        "--file-path",
        default=None,
        help="Override path to a findings ledger (default: bugs/strengths/improvements under findings/)",
    )

    args = parser.parse_args()

    try:
        destination = resolve_destination(args.type, args.file_path)
        result = add_entry(
            entry_type=args.type,
            entry_json=args.entry,
            agent=args.agent,
            destination_file=destination,
            entry_id=args.entry_id,
        )
        print(json.dumps(result, indent=2))
        targets = ", ".join(result["files"])
        print(f"\nEntry {result['id']} recorded in: {targets}")
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON entry: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
