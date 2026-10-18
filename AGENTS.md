# Agent Roles & Governance

Multi-agent coordination framework for ATS Showcase: role boundaries + escalation.

---

## Agent Roles

### Architect/Planner
- Draft implementation plans (tasks.md)
- Design module boundaries + APIs
- Write architectural decisions
- ✅ Read codebase, write tasks.md + docs/
- ❌ FORBIDDEN: Write production code

### Builder/Implementer
- Implement features, write tests
- Create commits
- Flag design issues to Architect
- ✅ Write src/, tests/, run tests
- ❌ FORBIDDEN: Modify tasks.md, CLAUDE.md, AGENTS.md, skip tests

### Reviewer/Tester
- Verify implementation vs tasks.md
- Run full test suite (pytest, coverage, lint)
- Check test coverage, code quality
- ✅ Read codebase, run verification commands
- ❌ FORBIDDEN: Modify production code, merge without human approval

---

## Claude Model Configuration

**Source of Truth:** `.claude/agents/{role}.md` frontmatter
**Global Default:** `.claude/settings.json` → `claude-haiku-4-5-20251001`

| Role | Model | Budget | Source |
|------|-------|--------|--------|
| **Architect** | claude-sonnet-5 | Deep planning | `.claude/agents/architect.md` |
| **Builder** | claude-haiku-4-5 | Synthesis | `.claude/agents/builder.md` |
| **Reviewer** | claude-haiku-4-5 | Code review | `.claude/agents/reviewer.md` |
| **Slop Hunter** | claude-sonnet-5 | Dead-code triage (report only) | `.claude/agents/slop-hunter.md` |
| **Cleanup Builder** | claude-haiku-4-5 | Approved ≤2-file cleanup | `.claude/agents/cavecrew-builder.md` |
| **Cleanup Reviewer** | claude-haiku-4-5 | Blast-radius gatekeeper (max 4 loops) | `.claude/agents/cavecrew-reviewer.md` |
| *Default* | haiku-4-5 | (all others) | `.claude/settings.json` |

**Precedence:** Agent `.md` frontmatter > Global settings.json

---

## Two-Gate System

All multi-file changes require **Gate 1 (Plan Review)** + **Gate 2 (Evidence-Based Verification)** before merge.

### Gate 1: Plan Mode Review
Before implementing cross-file changes:
1. Architect drafts tasks.md with API contracts
2. Architect sketches affected files (list + scope)
3. Human/team reviews and approves

Triggered by: module interface changes, config files, CLI changes, schema migrations.

### Gate 2: Evidence-Based Verification
Reviewer verifies with local tools (not predictions): pytest ✅, ruff/black ✅, mypy ✅, build ✅

---

## Handover Protocol

```
ARCHITECT → BUILDER → REVIEWER → HUMAN (merge)
```

---

## Directory Scoping & Skill Discovery

`.claude/rules/*.md` phase guidance • `.claude/agents/*.md` role overrides • `.claude/skills/<name>/SKILL.md` (lazy-loaded) • `.github/copilot/rules/` • `.github/instructions/` CLI docs. **Priority**: Agent `.md` > `.claude/settings.json` > defaults.

---

## Claude ↔ Copilot Handoff

Copilot: single-file edits. Claude Code: multi-file refactors (>3 files), cross-module changes. Escalate if >3 files or touches `.claude/`, `AGENTS.md`, `CLAUDE.md`.


---

## Permission Matrix

| Role | tasks.md | src/ | tests/ | docs/ | CLAUDE.md | .claude/ |
|------|----------|------|--------|-------|-----------|----------|
| Architect | W | R | R | W | R | R |
| Builder | R | W | W | R | ❌ | ❌ |
| Reviewer | R | R | R | W | R | R |
| Human | R | R | R | R | W | W |

**W** = write, **R** = read, **❌** = denied. Configuration in `.claude/agents/` overrides this matrix.

---

## Code Graph Tooling (Issue #325)

Architect uses `code-review-graph` (MCP) for structural/blast-radius context before wide scans — full detail + decision record: [.claude/README.md](.claude/README.md#code-graph-tooling-issue-325-upgraded-328).

---

**Related:** [CLAUDE.md](CLAUDE.md) • [DESIGN.md](DESIGN.md) • [multi-agent.md](.claude/rules/multi-agent.md) • [.claude/README.md](.claude/README.md)

**Last Updated:** 2026-10-14 (Issue #626: trim AGENTS.md to context budget)
