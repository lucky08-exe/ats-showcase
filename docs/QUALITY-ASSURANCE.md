# 🔍 Code Quality Assurance Guide

This guide explains how to use pre-commit hooks for automated code quality checks in the ATS Showcase project. Pre-commit hooks catch formatting, linting, type, and testing issues **before** commits, providing fast feedback and maintaining consistent code standards.

---

## Quick Start (1 minute)

### Install Hooks

```bash
# Option 1: Automated setup (recommended)
uv run python -m src.setup.setup_precommit

# Option 2: Manual installation
uv sync --all-groups
pre-commit install
```

### Verify Setup

```bash
# Validate configuration
pre-commit validate-config

# Test hooks on all files
pre-commit run --all-files
```

### Make a Commit

Hooks run automatically on `git commit`:

```bash
git add src/my_file.py
git commit -m "Add new feature"  # Hooks run here automatically
```

---

## Overview: 6 Quality Hooks

All hooks are configured in `.pre-commit-config.yaml` and run in optimized order:

### ✅ Auto-Fix Hooks (Fast)
These hooks automatically fix issues and stage changes:

| Hook | Purpose | Time | Example |
|------|---------|------|---------|
| **trailing-whitespace** | Remove trailing spaces | <1s | `x = 1    ` → `x = 1` |
| **end-of-file-fixer** | Ensure single newline at EOF | <1s | (no final newline) → (adds one) |
| **black** | Format code consistently | 2–5s | `x=1+2` → `x = 1 + 2` |
| **ruff** | Fix linting & imports | 3–8s | Import reordering, safe fixes |

### ❌ Read-Only Hooks (Slow)
These hooks require manual fixes:

| Hook | Purpose | Time | Notes |
|------|---------|------|-------|
| **mypy** | Type checking | 15–30s | Requires `# type: ignore` comments for intentional issues |
| **pytest** | Run unit tests | 5–10s | Runs only unit tests (skips slow/integration) |

---

## Hook Details & Configuration

### 1. trailing-whitespace

**Purpose**: Remove trailing spaces from lines (usually accidental)

**Behavior**: Automatically removes trailing whitespace and stages the fix

**Time**: <1 second

**Example**:
```python
# Before (with trailing spaces)
x = 1
y = 2

# After (spaces removed)
x = 1
y = 2
```

**When it triggers**: Every commit

**Status**: ✅ Auto-fix

---

### 2. end-of-file-fixer

**Purpose**: Ensure files end with a single newline (not blank lines, not no newline)

**Behavior**: Automatically adds/removes newlines at EOF

**Time**: <1 second

**Example**:
```python
# Before (no final newline)
def foo():
    return 1

# After (single newline added)
def foo():
    return 1
(EOF)
```

**When it triggers**: Every commit

**Status**: ✅ Auto-fix

---

### 3. black

**Purpose**: Format code to Black standard (consistent style, line-length=100)

**Behavior**: Reformats Python files in-place, stages changes

**Time**: 2–5 seconds

**Configuration** (from `pyproject.toml`):
```toml
[tool.black]
line-length = 100
target-version = ["py311", "py312"]
```

**Example**:
```python
# Before
x=1+2
long_function_call(arg1,arg2,arg3,arg4,arg5,arg6,arg7,arg8,arg9,arg10,arg11,arg12)

# After
x = 1 + 2
long_function_call(
    arg1, arg2, arg3, arg4, arg5, arg6, arg7, arg8, arg9, arg10, arg11, arg12
)
```

**When it triggers**: On Python files

**Status**: ✅ Auto-fix

---

### 4. ruff

**Purpose**: Fast linting & import sorting (superset of flake8)

**Behavior**: Fixes safe violations automatically (import sorting, whitespace, etc.)

**Time**: 3–8 seconds

**Configuration** (from `pyproject.toml`):
```toml
[tool.ruff]
line-length = 100
select = ["E", "W", "F", "I", "C", "B"]
ignore = ["E501"]  # line too long (handled by black)
```

**Enabled Rules**:
- **E**: pycodestyle errors (whitespace, indentation)
- **W**: pycodestyle warnings
- **F**: Pyflakes (undefined names, unused imports)
- **I**: isort (import sorting)
- **C**: flake8-comprehensions (list/dict comprehensions)
- **B**: flake8-bugbear (common bugs)

**Example**:
```python
# Before
import os, sys
from typing import Dict, List

unused_var = 1

# After
import os
import sys
from typing import Dict, List
```

**When it triggers**: On Python files

**Status**: ✅ Auto-fix (safe violations only)

**Note**: Some violations require manual fixes. Ruff will print error codes—check the rule and fix manually.

---

### 5. mypy

**Purpose**: Static type checking (catches type bugs at commit time)

**Behavior**: Type checks all Python files, reports errors (requires manual fixes)

**Time**: 15–30 seconds

**Configuration** (from `pyproject.toml`):
```toml
[tool.mypy]
python_version = "3.12"
ignore_missing_imports = true
```

**Example**:
```python
# Before (type error)
def add(x: int, y: int) -> int:
    return x + y

result = add("a", "b")  # ❌ mypy error: Argument 1 has incompatible type "str"; expected "int"

# After (fixed)
def add(x: int, y: int) -> int:
    return x + y

result = add(1, 2)  # ✅ OK
```

**When it triggers**: On Python files

**Status**: ❌ Manual fix required

**Suppressing Type Errors**:
```python
result = add("a", "b")  # type: ignore  # Intentionally passing strings
```

---

### 6. pytest

**Purpose**: Run unit tests to ensure no broken commits

**Behavior**: Runs all unit tests (skips slow/integration tests), blocks commit on failure

**Time**: 5–10 seconds

**Configuration**:
```bash
pytest -m "not slow and not integration"
```

**Test Markers**:
- `@pytest.mark.slow` – Skipped on commit (runs in CI/CD)
- `@pytest.mark.integration` – Skipped on commit (runs in CI/CD)
- No marker – Runs on every commit

**Example**:
```python
# This runs on commit
def test_basic_addition():
    assert 1 + 1 == 2

# This is skipped (slow)
@pytest.mark.slow
def test_large_dataset():
    data = list(range(1_000_000))
    process(data)

# This is skipped (integration)
@pytest.mark.integration
def test_with_external_api():
    result = call_external_api()
    assert result is not None
```

**When it triggers**: On every commit (only runs unit tests)

**Status**: ❌ Manual fix required (fix code, re-commit)

---

## Performance Benchmarks

Typical pre-commit run times (on a modern machine):

```
Hook                    Time      Cumulative
──────────────────────────────────────────
trailing-whitespace     <1s       <1s
end-of-file-fixer       <1s       <1s
black                   2-5s      3-6s
ruff                    3-8s      6-14s
mypy                    15-30s    21-44s
pytest (unit)           5-10s     26-54s
──────────────────────────────────────────
TOTAL                             26-54s
```

**Target**: Full run completes in <60 seconds ✅

**Performance Tips**:
- First run (with dependencies): 1-2 minutes (normal)
- Subsequent runs: 30-60 seconds
- If taking >2 minutes: Check if pytest is running slow tests
  - Use `pytest --collect-only` to verify markers
  - Use `SKIP=pytest` to skip tests during debugging

---

## Skip Hooks When Needed

### Skip One Hook

Skip by hook ID:

```bash
# Skip black only
SKIP=black git commit -m "WIP: testing new syntax"

# Skip multiple
SKIP=black,ruff,mypy git commit -m "WIP"

# Skip tests
SKIP=pytest git commit -m "WIP: feature in progress"

# Skip all
SKIP=black,ruff,mypy,pytest git commit -m "Temporary WIP"
```

**Hook IDs**: `trailing-whitespace`, `end-of-file-fixer`, `black`, `ruff`, `mypy`, `pytest-unit`

### Force Commit Without Hooks (Emergency Only)

```bash
git commit --no-verify -m "Emergency hotfix"
```

⚠️ **Use sparingly**: Bypassed code may fail in CI/CD

---

## Troubleshooting

### Q: Hooks are taking too long (>60s)

**A**:
1. Check if pytest is running slow tests:
   ```bash
   # See which tests are marked slow
   pytest --collect-only -m slow

   # Verify markers in test files
   grep -r "@pytest.mark" tests/
   ```

2. Use `SKIP=pytest` to skip tests while debugging:
   ```bash
   SKIP=pytest git commit -m "..."
   ```

3. Profile the hooks:
   ```bash
   time pre-commit run --all-files
   ```

---

### Q: Black or ruff changed files I didn't write

**A**: Black and ruff auto-fix many style issues. This is expected behavior:

1. Review the changes: `git diff`
2. Stage them: `git add .`
3. Commit: `git commit -m "..."`
4. Or revert and fix manually: `git checkout -- .`

---

### Q: mypy says "error: Untyped library" but I can't fix it

**A**: Some packages don't have type hints. Suppress the error:

```python
import somelib  # type: ignore[import]

# Or globally in pyproject.toml
[tool.mypy]
ignore_missing_imports = true  # Ignore all untyped imports
```

---

### Q: I got a false positive from ruff/black

**A**:

For Black:
```python
# Disable formatting for a line
x = some_long_function_call(arg1, arg2)  # fmt: skip

# Or a block
# fmt: off
x = 1  # Weird formatting intentional
# fmt: on
```

For Ruff:
```python
# Disable a rule for a line
x = undefined_variable  # noqa: F821

# Or multiple rules
x = y  # noqa: E501, F821

# For entire file
# ruff: noqa
```

---

### Q: How do I run hooks manually without committing?

**A**:
```bash
# Run all hooks on changed files
pre-commit run

# Run all hooks on all files
pre-commit run --all-files

# Run a specific hook
pre-commit run black --all-files
pre-commit run mypy --all-files
```

---

### Q: How do I disable hooks permanently?

**A**: We don't recommend this, but you can:

```bash
# Uninstall hooks (won't run anymore)
pre-commit uninstall

# Re-install later
python -m src.setup.setup_precommit
```

---

### Q: Hooks aren't running on my commit

**A**: Check if they're installed:

```bash
# Verify hook is installed
ls -la .git/hooks/pre-commit

# If not installed, install:
python -m src.setup.setup_precommit

# Or manually:
pre-commit install
```

---

### Q: I see "lxml" errors

**A**: lxml requires system C libraries. Install them:

**macOS** (Homebrew):
```bash
brew install libxml2 libxslt
```

**Ubuntu/Debian**:
```bash
sudo apt-get install libxml2-dev libxslt1-dev
```

**Windows**: Use precompiled wheels (automatic with pip)

Then re-sync:
```bash
uv sync --all-groups
```

---

## CI/CD Integration

Pre-commit also runs in GitHub Actions for PR validation. The same `.pre-commit-config.yaml` is used for both local and CI environments.

**CI/CD Workflow** (`.github/workflows/quality-checks.yml`):
- Runs on: `push` to main/develop, all PRs
- Python versions: 3.11, 3.12
- Fails PR if any hook fails
- Results shown in PR checks

---

## Performance Optimization Tips

### For Local Development

1. **Skip slow hooks during development**:
   ```bash
   SKIP=mypy,pytest git commit -m "WIP: feature"
   ```

2. **Run hooks manually before committing**:
   ```bash
   pre-commit run --all-files
   # Or just the fast ones
   pre-commit run trailing-whitespace end-of-file-fixer black ruff --all-files
   ```

3. **Use pytest markers** to keep unit tests fast:
   ```python
   @pytest.mark.slow
   def test_large_computation():
       # This won't run on commit
       pass
   ```

### For CI/CD

CI/CD can run the full hook suite including slow tests:
```bash
pre-commit run --all-files
pytest tests/ -v
```

---

## Related Documentation

- **README.md**: Project overview with quick start
- **CONTRIBUTING.md**: Contributor guidelines
- **pyproject.toml**: Tool configuration (black, ruff, mypy, pytest)
- **.pre-commit-config.yaml**: Hook definitions
- **src/setup/setup_precommit.py**: Setup automation script

---

## Glossary

| Term | Definition |
|------|-----------|
| **Pre-commit** | Framework for managing git hooks |
| **Hook** | Script that runs automatically before commit |
| **Auto-fix** | Hook modifies files automatically |
| **Skip** | Bypass hook with `SKIP=hook_name` |
| **Stage** | Add changes to git staging area |
| **Marker** | Test label like `@pytest.mark.slow` |
| **Type ignore** | Comment `# type: ignore` to suppress mypy errors |
| **Noqa** | Comment `# noqa` to suppress ruff/linting errors |

---

## Quick Reference Card

### Common Commands

```bash
# Setup
uv run python -m src.setup.setup_precommit

# Manual run
pre-commit run --all-files

# Skip one hook
SKIP=black git commit -m "..."

# Skip all hooks (emergency)
git commit --no-verify -m "..."

# Check hook status
ls -la .git/hooks/pre-commit

# Uninstall hooks
pre-commit uninstall

# Validate config
pre-commit validate-config
```

### Hook IDs

```
trailing-whitespace  end-of-file-fixer  black  ruff  mypy  pytest-unit
```

---

**Last Updated**: 2026-05-22

**Questions?** See troubleshooting section above or check [Issues](https://github.com/pluto-atom-4/ats-showcase/issues)
