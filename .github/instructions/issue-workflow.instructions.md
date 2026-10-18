---
applyTo: "**"
excludeAgent: "code-review"
---

# GitHub Copilot Issue Implementation Workflow

**Purpose**: Standardized workflow for implementing or fixing GitHub Issues in ATS Showcase using GitHub Copilot CLI.

**Audience**: Developers using `gh copilot` to work on issues

**Last Updated**: 2026-05-29

---

## Overview

This workflow ensures that all issue implementations follow consistent practices:

1. **Plan** - Create implementation plan document
2. **Implement** - Make code changes following plan
3. **Validate** - Run linting, type checking, tests
4. **Branch & Commit** - Create feature branch with atomic commits
5. **Push & Review** - Push to remote, create PR, handle feedback

---

## Phase 1: Planning

### Step 1.1: Read the Issue

```bash
# Get issue details
gh issue view <issue-number>

# Get detailed comments
gh issue view <issue-number> --comments
```

**Document:**
- Issue title and number
- Problem statement
- Current state
- Expected outcome
- Success criteria

### Step 1.2: Create Implementation Plan

Create a new file in `docs/implementation-planning/`:

**File Naming Convention:**
```
docs/implementation-planning/issue-<NUMBER>-<kebab-case-title>.md
```

**Examples:**
- `issue-22-mock-parsing-fix.md`
- `issue-19-poc-crawl-automation.md`

**Plan Document Structure:**

```markdown
# Issue #<NUMBER>: <Title>

**Issue**: <Short description>
**Status**: Planning
**Priority**: <High/Medium/Low>
**Estimated Time**: <X minutes>
**Dependencies**: <If any>

## Overview

<Detailed explanation of the problem and approach>

## Investigation Checklist

- [ ] Understand current implementation
- [ ] Identify root cause
- [ ] Verify hypothesis with tests
- [ ] Document findings

## Implementation Plan

### Phase 1: <Phase Name> (<Time>)

1. **Task 1**: <Description>
   - [ ] Step 1.1
   - [ ] Step 1.2

2. **Task 2**: <Description>
   - [ ] Step 2.1

### Phase 2: <Next Phase> (<Time>)

...

## Files to Modify

| File | Change | Reason |
|------|--------|--------|
| path/to/file.py | Update X to Y | Fix root cause |

## Success Criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] All tests passing
- [ ] Pre-commit hooks pass

## Related Files & References

- GitHub Issue: https://github.com/pluto-atom-4/ats-showcase/issues/<NUMBER>
- Related files: list them

---

**Document Version**: 1.0
**Created**: YYYY-MM-DD
**Status**: Planning
```

### Step 1.3: Verify Plan with Investigation

Before proceeding to implementation:

```bash
# Run existing tests to understand current state
export PYTHONPATH="/path/to/src:$PYTHONPATH"
uv run pytest tests/ -v

# Check linting status
uv run ruff check src/ tests/

# Review relevant source files
cat src/path/to/relevant/file.py
```

**Update plan with findings:**
- Actual test results
- Current behavior vs expected
- Exact files that need modification

---

## Phase 2: Implementation

### Step 2.1: Create Feature Branch

```bash
# Get latest main
git checkout main
git pull origin main

# Create feature branch from main
git checkout -b fix/issue-<NUMBER>-<kebab-case-title>
# or
git checkout -b feat/issue-<NUMBER>-<kebab-case-title>

# Examples:
git checkout -b fix/issue-22-mock-parsing
git checkout -b feat/issue-19-poc-crawl
```

**Branch naming conventions:**
- `fix/issue-<N>-<name>` - Bug fixes, patches
- `feat/issue-<N>-<name>` - New features, enhancements
- `docs/issue-<N>-<name>` - Documentation only

### Step 2.2: Make Code Changes

**Best Practices:**

1. **Change only what's necessary**
   - Stick to the plan
   - Don't fix unrelated issues
   - Keep commits focused

2. **Follow project conventions**
   - Code style (black, ruff)
   - Type hints (mypy)
   - Docstrings and comments
   - Test coverage

3. **Update documentation**
   - Update implementation plan with resolution
   - Update related .md files in docs/
   - Update README.md if needed

   **Documentation Structure (Two-Location Approach):**

   ATS Showcase uses a dual documentation model for GitHub Issues:

   a) **Implementation Planning** (`docs/implementation-planning/`)
      - File: `issue-<NUMBER>-<kebab-case-title>.md`
      - Purpose: Detailed step-by-step implementation plan
      - Usage: Before implementation starts
      - Content: Investigation checklist, tasks, file modifications, success criteria
      - Example: `issue-22-mock-parsing-fix.md`, `issue-19-poc-crawl-automation.md`

   b) **Developer Notes** (`docs/dev-note/`)
      - File: `issue-<NUMBER>-<kebab-case-title>.md`
      - Purpose: Reference documentation and research findings
      - Usage: After implementation for future reference
      - Content: Analysis results, structure decisions, architectural notes, lessons learned
      - Example: `issue-19-poc-evaluation-guide.md`, `issue-23-copilot-structure-analysis.md`

   **When to create which file:**
   - **Always create** `docs/implementation-planning/issue-<N>-*.md` during Phase 1 (Planning)
   - **Create additional** `docs/dev-note/issue-<N>-*.md` if you discover important insights that should be preserved (during Phase 2-3)
   - Both files get committed but serve different purposes

   **Example from Issue #23:**
   - Implementation Planning: `issue-23-add-copilot-workflow.md` → Implementation steps
   - Developer Notes: `issue-23-copilot-structure-analysis.md` → Research on GitHub Copilot file structure standards

**Example workflow:**

```bash
# Make changes
vim src/path/to/file.py

# Check status
git status

# Verify changes look correct
git diff src/path/to/file.py
```

### Step 2.3: Update Implementation Plan

In your feature branch, update the plan document:

```markdown
# Issue #<NUMBER>: <Title>

**Status**: In Progress ← UPDATE FROM "Planning"

...

## Implementation Done

✅ Phase 1 complete
✅ Phase 2 complete
⏳ Phase 3 in progress

### Resolution Summary

<Describe what was changed and why>

- Changed X to Y because <reason>
- Updated Z to fix <specific issue>
- Added test for <scenario>

---

**Document Version**: 1.1
**Updated**: YYYY-MM-DD
**Status**: In Progress ← UPDATE
```

---

## Phase 3: Validation

### Step 3.1: Run Pre-commit Hooks

```bash
# Install pre-commit if needed
uv pip install pre-commit

# Run all hooks on changed files
uv run pre-commit run --files <file1> <file2>

# Or run all hooks on all files
uv run pre-commit run --all-files

# Expected output:
# Trim trailing whitespace............................Passed
# Fix end of file.....................................Passed
# Format code with black..............................Passed
# Lint with ruff......................................Passed
# Type check with mypy.................................Passed
```

**If hooks fail:**

```bash
# Black formatting fixes automatically
# Ruff and trailing whitespace also auto-fix
# Re-run to verify
uv run pre-commit run --all-files

# If mypy fails, fix manually and re-run
```

### Step 3.2: Run Type Checking

```bash
# Type check modified files
uv run mypy src/path/to/file.py

# Or type check entire src/ and tests/ directories
uv run mypy src/ tests/

# Ensure no type errors reported
```

### Step 3.3: Run Tests

```bash
# Set PYTHONPATH for src-layout project
export PYTHONPATH="/path/to/ats-showcase/src:$PYTHONPATH"

# Run full test suite
uv run pytest tests/ -v

# Or run specific test file
uv run pytest tests/test_file.py -v

# Or run tests matching pattern
uv run pytest tests/ -k "test_function_name" -v

# Expected: All tests passing (or xfail as expected)
```

**If tests fail:**

```bash
# Run with more verbose output
uv run pytest tests/test_file.py -vv

# Run single test to debug
uv run pytest tests/test_file.py::TestClass::test_method -xvs

# Check if failure is related to your change
# If unrelated, document in PR
```

### Step 3.4: Final Validation

```bash
# Before committing, verify all checks pass:

# 1. Pre-commit
uv run pre-commit run --all-files

# 2. Type checking
uv run mypy src/ tests/

# 3. Tests
export PYTHONPATH="/path/to/ats-showcase/src:$PYTHONPATH"
uv run pytest tests/ -q

# 4. Markdown linting (if docs/ files added)
# For documentation files added to docs/implementation-planning/ or docs/dev-note/:
mdl docs/path/to/file.md

# To check entire docs directory:
mdl docs/

# Expected: All green ✅
```

**Common Pre-commit Issues & Solutions:**

If pre-commit hooks fail:

| Hook | Error | Fix |
|------|-------|-----|
| **Trim trailing whitespace** | "Fixed trailing whitespace" | Pre-commit auto-fixes; re-run to verify |
| **Fix end of file** | "Fixed end of file" | File missing final newline; pre-commit adds it |
| **Black formatter** | "Reformatted file" | Pre-commit auto-fixes; re-run to verify |
| **Ruff linter** | "Fixed issues" | Pre-commit auto-fixes; re-run to verify |
| **mypy** | "Type errors" | Requires manual fixes; examine error messages |

**If a hook modifies files:**
```bash
# After pre-commit auto-fixes:
git add <modified-files>
uv run pre-commit run --all-files
# Repeat until all hooks pass
```

**Note on Markdown Linting:**
If `mdl` reports errors, most are resolvable:
- Trailing spaces: Fixed by pre-commit
- Line length: Check if necessary or acceptable for tables/long descriptions
- Header hierarchy: Ensure H2/H3 structure is correct (no skipping levels)
- YAML frontmatter: MD041 error is expected and acceptable

---

## Phase 4: Commit & Push

### Step 4.1: Stage Changes

```bash
# Check what changed
git status

# Stage only files you modified (as per plan)
git add src/path/to/file1.py
git add src/path/to/file2.py
git add docs/implementation-planning/issue-<N>-<title>.md

# Verify staged changes
git diff --cached
```

**Important: Only commit files mentioned in the plan**
- Don't accidentally commit unrelated changes
- Don't commit node_modules, cache, .env, etc.

### Step 4.2: Create Commit

```bash
# Commit with clear message
git commit -m "Fix: Issue #<N> short description

Detailed explanation of what was changed and why.

- Bullet point 1
- Bullet point 2

Files changed:
- src/path/to/file.py: Changed X to Y
- docs/implementation-planning/issue-<N>-<title>.md: Updated

Fixes #<N>"

# Use conventional commit format:
# fix: - for bug fixes
# feat: - for new features
# docs: - for documentation
# refactor: - for code reorganization
```

**Example:**

```bash
git commit -m "Fix: Resolve mock response parsing in tests (issue #22)

The mock Anthropic API response structure was not properly iterable.
Updated response.content to be a proper list instead of MagicMock chain.

Root cause: response.content[0].text pattern didn't support iteration
Solution: Create text_block MagicMock and response.content = [text_block]

Results:
- ✅ 3 tests now pass (previously xfailed)
- ✅ All 74 tests passing
- ✅ Mock now matches real Anthropic response structure

Files changed:
- tests/test_assessment.py: Fixed mock setup, removed xfail markers
- docs/implementation-planning/issue-22-mock-parsing-fix.md: Updated

Fixes #22"
```

### Step 4.3: Push to Remote

```bash
# First time pushing this branch
git push -u origin fix/issue-<NUMBER>-<kebab-case-title>

# Example:
git push -u origin fix/issue-22-mock-parsing

# Output will include link to create PR:
# Create a pull request for 'fix/issue-22-mock-parsing' on GitHub by visiting:
#      https://github.com/pluto-atom-4/ats-showcase/pull/new/fix/issue-22-mock-parsing
```

---

## Phase 5: Pull Request & Review

### Step 5.1: Create Pull Request

```bash
# Create PR from CLI
gh pr create \
  --title "Fix #<NUMBER>: <Brief description>" \
  --body "## Summary

Fixes #<NUMBER>

## Changes

- Change 1
- Change 2

## Validation

- [x] All 74 tests passing
- [x] Pre-commit hooks pass
- [x] Type checking passes
- [x] Code follows project conventions

## Related

- See docs/implementation-planning/issue-<N>-<title>.md for details" \
  --base main

# Example:
gh pr create \
  --title "Fix #22: Resolve mock response parsing in LLM tests" \
  --body "## Summary

Fixes #22

## Changes

- Fixed mock_anthropic fixture to use proper list structure
- Updated test_assess_job_with_markdown_json mock setup
- Removed @pytest.mark.xfail decorators from 3 tests

## Results

- ✅ test_assess_job_success: 50 → 78
- ✅ test_assess_job_with_markdown_json: 50 → 78
- ✅ test_assess_job_token_cost_calculation: 0.0 → 0.002055
- ✅ All 74 tests passing (previously 71 + 3 xfailed)

## Validation

- [x] All 74 tests passing
- [x] Pre-commit hooks pass
- [x] Type checking passes

See docs/implementation-planning/issue-22-mock-parsing-fix.md" \
  --base main
```

### Step 5.2: Monitor GitHub Actions

```bash
# View PR status
gh pr view --web  # Open in browser

# Or check from CLI
gh pr checks   # Show CI status
```

**Monitor for:**
- ✅ Code Quality Checks (black, ruff, mypy, pytest)
- ✅ Tests passing on Python 3.11 and 3.12
- ✅ All quality gates passing

### Step 5.3: Address Feedback

**If GitHub Actions fails:**

1. **Read the error**
   ```bash
   gh pr checks    # Show which check failed
   ```

2. **Investigate locally**
   ```bash
   # Reproduce the failure locally
   export PYTHONPATH="/path/to/src:$PYTHONPATH"
   uv run pytest tests/ -v
   # Or specific failing test
   ```

3. **Fix the issue**
   ```bash
   # Make code changes
   vim src/path/to/file.py

   # Validate fixes
   uv run pre-commit run --all-files
   uv run mypy src/ tests/
   uv run pytest tests/ -q
   ```

4. **Commit and push**
   ```bash
   git add .
   git commit -m "Fix: Address GitHub Actions failure (test_X failing)"
   git push
   ```

**If code review has feedback:**

1. **Read the review comments**
   ```bash
   gh pr view    # Show comments
   ```

2. **Make requested changes**
   ```bash
   # Update code as per feedback
   vim src/path/to/file.py
   ```

3. **Test again**
   ```bash
   uv run pytest tests/ -q
   ```

4. **Commit with context**
   ```bash
   git add src/path/to/file.py
   git commit -m "Review feedback: Address comment about X

   Changed Y to Z as requested in code review.

   Related: Review comment on line N"
   git push
   ```

### Step 5.4: Merge PR

Once approved and all checks pass:

```bash
# Merge PR (squash or regular merge as per project policy)
gh pr merge --squash    # Squash into single commit
# or
gh pr merge --rebase    # Rebase and merge
# or
gh pr merge              # Create merge commit

# Example:
gh pr merge --squash --auto  # Auto-merge when ready
```

---

## Quick Reference

### Command Checklist

```bash
# 1. Planning
gh issue view <NUMBER>
mkdir -p docs/implementation-planning
cat > docs/implementation-planning/issue-<N>-<title>.md << 'EOF'
...plan content...
EOF

# 2. Branch & changes
git checkout -b fix/issue-<NUMBER>-<title>
vim src/path/to/file.py
vim docs/implementation-planning/issue-<N>-<title>.md

# 3. Validation
uv run pre-commit run --all-files
uv run mypy src/ tests/
export PYTHONPATH="/path/to/src:$PYTHONPATH"
uv run pytest tests/ -q

# 4. Commit & push
git add src/path/to/file.py docs/implementation-planning/issue-<N>-<title>.md
git commit -m "Fix/Feat: ..."
git push -u origin fix/issue-<NUMBER>-<title>

# 5. PR & review
gh pr create --title "Fix #<N>: ..." --body "..." --base main
gh pr view
gh pr checks
# Address feedback if needed
gh pr merge
```

### File Locations

The ATS Showcase repository uses an official GitHub Copilot instructions structure with a two-location documentation approach for GitHub Issues:

```
Project Root
├── .github/
│   ├── copilot-instructions.md          (Repository-wide Copilot guidance)
│   ├── instructions/
│   │   └── issue-workflow.instructions.md   (THIS FILE - Issue implementation workflow)
│   └── workflows/
│       └── quality-checks.yml           (CI/CD pipeline)
├── docs/
│   ├── implementation-planning/         (Issue step-by-step plans - Phase 1)
│   │   ├── issue-19-poc-crawl.md
│   │   ├── issue-22-mock-parsing-fix.md
│   │   └── issue-<N>-<kebab-case-title>.md  (NEW ISSUES - before implementation)
│   ├── dev-note/                        (Issue reference docs - Phase 2-3)
│   │   ├── issue-19-poc-evaluation-guide.md
│   │   ├── issue-19-success-criteria.md
│   │   ├── issue-23-copilot-structure-analysis.md
│   │   └── issue-<N>-<kebab-case-title>.md  (NEW INSIGHTS - discovered during implementation)
│   ├── ARCHITECTURE.md
│   ├── CRAWL.md
│   ├── PREPROCESS.md
│   └── ...
├── CLAUDE.md                            (Claude Code long-form guidance)
└── src/
    └── (Implementation files)
```

**File Location Key:**

| Location | Purpose | When Created | When Used |
|----------|---------|--------------|-----------|
| `.github/copilot-instructions.md` | Repository-wide Copilot instructions | Repository setup | All Copilot requests |
| `.github/instructions/issue-workflow.instructions.md` | Issue implementation workflow guide | Repository setup | Implementing GitHub Issues |
| `docs/implementation-planning/issue-<N>-*.md` | Step-by-step implementation plan | **Phase 1 (Planning)** | During implementation as checklist |
| `docs/dev-note/issue-<N>-*.md` | Research findings and reference docs | **Phase 2-3 (Implementation/Validation)** | Future reference, decisions, lessons learned |
| `CLAUDE.md` | Long-form guidance for Claude Code users | Repository setup | Claude IDE users |

---

## Examples

### Example: Issue #22 (Bug Fix)

```bash
# 1. Read issue
gh issue view 22

# 2. Plan
vim docs/implementation-planning/issue-22-mock-parsing-fix.md

# 3. Branch
git checkout -b fix/issue-22-mock-parsing

# 4. Implement
vim tests/test_assessment.py

# 5. Validate
uv run pre-commit run --all-files
uv run pytest tests/ -q

# 6. Commit
git add tests/test_assessment.py docs/implementation-planning/issue-22-mock-parsing-fix.md
git commit -m "Fix: Resolve mock response parsing in LLM assessment tests

Root cause: response.content was not properly iterable
Solution: Create text_block MagicMock and set response.content = [text_block]

Results:
- ✅ 3 tests now pass (previously xfailed)
- ✅ All 74 tests passing
- ✅ Mock matches real Anthropic response structure

Fixes #22"

# 7. Push & PR
git push -u origin fix/issue-22-mock-parsing
gh pr create --title "Fix #22: Resolve mock response parsing" \
  --body "Fixes #22

## Changes
- Fixed mock_anthropic fixture
- Removed xfail markers
- All 74 tests passing" \
  --base main

# 8. Monitor
gh pr checks

# 9. Merge (when approved)
gh pr merge --squash
```

### Example: Issue #19 (Feature)

```bash
# Similar flow, but:
git checkout -b feat/issue-19-poc-crawl
git commit -m "Feat: Implement Phase 1 POC crawl automation

Implements web crawler using Playwright for Phase 1 of issue #19.

Features:
- Crawl jobs from company URLs
- Extract via CSS selectors
- Rate limiting and retries
- Store to SQLite

See docs/implementation-planning/issue-19-poc-crawl-automation.md

Fixes #19"
```

---

## Best Practices

✅ **DO:**
- Keep commits atomic (one logical change per commit)
- Write clear, descriptive commit messages
- Include issue number in PR title and commit
- Test locally before pushing
- Update implementation plan as you work
- Run full validation suite before pushing

❌ **DON'T:**
- Mix multiple issues in one PR
- Commit unrelated changes
- Skip pre-commit validation
- Force push to remote (unless absolutely necessary)
- Leave debug print statements or temporary code
- Commit .env, secrets, or large files

---

## Troubleshooting

**"Pre-commit hooks fail"**
```bash
# Most auto-fix
uv run pre-commit run --all-files
# If mypy fails, fix manually
uv run mypy src/ tests/ --show-error-codes
```

**"Tests fail locally"**
```bash
# Ensure PYTHONPATH is set for src-layout
export PYTHONPATH="/path/to/ats-showcase/src:$PYTHONPATH"
uv run pytest tests/ -xvs   # Verbose, stop on first failure
```

**"GitHub Actions fails but tests pass locally"**
```bash
# Check Python version difference
python --version              # Local
# GitHub Actions uses 3.11 and 3.12
# Try with different version or check CI logs
gh pr checks    # View detailed logs
```

**"Can't create PR"**
```bash
# Ensure branch is pushed
git push -u origin <branch>
# Then create PR
gh pr create --title "..." --base main
```

---

## Resources

- **GitHub CLI Docs**: https://cli.github.com/manual/
- **Project Architecture**: See `CLAUDE.md` and `docs/ARCHITECTURE.md`
- **Pre-commit Hooks**: See `.pre-commit-config.yaml`
- **CI/CD Pipeline**: See `.github/workflows/quality-checks.yml`
- **Development Guide**: See `docs/CONVENTIONS.md`

---

## Related Documentation

This file is part of the ATS Showcase GitHub Copilot instruction system. For complete context:

**File Structure** (Official GitHub Copilot Patterns):
- **`.github/copilot-instructions.md`** - Repository-wide Copilot instructions (all users)
- **`.github/instructions/issue-workflow.instructions.md`** - This file (issue implementation workflow)
- **`CLAUDE.md`** - Long-form guidance for Claude Code users (IDE)

**See Also**:
- `.github/COPILOT-STRUCTURE-ANALYSIS.md` - Reference document on GitHub Copilot file structure standards
- `docs/dev-note/issue-23-copilot-structure-analysis.md` - Research findings on official Copilot structure
- `docs/implementation-planning/` - Implementation plans for specific GitHub Issues
- `docs/dev-note/` - Developer reference notes and research from completed issues

**Documentation Dual-Location Approach**:
- **`docs/implementation-planning/issue-<N>-*.md`** - Step-by-step plan (created Phase 1, before implementation)
- **`docs/dev-note/issue-<N>-*.md`** - Research and findings (created Phase 2-3, after discoveries)

---

**Version**: 1.0
**Last Updated**: 2026-05-29
**Status**: Active
**Scope**: All GitHub Issue implementations in this repository
