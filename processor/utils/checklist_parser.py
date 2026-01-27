"""
Checklist Parser - handles parsing and updating checklist markdown files.

Single Responsibility: Only deals with checklist file I/O and parsing.
"""

import asyncio
import re
from pathlib import Path
from typing import Optional
from uuid import uuid4

from ..models import ChecklistItem


class ChecklistParser:
    """
    Parser for checklist markdown files.
    
    Thread-safe with file locking for concurrent access.
    """
    
    def __init__(self, checklist_path: Path, repo_root: Path):
        self.checklist_path = Path(checklist_path)
        self.repo_root = Path(repo_root)
        self._file_locks: dict[str, asyncio.Lock] = {}
    
    def _get_lock(self, path: Path) -> asyncio.Lock:
        """Get or create a lock for a file path."""
        key = str(path.resolve())
        if key not in self._file_locks:
            self._file_locks[key] = asyncio.Lock()
        return self._file_locks[key]
    
    def read_safe(self, path: Path) -> str:
        """Safely read a file, returning empty string if not found."""
        try:
            resolved = path if path.is_absolute() else self.repo_root / path
            if not resolved.exists():
                return ""
            return resolved.read_text(encoding="utf-8")
        except Exception:
            return ""
    
    def write_atomically(self, path: Path, contents: str) -> None:
        """Write file atomically using temp file + rename."""
        resolved = path if path.is_absolute() else self.repo_root / path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        
        temp_file = resolved.parent / f"{uuid4()}.tmp"
        try:
            temp_file.write_text(contents, encoding="utf-8")
            temp_file.rename(resolved)
        except Exception:
            if temp_file.exists():
                temp_file.unlink()
            raise
    
    def parse(self) -> list[ChecklistItem]:
        """Parse the checklist file and return all items."""
        if not self.checklist_path.exists():
            raise FileNotFoundError(f"Checklist file not found: {self.checklist_path}")
        
        content = self.checklist_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        items: list[ChecklistItem] = []
        
        current_tier = ""
        current_section = ""
        in_table = False
        
        for line in lines:
            trimmed = line.strip()
            
            # Track tier headings
            if trimmed.startswith("## Tier ") or trimmed.startswith("## "):
                current_tier = trimmed.replace("## ", "").strip()
                current_section = ""
                continue
            
            # Track section headings
            if trimmed.startswith("### "):
                current_section = trimmed.replace("### ", "")
                continue
            
            # Detect table start
            if "| ID |" in line and "| Target |" in line:
                in_table = True
                continue
            
            # Parse table rows
            if in_table and trimmed.startswith("|"):
                cols = [c.strip() for c in trimmed.split("|") if c.strip()]
                
                if len(cols) >= 5:
                    item_id = cols[0]
                    target = cols[1]
                    priority = cols[2]
                    risk = cols[3]
                    status = cols[4]
                    
                    # Skip header/divider rows
                    if item_id in ("ID", "----") or item_id.startswith("---"):
                        continue
                    
                    items.append(ChecklistItem(
                        id=item_id,
                        target=target,
                        priority=priority,
                        risk=risk,
                        status=status,
                        tier=current_tier,
                        section=current_section,
                    ))
            
            # Detect table end
            if in_table and trimmed and "|" not in trimmed:
                in_table = False
        
        return items
    
    def get_remaining(self, items: list[ChecklistItem]) -> list[ChecklistItem]:
        """Get items that still need processing."""
        return [item for item in items if item.is_pending()]
    
    async def update_item_status(self, item_id: str, new_status: str) -> None:
        """Update the status of an item in the checklist file."""
        lock = self._get_lock(self.checklist_path)
        
        async with lock:
            content = self.read_safe(self.checklist_path)
            lines = content.split("\n")
            
            new_lines = []
            for line in lines:
                trimmed = line.strip()
                # Match the item by ID in the table
                if trimmed.startswith("|") and f" {item_id} " in line:
                    parts = line.split("|")
                    if len(parts) >= 6:
                        parts[5] = f" {new_status} "
                        line = "|".join(parts)
                new_lines.append(line)
            
            self.write_atomically(self.checklist_path, "\n".join(new_lines))
    
    def build_prefix_tier_map(self, items: list[ChecklistItem]) -> dict[str, str]:
        """Build a mapping from ID prefix to tier name."""
        mapping: dict[str, str] = {}
        for item in items:
            prefix = item.id.split("-")[0].upper() if "-" in item.id else item.id.upper()
            if prefix and item.tier:
                mapping[prefix] = item.tier
        return mapping
    
    def get_sanitized_tier_name(self, tier_heading: str) -> str:
        """Convert tier heading to a filesystem-safe name."""
        name = tier_heading.replace("## ", "").strip()
        name = re.sub(r"[^a-zA-Z0-9]", "_", name)
        name = re.sub(r"_+", "_", name)
        name = name.strip("_").lower()
        return name or "uncategorized"
    
    def resolve_tier_heading(self, item: ChecklistItem, prefix_tier_map: dict[str, str]) -> Optional[str]:
        """Resolve the tier heading for an item."""
        if item.tier:
            return item.tier if item.tier.startswith("## ") else f"## {item.tier}"
        
        prefix = item.id.split("-")[0].upper() if "-" in item.id else None
        if prefix and prefix in prefix_tier_map:
            tier = prefix_tier_map[prefix]
            return tier if tier.startswith("## ") else f"## {tier}"
        
        return None
    
    def format_checklist_row(self, item: ChecklistItem) -> str:
        """Format a checklist item as a markdown table row."""
        status = item.status or "☐ Not Started"
        return f"| {item.id} | {item.target} | {item.priority} | {item.risk} | {status} |"
    
    def ensure_tier_section(self, content: str, tier_name: str) -> str:
        """Ensure a tier section exists in the content."""
        header = tier_name if tier_name.startswith("## ") else f"## {tier_name}"
        table_header = "| ID | Target | Priority | Risk | Status |"
        divider = "|----|--------|----------|------|--------|"
        
        if header in content:
            return content if content.endswith("\n") else f"{content}\n"
        
        trimmed = content.rstrip()
        separator = "\n\n" if trimmed else ""
        return f"{trimmed}{separator}{header}\n{table_header}\n{divider}\n"
    
    async def append_rows(self, items: list[ChecklistItem], target_file: Optional[Path] = None) -> None:
        """Append new items to the checklist."""
        if not items:
            return
        
        target = target_file or self.checklist_path
        lock = self._get_lock(target)
        
        async with lock:
            content = self.read_safe(target)
            
            # Ensure tier sections exist
            unique_tiers = {item.tier for item in items if item.tier}
            for tier in unique_tiers:
                if tier not in content:
                    content = self.ensure_tier_section(content, tier)
            
            lines = content.split("\n") if content else []
            tier_metadata = self._build_tier_table_metadata(lines)
            prefix_tier_map = self.build_prefix_tier_map(self.parse() if self.checklist_path.exists() else [])
            grouped = self._group_items_by_tier(items, prefix_tier_map)
            
            # Calculate insertions (in reverse order to preserve line numbers)
            insertions = []
            for tier_heading, tier_items in grouped.items():
                meta = tier_metadata.get(tier_heading)
                if meta and "insert_line" in meta:
                    insertions.append({
                        "insert_line": meta["insert_line"],
                        "rows": [self.format_checklist_row(item) for item in tier_items],
                    })
            
            insertions.sort(key=lambda x: x["insert_line"], reverse=True)
            
            for insertion in insertions:
                for row in reversed(insertion["rows"]):
                    lines.insert(insertion["insert_line"], row)
            
            self.write_atomically(target, "\n".join(lines))
    
    def _build_tier_table_metadata(self, lines: list[str]) -> dict[str, dict]:
        """Build metadata about tier table locations."""
        metadata: dict[str, dict] = {}
        current_tier: Optional[str] = None
        in_table = False
        
        for i, line in enumerate(lines):
            if line.startswith("## "):
                current_tier = line.strip()
                in_table = False
                metadata[current_tier] = {}
            
            if not current_tier:
                continue
            
            if "| ID |" in line and "| Status |" in line:
                metadata[current_tier]["table_header_line"] = i
                metadata[current_tier]["table_end_line"] = i
                in_table = True
                continue
            
            if in_table:
                if line.strip().startswith("|"):
                    metadata[current_tier]["table_end_line"] = i
                elif line.strip() == "" or line.strip().startswith("-"):
                    in_table = False
        
        # Calculate insert lines
        for meta in metadata.values():
            if "table_end_line" in meta:
                meta["insert_line"] = meta["table_end_line"] + 1
            elif "table_header_line" in meta:
                meta["insert_line"] = meta["table_header_line"] + 1
        
        return metadata
    
    def _group_items_by_tier(self, items: list[ChecklistItem], prefix_tier_map: dict[str, str]) -> dict[str, list[ChecklistItem]]:
        """Group items by their tier heading."""
        groups: dict[str, list[ChecklistItem]] = {}
        for item in items:
            heading = self.resolve_tier_heading(item, prefix_tier_map)
            if heading:
                if heading not in groups:
                    groups[heading] = []
                groups[heading].append(item)
        return groups
