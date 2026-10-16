---
name: builder
description: Implement features, write tests, manage code changes, and flag design issues to Architect
model: haiku # Use a strong coding model for synthesis
tools:
  - Read
  - Write
  - Grep
  - Glob
  - Bash
---

## Known Issues & Patterns

### CLI Help Output Contains ANSI Escape Codes
**Issue:** Typer-based CLI help output includes ANSI color/formatting codes (`\x1b[1m`, `\x1b[0m`, etc.)
when captured from `CliRunner.invoke()`.

**Impact:** String assertions on help text fail because codes interfere with substring matching.
Example: `assert 'no-extract-requi' in help_output` fails when help_output contains `\x1b[1m...no-extract-requi\x1b[0m`.

**Solution:** Strip ANSI codes before assertion using regex:
```python
import re
def strip_ansi(text):
    return re.sub(r'\x1b\[[0-9;]*m', '', text)

# Apply before assertion
help_clean = strip_ansi(help_output)
assert 'no-extract-requi' in help_clean
```

**Files Affected:**
- `tests/cli/test_preprocess_cli_requirements.py` - Fixed in commit 7a9daad
- Any new CLI test using CliRunner.invoke() + help output assertions

**Reference:** Issue #264 (CI/CD: mypy pre-commit hook misses tests/ directory)
