"""
Parse Checklist Stage - loads and parses the checklist file.

Single responsibility: Parse checklist and identify items to process.
"""

from stageflow import StageContext, StageKind, StageOutput

from ..utils.checklist_parser import ChecklistParser
from ..models import ChecklistItem


class ParseChecklistStage:
    """Stage that parses the checklist and identifies pending items."""
    
    name = "parse_checklist"
    kind = StageKind.TRANSFORM
    
    def __init__(self, parser: ChecklistParser, batch_size: int = 5):
        self.parser = parser
        self.batch_size = batch_size
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        """Parse checklist and return pending items for processing."""
        try:
            # Parse all items
            all_items = self.parser.parse()
            
            if not all_items:
                return StageOutput.skip(reason="No items found in checklist")
            
            # Get remaining items
            remaining = self.parser.get_remaining(all_items)
            
            if not remaining:
                return StageOutput.ok(
                    all_items=[item.__dict__ for item in all_items],
                    remaining_items=[],
                    batch_items=[],
                    total_count=len(all_items),
                    remaining_count=0,
                    batch_count=0,
                    all_complete=True,
                    prefix_tier_map=self.parser.build_prefix_tier_map(all_items),
                )
            
            # Select batch
            batch = remaining[:self.batch_size]
            prefix_tier_map = self.parser.build_prefix_tier_map(all_items)
            
            return StageOutput.ok(
                all_items=[item.__dict__ for item in all_items],
                remaining_items=[item.__dict__ for item in remaining],
                batch_items=[item.__dict__ for item in batch],
                total_count=len(all_items),
                remaining_count=len(remaining),
                batch_count=len(batch),
                all_complete=False,
                prefix_tier_map=prefix_tier_map,
            )
            
        except FileNotFoundError as e:
            return StageOutput.fail(
                error=f"Checklist file not found: {e}",
                data={"error_type": "FILE_NOT_FOUND"},
            )
        except Exception as e:
            return StageOutput.fail(
                error=f"Failed to parse checklist: {e}",
                data={"error_type": type(e).__name__},
            )
