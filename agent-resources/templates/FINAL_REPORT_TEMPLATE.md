# Final Report: {ROADMAP_ENTRY_ID} - {ENTRY_TITLE}

> **Run ID**: {RUN_ID}  
> **Agent**: {AGENT_MODEL}  
> **SUT Version / Commit**: {SUT_VERSION}  
> **Date**: {DATE}  
> **Status**: {STATUS}

---

## Executive Summary

{2-3 paragraph summary of the entire investigation, key findings, and recommendations}

### Key Metrics

| Metric | Value |
|--------|-------|
| Total Findings | {N} |
| Strengths Identified | {N} |
| Bugs Found | {N} |
| Critical Issues | {N} |
| High Issues | {N} |
| DX Issues | {N} |
| Improvements Suggested | {N} |
| Component/Pattern Suggestions | {N} |
| Silent Failures Detected | {N} |
| Bugs Found via Log Analysis | {N} |
| Log Lines Captured | {N} |
| DX Score | {X.X}/5.0 |
| Test Coverage | {N}% |
| Time to Complete | {N} hours |

### Verdict

{One of: PASS, PASS_WITH_CONCERNS, NEEDS_WORK, FAIL}

{Brief justification for the verdict}

---

## 1. Research Summary

### 1.1 Industry Context

{Summary of industry research, if applicable}

**Key Industry Requirements:**
- {Requirement 1}
- {Requirement 2}
- ...

**Regulatory Considerations:**
- {Regulation 1}: {How it applies}
- {Regulation 2}: {How it applies}

### 1.2 Technical Context

{Summary of technical research}

**State of the Art:**
- {Approach 1}: {Brief description}
- {Approach 2}: {Brief description}

**Known Failure Modes:**
- {Failure mode 1}
- {Failure mode 2}

### 1.3 Hypotheses Tested

| # | Hypothesis | Result |
|---|------------|--------|
| H1 | {Hypothesis description} | ✅ Confirmed / ❌ Rejected / ⚠️ Partial |
| H2 | {Hypothesis description} | ✅ / ❌ / ⚠️ |
| ... | ... | ... |

---

## 2. Environment Simulation

### 2.1 Industry Persona

{If applicable, describe the persona adopted}

```
Role: {Role title}
Organization: {Type of organization}
Key Concerns:
- {Concern 1}
- {Concern 2}
Scale: {Volume/size characteristics}
```

### 2.2 Mock Data Generated

| Dataset | Records | Purpose |
|---------|---------|---------|
| {Dataset name} | {N} | {Purpose} |
| ... | ... | ... |

### 2.3 Services Mocked

| Service | Mock Type | Behavior |
|---------|-----------|----------|
| {Service name} | {Deterministic/Probabilistic} | {Brief description} |
| ... | ... | ... |

---

## 3. Automation Artifacts Produced

*(Pipelines, harnesses, datasets, tooling, or any other assets the agent created to exercise the SUT.)*

### 3.1 Artifact Overview

| Artifact | Type | Purpose | LOC / Size |
|----------|------|---------|------------|
| `{baseline_suite}` | pipeline / notebook / script | `{goal}` | `{lines_or_size}` |
| `{stress_tool}` | load tool / harness | `{goal}` | `{lines_or_size}` |
| `{dataset_name}` | dataset / fixture | `{goal}` | `{records}` |
| ... | ... | ... | ... |

### 3.2 Architecture / Flow

```
{ASCII diagram or description of how artifacts connect (e.g., pipeline graph, harness flow, tool orchestration)}
```

### 3.3 Notable Implementation Details

- {Pattern, workaround, or design decision worth calling out}
- {Instrumentation or guardrails added}
- {Reuse potential or follow-up TODOs}

---

## 4. Test Results

### 4.1 Correctness

| Test | Status | Notes |
|------|--------|-------|
| {Test name} | ✅ PASS / ❌ FAIL | {Notes} |
| ... | ... | ... |

**Correctness Score**: {N}/{M} tests passing

**Silent Failure Checks**:
- Golden output comparison: ✅ / ❌
- State audit: ✅ / ❌
- Metrics validation: ✅ / ❌
- Side effect verification: ✅ / ❌

**Silent Failures Detected**: {N}

### 4.2 Reliability

| Scenario | Expected | Actual | Status |
|----------|----------|--------|--------|
| {Scenario} | {Expected behavior} | {Actual behavior} | ✅ / ❌ |
| ... | ... | ... | ... |

**Reliability Score**: {N}/{M} scenarios passing

### 4.3 Performance

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| P50 Latency | {X}ms | {Y}ms | ✅ / ❌ |
| P95 Latency | {X}ms | {Y}ms | ✅ / ❌ |
| P99 Latency | {X}ms | {Y}ms | ✅ / ❌ |
| Throughput | {X} TPS | {Y} TPS | ✅ / ❌ |
| Memory Usage | {X}MB | {Y}MB | ✅ / ❌ |

**Performance Charts**: See `results/metrics/`

### 4.4 Security

| Attack Vector | Tested | Blocked | Notes |
|---------------|--------|---------|-------|
| {Attack type} | ✅ | ✅ / ❌ | {Notes} |
| ... | ... | ... | ... |

**Security Score**: {N}/{M} attacks blocked

### 4.5 Scalability

| Load Level | Status | Degradation |
|------------|--------|-------------|
| 1x baseline | ✅ | None |
| 10x baseline | ✅ / ❌ | {Description} |
| 100x baseline | ✅ / ❌ | {Description} |

### 4.6 Observability

| Requirement | Met | Notes |
|-------------|-----|-------|
| Correlation ID propagation | ✅ / ❌ | {Notes} |
| Span completeness | ✅ / ❌ | {Notes} |
| Error attribution | ✅ / ❌ | {Notes} |
| ... | ... | ... |

### 4.7 Silent Failures Detected

| ID | Pattern | Component | Detection Method | Severity |
|----|---------|-----------|------------------|----------|
| {SILENT-001} | {Swallowed exception / Default value / etc.} | {Component} | {Golden output / State audit / Metrics} | {critical/high/medium/low} |
| ... | ... | ... | ... | ... |

**Silent Failure Details:**

#### {FINDING_ID}: {Title}

**Pattern**: {pattern_type} | **Component**: {component}

{Description of the silent failure}

**Detection Method**:
{How the failure was discovered - e.g., compared golden output against actual output and found mismatch}

**Reproduction**:
```python
{Minimal code to reproduce}
```

**Impact**: {Impact description - why this is dangerous}

**Recommendation**: {Recommendation to fix}

---

{Repeat for each silent failure discovered}

**Silent Failure Summary**:
- Total Silent Failures: {N}
- Critical: {N}, High: {N}, Medium: {N}, Low: {N}
- Most Common Pattern: {Pattern}

---

## 5. Findings Summary

### 5.1 By Severity

```
Critical: {N} ████████
High:     {N} ██████
Medium:   {N} ████████████
Low:      {N} ████
Info:     {N} ██
```

### 5.2 By Type

```
Bug:            {N} ████████
Security:       {N} ██
Performance:    {N} ██████
Reliability:    {N} ████
Silent Failure: {N} ███
Log Issue:      {N} ████
DX:             {N} ████████
Improvement:    {N} ██████
Documentation:  {N} ██
Feature:        {N} ██
```

### 5.3 Critical & High Findings

**NOTE**: If any silent failures were discovered, ensure they are highlighted here even if they would otherwise be classified as medium severity - silent failures are inherently dangerous and should be prioritized.

#### {FINDING_ID}: {Title}

**Type**: {type} | **Severity**: {severity} | **Component**: {component}

{Description}

**Reproduction**:
```python
{Minimal code to reproduce}
```

**Impact**: {Impact description}

**Recommendation**: {Recommendation}

**Evidence**:
- [Log Excerpt](results/logs/run.log)
- [Screenshot](results/screenshots/evidence.png)

---

{Repeat for each critical/high finding}

---

### 5.4 Medium & Low Findings

#### {FINDING_ID}: {Title}

**Type**: {type} | **Severity**: {severity} | **Component**: {component}

{Description}

**Recommendation**: {Recommendation}

---

{Repeat for medium/low findings}

---

### 5.5 Log Analysis Findings

| Test Run | Log Lines | Errors | Warnings | Analysis |
|----------|-----------|--------|----------|----------|
| {test_name} | {N} | {N} | {N} | [Link](results/logs/{test_name}_analysis.md) |
| ... | ... | ... | ... | ... |

**Log Analysis Summary**:
- Total log lines captured: {N}
- Total errors found: {N}
- Total warnings: {N}
- Critical issues discovered via logs: {N}

**Notable Log Patterns**:

#### {PATTERN_ID}: {Title}

**Pattern**: {Pattern type - e.g., duplicate errors, missing success logs}

**Log Evidence**:
```log
{Relevant log excerpt showing the pattern}
```

**Analysis**:
{Explanation of what this pattern indicates}

**Finding Reference**: Links to finding ID if applicable

---

{Repeat for each notable pattern}

**Log-Based Bug Discoveries**:

{If bugs were discovered through log analysis, list them here}

| Bug ID | Pattern Type | Test Run | Severity |
|--------|--------------|----------|----------|
| {ID} | {Pattern} | {test_name} | {severity} |
| ... | ... | ... | ... |

**Log Quality Assessment**:
- Log completeness: ✅ / ❌
- Error logging: ✅ / ❌
- Context information: ✅ / ❌
- Correlation ID propagation: ✅ / ❌
- Stack trace quality: ✅ / ❌

**Logging Recommendations**:
{Based on log analysis, suggest improvements to logging practices}

---

## 6. Developer Experience Evaluation

### 6.1 Scores

| Category | Score | Notes |
|----------|-------|-------|
| Discoverability | {N}/5 | {Notes} |
| Clarity | {N}/5 | {Notes} |
| Documentation | {N}/5 | {Notes} |
| Error Messages | {N}/5 | {Notes} |
| Debugging | {N}/5 | {Notes} |
| Boilerplate | {N}/5 | {Notes} |
| Flexibility | {N}/5 | {Notes} |
| Performance | {N}/5 | {Notes} |
| **Overall** | **{N}/5** | |

### 6.2 Time Metrics

| Activity | Time |
|----------|------|
| Time to first working pipeline | {N} min |
| Time to understand first error | {N} min |
| Time to implement workaround | {N} min |

### 6.3 Friction Points

1. **{Friction point title}**
   - Encountered when: {Context}
   - Impact: {How it slowed down development}
   - Suggestion: {How to improve}

2. **{Friction point title}**
   - ...

### 6.4 Delightful Moments

1. **{What was good}**: {Why it was good}
2. ...

---

## 7. Recommendations

### 7.1 Immediate Actions (P0)

| # | Recommendation | Effort | Impact |
|---|----------------|--------|--------|
| 1 | {Recommendation} | {Effort} | {Impact} |
| ... | ... | ... | ... |

### 7.2 Short-Term Improvements (P1)

| # | Recommendation | Effort | Impact |
|---|----------------|--------|--------|
| 1 | {Recommendation} | {Effort} | {Impact} |
| ... | ... | ... | ... |

### 7.3 Long-Term Considerations (P2)

| # | Recommendation | Effort | Impact |
|---|----------------|--------|--------|
| 1 | {Recommendation} | {Effort} | {Impact} |
| ... | ... | ... | ... |

### 7.4 Industry-Specific Recommendations

{If applicable}

| # | Recommendation | Regulatory Driver |
|---|----------------|-------------------|
| 1 | {Recommendation} | {Regulation} |
| ... | ... | ... |

---

## 8. Framework Design Feedback

### 8.1 What Works Well (Strengths)

| ID | Title | Component | Impact |
|----|-------|-----------|--------|
| {STR-001} | {Title} | {Component} | {high/medium/low} |
| ... | ... | ... | ... |

**Top Strengths**:
- {Strength 1}: {Why it's good}
- {Strength 2}: {Why it's good}
- ...

### 8.2 What Needs Improvement

**Bugs Found**:
| ID | Title | Severity | Component |
|----|-------|----------|-----------|
| {BUG-001} | {Title} | {critical/high/medium/low} | {Component} |
| ... | ... | ... | ... |

**Total Bugs**: {N} (Critical: {N}, High: {N}, Medium: {N}, Low: {N})

**DX Issues Identified**:
| ID | Title | Category | Severity |
|----|-------|----------|----------|
| {DX-001} | {Title} | {category} | {high/medium/low} |
| ... | ... | ... | ... |

**Total DX Issues**: {N} (High: {N}, Medium: {N}, Low: {N})

**Key Weaknesses**:
- {Weakness 1}: {Why it's a problem}
- {Weakness 2}: {Why it's a problem}
- ...

### 8.3 Missing Capabilities

| Capability | Use Case | Priority |
|------------|----------|----------|
| {Capability} | {Use case} | {P0/P1/P2} |
| ... | ... | ... |

### 8.4 API Design Suggestions

{Specific API improvements with code examples}

```python
# Current API
{current_code}

# Suggested API
{suggested_code}
```

---

### 8.5 the the system Plus Package Suggestions

**Context**: the the system Plus is a companion package with prebuilt components for builders. These suggestions come from the agent's roleplay perspective based on testing experience.

#### New Stagekinds Suggested

| ID | Title | Priority | Use Case |
|----|-------|----------|----------|
| {IMP-001} | {Title} | {P0/P1/P2} | {Use case} |
| ... | ... | ... | ... |

**Detailed Stagekind Suggestions**:

#### {IMP-XXX}: {Title}

**Priority**: {P0/P1/P2}

**Description**:
{Detailed description}

**Roleplay Perspective**:
{From the agent's industry persona, explain why this stagekind is valuable}

**Proposed API**:
```python
# Example of how this stagekind would be used
{code_example}
```

---

#### Prebuilt Components Suggested

| ID | Title | Priority | Type |
|----|-------|----------|------|
| {IMP-002} | {Title} | {P0/P1/P2} | {utility/validation/integration/etc.} |
| ... | ... | ... | ... |

**Detailed Component Suggestions**:

#### {IMP-XXX}: {Title}

**Priority**: {P0/P1/P2}

**Description**:
{Detailed description of the component}

**Roleplay Perspective**:
{From the agent's industry persona, explain how this component would help}

**Proposed Implementation**:
{Description of suggested implementation approach}

#### Abstraction Patterns Suggested

| ID | Title | Priority | Impact |
|----|-------|----------|--------|
| {IMP-003} | {Title} | {P0/P1/P2} | {high/medium/low} |
| ... | ... | ... | ... |

**Summary**: {N} total suggestions for the the system Plus ({N} P0, {N} P1, {N} P2)

---

## 9. Appendices

### A. Structured Findings

See the following JSON files for detailed, machine-readable findings:
- `strengths.json`: Positive aspects and well-designed patterns
- `bugs.json`: All bugs, defects, and incorrect behaviors
- `dx.json`: Developer experience issues and usability concerns
- `improvements.json`: Enhancement suggestions, feature requests, and the the system Plus proposals
- `findings.json`: Comprehensive findings including all types

### B. Test Logs

See `results/logs/` for complete test logs including:
- Raw log files for each test run
- Log analysis summaries
- Log statistics and error extracts

### C. Log Analysis Details

See `results/logs/*_analysis.md` for detailed log analysis for each test run.

### D. Performance Data

See `results/metrics/` for raw performance data.

### E. Trace Examples

See `results/traces/` for execution traces.

### F. Citations

| # | Source | Relevance |
|---|--------|-----------|
| 1 | {Source} | {How it was used} |
| ... | ... | ... |

---

## 10. Sign-Off

**Run Completed**: {TIMESTAMP}  
**Agent Model**: {AGENT_MODEL}  
**Total Duration**: {DURATION}  
**Findings Logged**: {N}  

---

*This report was generated by the 24h Testers Agent System.*
