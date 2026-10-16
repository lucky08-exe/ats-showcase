# Cavecrew Shared Rules

Shared guidance for the `caveman:cavecrew-builder` and `caveman:cavecrew-reviewer`
plugin agents. Content only: no enforcement lives here.

---

## Tool Usage

**Code graph (structural / blast-radius):** `code-review-graph` (MCP, project-isolated DB).
Use before wide Grep/Glob scans. Full setup and command list:
[.claude/README.md](../README.md#code-graph-tooling-issue-325-upgraded-328).

- `code-review-graph detect-changes --brief` — risk-scored diff summary
- `code-review-graph impact --files <paths>` — blast radius of a change
- `code-review-graph dead-code` — orphan check

**Knowledge graph (concept navigation):** `graphify` (`graphify-out/graph.json`).
Use `graphify query|path|explain` for scoped subgraphs. Setup:
[.claude/README.md](../README.md#graphify-issue-325--revisited).

Phase-level use of these tools: [multi-agent.md](multi-agent.md#code-graph-tooling-issue-325-328).

---

## False-Positive Avoidance

Before flagging any symbol as dead, check the exclusions in
[slop-hunter.md](../agents/slop-hunter.md#exclusions-never-flag-as-dead).

---

## Severity Levels (cavecrew-reviewer)

The reviewer's severity format is defined in
[cavecrew-reviewer.md](../agents/cavecrew-reviewer.md#severity-format). It has three
tiers only: `🚨 Critical`, `⚠️ Warning`, `ℹ️ Info`. There is no orange tier; this
matches the sibling repo's decision. Do not add intermediate levels.

---

## Scope

- Builders edit at most 2 files per execution. See
  [cavecrew-builder.md](../agents/cavecrew-builder.md) for the scope limit.
- Reviewers loop at most 4 times before escalating. See
  [cavecrew-reviewer.md](../agents/cavecrew-reviewer.md#loop-control).

Governance and role boundaries: [AGENTS.md](../../AGENTS.md).

---

**Last Updated:** 2026-10-15 (Issue #654: T6 shared cavecrew rules)
