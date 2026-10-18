# Custom Skills Index

Indexed catalog of Claude Code skills for ATS Showcase. Each skill automates a phase of the workflow.

---

## Skills by Phase

| Skill | Phase(s) | Description | Link |
|-------|----------|-------------|------|
| **Crawl + Preprocess** | crawl, preprocess | Fetch job listings via Playwright and prepare for assessment (crawl + preprocess) | [.claude/skills/crawl-jobs/SKILL.md](.claude/skills/crawl-jobs/SKILL.md) |
| **Review + Assess** | verify, assess | Verify extracted jobs and run Claude assessment for CV fit scoring | [.claude/skills/assess-jobs/SKILL.md](.claude/skills/assess-jobs/SKILL.md) |
| **Pre-Commit Enforce** | meta | Enforce feature branch workflow by blocking commits to protected branches | [.claude/skills/pre-commit-enforce/SKILL.md](.claude/skills/pre-commit-enforce/SKILL.md) |

---

## Skill Template

To add a new skill, copy [.claude/skills/TEMPLATE.md](.claude/skills/TEMPLATE.md) and fill in the YAML metadata:

```yaml
name: skill-name
description: One-line description
dependencies:
  - "package >= version"
phases:
  - phase_name
cost_estimate: "$cost (or $0.00 for local)"
triggers:
  - "user phrase 1"
  - "user phrase 2"
execution: atomic | streaming
allowed_tools:
  - Read
  - Write
  - Bash(pattern)
```

Then add a row to the table above with link to your new SKILL.md.

---

## Discovery

Skills are auto-discovered by Claude Code when invoked by trigger phrases or via `/skill <name>` command. See each SKILL.md's `triggers` section for available phrases.

---

**Last Updated:** 2026-08-16
