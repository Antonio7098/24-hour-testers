# Tier Report Aggregation Prompt

Use this prompt when a tier in `scenario-checklist.md` is fully ✅ and you need a
structured summary for stakeholders.

---

## Inputs to substitute

- `{{TIER_NAME}}` – the heading text for the tier (e.g., `Tier 2 · Functional Risks`).
- `{{CHECKLIST_ROWS}}` – Markdown table of the tier's checklist rows (ID, Target, Priority, Risk, Status).
- `{{MISSION_BRIEF}}` – contents of `mission-brief.md` (or fallback overview).
- `{{FINAL_REPORT_DIGEST}}` – concatenated excerpts from `runs/**/FINAL_REPORT.md` related to this tier.

---

## Prompt

```
You are a reliability program lead preparing a stakeholder-ready report for the
completed tier {{TIER_NAME}}.

Mission Brief Context:
{{MISSION_BRIEF}}

Checklist Rows:
{{CHECKLIST_ROWS}}

Final Report Evidence:
{{FINAL_REPORT_DIGEST}}

Produce a Markdown report with the following sections:
1. Executive Summary – 2-3 bullet highlights describing the outcomes.
2. Key Findings – table with columns {ID, Title, Severity, Impact, Status}.
3. Risks & Gaps – list any remaining open issues or follow-ups.
4. Evidence & Artifacts – bullet list linking notable FINAL_REPORT snippets or
   telemetry.
5. Next Steps – concrete recommendations for the next batch.

Keep the tone concise and action-oriented. Prefer bullet lists over prose.
```

---

## Notes for Agents

1. Do not hallucinate evidence; quote from the provided final report digest.
2. Preserve severity terms used in the findings (`critical`, `high`, etc.).
3. If no findings exist, state that explicitly and focus on positive outcomes.
4. Always mention whether success criteria were met and call out any deviations.
