# Infinite Backlog Synthesis Prompt

This prompt is used by `scripts/checklist-processor.js` whenever infinite mode needs
additional checklist rows. Provide it to any LLM agent responsible for extending the
backlog so new rows match the tone and priorities of the existing plan.

---

## How to Use

Inject the following values before handing the prompt to the agent:

- `{{CHECKLIST_CONTENT}}` — current `SUT-CHECKLIST.md` markdown, including status.
- `{{NEEDED_COUNT}}` — integer number of rows required to refill the batch.

```
You are an autonomous reliability planner. When the existing backlog runs dry you must
synthesize new checklist rows that feel like thoughtful follow-ons, not duplicates.

Current checklist markdown (for reference, do not rewrite existing rows):
{{CHECKLIST_CONTENT}}

Generate exactly {{NEEDED_COUNT}} brand-new checklist rows scoped to one autonomous run each.
Keep the same five-column structure (ID, Target, Priority, Risk, Status) and prefer concrete
SUT targets over placeholders.

Respond ONLY with JSON using the shape:
{
  "items": [
    {
      "id": "INF-123",
      "target": "...",
      "priority": "P1",
      "risk": "High",
      "status": "☐ Not Started",
      "tier": "Tier 4: Reliability & Backlog Expansion"
    }
  ]
}
```

---

## Notes for Agents

1. IDs should be unique. Use the `INF-###` pattern if the caller does not provide one.
2. Priorities must stay within the existing P0–P3 scale unless the checklist defines another.
3. Use risks like Catastrophic/Severe/High/Moderate/Low to match current phrasing.
4. Always default status to `☐ Not Started`.
5. **Tier Assignment**: Assign each item to the most relevant existing tier found in the checklist. If the item represents a completely new category of testing not covered by existing tiers, you may define a new Tier name (e.g., "Tier 5: Performance").
6. Focus on expansion work that can be executed independently in the next batch.
