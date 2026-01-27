# CLI API Reference

This document provides the API reference for Stageflow's command-line tools and pipeline linting utilities.

## Dependency Linting

The CLI module provides static analysis tools to detect dependency issues in pipeline definitions before runtime.

### lint_pipeline()

```python
from stageflow.cli import lint_pipeline
```

Lint a Pipeline instance for dependency issues.

**Parameters:**
- `pipeline`: `Pipeline` — The Pipeline instance to analyze

**Returns:** `DependencyLintResult` with validation status and issues

**Example:**
```python
from stageflow.cli import lint_pipeline
from stageflow import Pipeline, StageKind

pipeline = (
    Pipeline()
    .with_stage("input", InputStage, StageKind.TRANSFORM)
    .with_stage("process", ProcessStage, StageKind.TRANSFORM, dependencies=("input",))
)

result = lint_pipeline(pipeline)
if not result.valid:
    for error in result.errors:
        print(f"Error: {error}")
```

### lint_pipeline_file()

```python
from stageflow.cli import lint_pipeline_file
```

Lint pipeline definitions from a Python file.

**Parameters:**
- `file_path`: `str | Path` — Path to the Python file containing pipeline definitions

**Returns:** `DependencyLintResult` with validation status and issues

**Raises:**
- `FileNotFoundError` — If the file doesn't exist
- `ImportError` — If the file can't be imported

**Example:**
```python
result = lint_pipeline_file("my_app/pipelines/chat.py")
print(result)
```

### DependencyIssue

```python
from stageflow.cli import DependencyIssue, IssueSeverity
```

Represents a dependency-related issue found during linting.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `stage_name` | `str` | The stage where the issue was found |
| `message` | `str` | Human-readable description of the issue |
| `severity` | `IssueSeverity` | How serious the issue is |
| `accessed_stage` | `str \| None` | The stage that was accessed (if applicable) |
| `suggestion` | `str \| None` | How to fix the issue (if applicable) |
| `line_number` | `int \| None` | Source line number (if available from AST analysis) |

**Methods:**

#### `__str__() -> str`

Returns a formatted string representation of the issue.

```python
issue = DependencyIssue(
    stage_name="process",
    message="Dependency 'missing' does not exist in pipeline",
    severity=IssueSeverity.ERROR,
    suggestion="Add stage 'missing' to the pipeline or remove it from dependencies"
)
print(issue)
# [ERROR] process: Dependency 'missing' does not exist in pipeline
#   Suggestion: Add stage 'missing' to the pipeline or remove it from dependencies
```

---

### IssueSeverity

```python
from stageflow.cli import IssueSeverity
```

Enumeration of issue severity levels.

**Values:**

| Value | Description |
|-------|-------------|
| `ERROR` | Critical issues that will cause runtime failures |
| `WARNING` | Potential issues that should be reviewed |
| `INFO` | Informational findings for optimization |

---

### DependencyLintResult

```python
from stageflow.cli import DependencyLintResult
```

Result of dependency linting analysis.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `valid` | `bool` | True if no errors found (warnings are OK) |
| `issues` | `list[DependencyIssue]` | List of all issues found |
| `stage_count` | `int` | Number of stages analyzed |
| `dependency_count` | `int` | Total declared dependencies |

**Properties:**

#### `errors -> list[DependencyIssue]`

Get only error-level issues.

```python
errors = result.errors
for error in errors:
    print(f"Critical: {error.message}")
```

#### `warnings -> list[DependencyIssue]`

Get only warning-level issues.

```python
warnings = result.warnings
for warning in warnings:
    print(f"Review: {warning.message}")
```

**Methods:**

#### `__str__() -> str`

Returns a formatted summary of the linting results.

```python
result = lint_pipeline(pipeline)
print(result)
# ✓ Pipeline dependencies are valid
#   Stages: 3
#   Dependencies: 2
```

---

## Command Line Interface

### Usage

```bash
python -m stageflow.cli.lint <file> [options]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `file` | Python file containing pipeline definition(s) |

### Options

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Show detailed output including info-level issues |
| `--json` | Output results as JSON |
| `--strict` | Treat warnings as errors |

### Examples

```bash
# Basic linting
python -m stageflow.cli.lint pipeline.py

# Verbose output
python -m stageflow.cli.lint pipeline.py --verbose

# JSON output for CI/CD
python -m stageflow.cli.lint pipeline.py --json

# Strict mode (warnings become errors)
python -m stageflow.cli.lint pipeline.py --strict
```

### JSON Output Format

```json
{
  "valid": false,
  "stage_count": 3,
  "dependency_count": 2,
  "issues": [
    {
      "stage_name": "process",
      "message": "Dependency 'missing' does not exist in pipeline",
      "severity": "error",
      "accessed_stage": "missing",
      "suggestion": "Add stage 'missing' to the pipeline or remove it from dependencies",
      "line_number": null
    }
  ]
}
```

---

## Detected Issues

The linter detects the following types of issues:

### 1. Missing Dependencies
**Severity:** ERROR
**Description:** A stage declares a dependency on a non-existent stage.
**Example:** `Stage A depends on 'missing_stage'` but `missing_stage` is not in the pipeline.

### 2. Circular Dependencies
**Severity:** ERROR
**Description:** A cycle exists in the dependency graph.
**Example:** `A → B → C → A`

### 3. Self-Dependencies
**Severity:** ERROR
**Description:** A stage lists itself as a dependency.
**Example:** `Stage A depends on A`

### 4. Orphaned Stages
**Severity:** WARNING
**Description:** A stage has no dependencies and nothing depends on it.
**Example:** `Stage Z` is completely isolated from the pipeline flow.

---

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Pipeline Lint
on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install stageflow
      - name: Lint pipelines
        run: |
          python -m stageflow.cli.lint my_app/pipelines/ --strict --json
```

### Pre-commit Hook

```bash
#!/bin/sh
# .git/hooks/pre-commit

echo "Running pipeline linting..."
python -m stageflow.cli.lint my_app/pipelines/ --strict
if [ $? -ne 0 ]; then
    echo "Pipeline linting failed. Commit aborted."
    exit 1
fi
```

---

## Advanced Usage

### Custom Linting Rules

You can extend the linter by analyzing stage source code for dependency access patterns:

```python
from stageflow.cli import analyze_stage_source

stage_source = '''
async def execute(self, ctx):
    # This accesses 'input' stage but doesn't declare dependency
    result = ctx.inputs.get_from("input", "data")
    return StageOutput.ok(data=result)
'''

accessed = analyze_stage_source(stage_source)
print(accessed)  # [('input', 3)]
```

### Programmatic Integration

```python
from stageflow.cli import lint_pipeline, DependencyLintResult
from pathlib import Path

def lint_all_pipelines(pipelines_dir: Path) -> bool:
    """Lint all pipeline files in a directory."""
    all_valid = True
    
    for py_file in pipelines_dir.glob("**/*.py"):
        try:
            result = lint_pipeline_file(py_file)
            if not result.valid:
                print(f"❌ {py_file}: {len(result.errors)} errors")
                all_valid = False
            else:
                print(f"✅ {py_file}: Valid")
        except Exception as e:
            print(f"⚠️  {py_file}: {e}")
            all_valid = False
    
    return all_valid

# Usage
valid = lint_all_pipelines(Path("my_app/pipelines"))
if not valid:
    exit(1)
```

---

## Error Recovery

### Common Issues and Solutions

#### 1. "No Pipeline instances found in file"
**Cause:** The file doesn't contain any Pipeline definitions.
**Solution:** Define a Pipeline instance or create a factory function:
```python
def create_chat_pipeline():
    return Pipeline().with_stage("chat", ChatStage, StageKind.TRANSFORM)
```

#### 2. "Could not load module"
**Cause:** Syntax errors or missing dependencies in the pipeline file.
**Solution:** Fix syntax errors and ensure all imports are available.

#### 3. Circular dependency errors
**Cause:** Stages depend on each other in a cycle.
**Solution:** Break the cycle by removing one dependency or restructuring the pipeline.

---

## Performance Considerations

- **File Analysis**: The linter imports and executes pipeline files, which may be slow for large codebases
- **Memory Usage**: Each pipeline file is loaded into memory separately
- **Caching**: Consider caching results for unchanged files in CI/CD pipelines

For large codebases, consider:
1. Running linter on changed files only
2. Using parallel execution for multiple files
3. Implementing result caching
