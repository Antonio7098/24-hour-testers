# Error Message Style Guide

This guide defines the structure and tone for surfaced contract violation errors in stageflow. The goal is to make errors actionable, searchable, and linkable to remediation docs.

## Structure

Every contract error should include:

1. **Problem** – What went wrong in plain language.
2. **Context** – Where it happened (stage names, dependency edges, versions).
3. **Fix** – Immediate remediation steps.
4. **Docs** – Link to a deeper troubleshooting guide.
5. **Code** – Stable error identifier for automation.

## Template

```
{code}: {summary}

Context:
{context_lines}

Fix:
{fix_hint}

Docs: {doc_url}
```

## Example Errors

### Missing Stage Dependency

```
CONTRACT-004-MISSING_DEP: Stage 'summarize' depends on 'extract' which does not exist

Context:
- Stage: summarize
- Missing dependency: extract

Fix:
Add the missing stage to the pipeline or remove it from the dependency list.

Docs: https://github.com/stageflow/stageflow/blob/main/docs/advanced/error-messages.md#missing-stage-dependencies
```

### Dependency Cycle

```
CONTRACT-004-CYCLE: Dependency cycle detected

Context:
- Cycle: summarize -> translate -> summarize

Fix:
Break the cycle by removing one of the dependencies in the loop.

Docs: https://github.com/stageflow/stageflow/blob/main/docs/advanced/error-messages.md#dependency-cycles
```

### Empty Pipeline

```
CONTRACT-004-EMPTY: Attempted to build an empty pipeline

Context:
- Pipeline name: chat_pipeline

Fix:
Add at least one stage before invoking Pipeline.build().

Docs: https://github.com/stageflow/stageflow/blob/main/docs/advanced/error-messages.md#empty-pipelines
```

## Implementation Guidance

- Use `ContractErrorInfo` to populate the structured fields.
- Keep `summary` under 80 characters.
- Include stage names and versions in `context`.
- Use `get_contract_suggestion` to look up fix steps and doc URLs.
- Ensure `code` is stable and documented in the suggestions registry.

## Enforcement

- Unit tests snapshot error output for golden paths.
- Lint checks enforce presence of `doc_url` and `fix_hint` on raised contract errors.
- CI validates that every registered suggestion has a reachable doc URL.
