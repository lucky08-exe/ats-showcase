---
name: gate-enforcer
description: Enforce pre-commit gates (Gate 1 plan review) and verification checkpoints (Gate 2 evidence-based)
model: claude-sonnet-5 # Architect-level reasoning for gate validation
tools:
  - Read
  - Grep
  - Bash
permissions:
  bash:
    ask: ["*"] # All operations require human review (verification gate)
---

# Gate Enforcement Policy

Automated enforcement of Gate 1 & Gate 2 quality checkpoints for ATS Playground multi-file changes.

## Gate 1: Plan Review

**Trigger:** Multi-file changes (≥2 files across different directories or governance files)

**Requirements:**
- [ ] Implementation plan document exists: `docs/implementation-planning/issue-<N>-*.md`
- [ ] Plan includes:
  - Issue description and context
  - Investigation checklist (completed)
  - File modification list with rationale
  - Success criteria (measurable)
- [ ] Human approval on GitHub (code review or issue comment)

**Automated Check:**
```bash
# Verify plan existence
if git diff --name-only | wc -l >= 2; then
  if [ ! -f "docs/implementation-planning/issue-*.md" ]; then
    echo "Error: Gate 1 failed - plan document missing"
    exit 1
  fi
fi
```

**Enforcement Point:** Pre-commit hook blocks commits violating Gate 1

---

## Gate 2: Evidence-Based Verification

**Trigger:** All PRs and branch commits

**Required Evidence:**
- ✅ Type checking passes: `mypy src/ tests/` (0 errors)
- ✅ Linting passes: `ruff check src/ tests/` (0 errors)
- ✅ Tests passing: `pytest tests/ -v` (all pass or xfail expected)
- ✅ Code coverage maintained: No decrease in existing coverage
- ✅ CI workflow success: All GitHub Actions checks green

**Automated Check:**
```yaml
# .github/workflows/quality-checks.yml
- name: Type Check
  run: uv run mypy src/ tests/

- name: Lint
  run: uv run ruff check src/ tests/

- name: Tests
  run: uv run pytest tests/ -v --cov=src

- name: Coverage
  run: |
    previous=$(cat .coverage.baseline || echo "100")
    current=$(uv run coverage report --format=json | jq '.total_coverage')
    if (( $(echo "$current < $previous" | bc -l) )); then
      echo "Coverage regression: $current < $previous"
      exit 1
    fi
```

**Enforcement Point:** GitHub Actions CI blocks merge if Gate 2 fails

---

## Permission Enforcement

**Files Protected from Builder Modification:**
- `AGENTS.md` - Role governance
- `CLAUDE.md` - Project guidance
- `.claude/agents/**` - Agent configuration
- `.claude/rules/**` - Phase-specific rules
- `.claude/skills/**` - Skill definitions
- `.claude/settings.json` - Global configuration

**Enforcement Mechanism:** Two layers in the harness. Agent frontmatter `permissions:` blocks are not read by Claude Code and are not enforcement.

1. **`.claude/settings.json` `permissions.deny`** - `Edit(...)` and `Write(...)` rules for each protected path above. Applies to every agent, including plugin subagents.
2. **`.claude/hooks/protected-file-guard.sh`** - PreToolUse hook (matcher `Edit|Write`). Denies the same paths when `agent_type` is a known subagent type. Allows when `agent_type` is empty (human main session) or unrecognized, and never blocks the `SubagentHandback` pseudo-tool. Fails open on malformed input.

If a subagent attempts to modify a protected file:
- Tool layer denies the write (permissions.deny, then the hook)
- Fallback: Pre-commit hook catches and rejects commit
- Escalation: Human approval required (Architect or Human role)

Protected files are edited by a human on a feature branch, via a reviewed PR.

---

## Cost Policy

Model selection by role:
- **Architect**: Sonnet (~$3/$15 per 1M tokens) - High reasoning for planning
- **Builder**: Sonnet (~$3/$15 per 1M tokens) - Complex synthesis
- **Reviewer**: Haiku (~$0.80/$4 per 1M tokens) - Cost-efficient QA

**Projected savings**: ~60% tokens for review phase by using Haiku

---

## Related

- **AGENTS.md**: Role definitions and governance framework
- **Settings**: `.claude/settings.json` (`permissions.deny`)
- **Protected-file hook**: `.claude/hooks/protected-file-guard.sh`
- **CI/CD Pipeline**: `.github/workflows/quality-checks.yml` (Gate 2 automation)

---

**Status**: Enforcement active
**Last Updated**: 2026-08-06
**Related Issue**: #235 (Agent configuration review)
