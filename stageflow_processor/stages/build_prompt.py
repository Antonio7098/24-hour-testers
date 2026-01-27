"""
Build Prompt Stage - constructs the agent prompt for a checklist item.

Single responsibility: Build prompts from templates and context.
"""

from pathlib import Path
from stageflow import StageContext, StageKind, StageOutput

from ..models import ChecklistItem

COMPLETION_MARKER = "ITEM_COMPLETE"


class BuildPromptStage:
    """Stage that builds the agent prompt for processing an item."""
    
    name = "build_prompt"
    kind = StageKind.TRANSFORM
    
    def __init__(
        self,
        repo_root: Path,
        agent_prompt_path: Path,
        checklist_path: Path,
    ):
        self.repo_root = Path(repo_root)
        self.agent_prompt_path = Path(agent_prompt_path)
        self.checklist_path = Path(checklist_path)
        self._prompt_cache: str | None = None
    
    def _load_prompt_template(self) -> str:
        """Load the agent prompt template."""
        if self._prompt_cache is not None:
            return self._prompt_cache
        
        if not self.agent_prompt_path.exists():
            return ""
        
        self._prompt_cache = self.agent_prompt_path.read_text(encoding="utf-8")
        return self._prompt_cache
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        """Build the prompt for the current item."""
        # Get item data from context metadata
        metadata = ctx.snapshot.metadata or {}
        item_data = metadata.get("item")
        if not item_data:
            return StageOutput.fail(error="No item provided in context metadata")
        
        item = ChecklistItem(**item_data) if isinstance(item_data, dict) else item_data
        
        run_dir = metadata.get("run_dir")
        if not run_dir:
            return StageOutput.fail(error="No run_dir provided in context metadata")
        
        mission_brief = metadata.get("mission_brief") or "No brief provided"
        
        # Load template
        template = self._load_prompt_template()
        if not template:
            # Use a minimal default prompt
            template = """
You are an autonomous testing agent. Your task is to execute checklist item {{ENTRY_ID}}.

Task: {{ENTRY_TITLE}}
Priority: {{PRIORITY}}
Risk: {{RISK_CLASS}}

Mission Brief:
{{MISSION_BRIEF}}

Save all artifacts to: {{RUN_DIR}}

When complete, output: ITEM_COMPLETE
"""
        
        # Get relative path for prompt
        run_dir_path = Path(run_dir)
        try:
            relative_path = run_dir_path.relative_to(self.repo_root)
        except ValueError:
            relative_path = run_dir_path
        
        # Build prompt from template
        prompt = template
        prompt = prompt.replace("{{ENTRY_ID}}", item.id)
        prompt = prompt.replace("{{ENTRY_TITLE}}", item.target)
        prompt = prompt.replace("{{PRIORITY}}", item.priority)
        prompt = prompt.replace("{{RISK_CLASS}}", item.risk)
        prompt = prompt.replace("{{INDUSTRY}}", "Tech")
        prompt = prompt.replace("{{DEPLOYMENT_MODE}}", "Dev")
        prompt = prompt.replace("{{CHECKLIST_FILE}}", str(self.checklist_path))
        prompt = prompt.replace("{{MISSION_BRIEF}}", mission_brief)
        prompt = prompt.replace("{{RUN_DIR}}", str(relative_path).replace("\\", "/"))
        
        # Add task instructions
        prompt += f"\n\nYOUR CURRENT TASK:\nExecute checklist item {item.id}: {item.target}\n"
        prompt += f"Perform the necessary tests/research. All artifacts MUST be saved in: {relative_path}\n"
        prompt += f'When you have completed the task and generated the FINAL-REPORT.md, you MUST output: "{COMPLETION_MARKER}" to signal completion.\n'
        
        return StageOutput.ok(
            prompt=prompt,
            item_id=item.id,
            run_dir=str(run_dir),
            completion_marker=COMPLETION_MARKER,
        )
