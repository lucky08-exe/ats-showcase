# PLUGIN.md

GitHub Copilot CLI plugin configuration for ATS Showcase.

## Two-System Architecture

Unlike Claude Code (which uses `.claude/settings.json`), GitHub Copilot CLI requires skills to be installed as **plugins** via the CLI plugin system.

### Claude Code Skills
- Defined in: `.claude/settings.json`
- Registration: `skillOverrides` array
- Installation: Automatic (file-based)
- When available: During Code sessions

### GitHub Copilot CLI Skills
- Delivered via: GitHub plugin repositories
- Installation: Manual (`gh copilot -- plugin install`)
- Prerequisites: GitHub Copilot CLI installed + authenticated
- When available: During CLI sessions

## Installing ATS Showcase Plugin

To enable ATS Showcase skills in GitHub Copilot CLI sessions:

```bash
# Install the plugin
gh copilot -- plugin install pluto-atom-4/copilot-plugin-ats-playground

# Verify installation
gh copilot -- plugin list

# Start a session
gh copilot

# In the session, use skills:
> /ats-preprocessing --help
> /ats-assessment --cv data/cv.json
> /ats-nlp-setup --model en_core_web_md
```

## Plugin Repository

The `copilot-plugin-ats-playground` repository contains:
- Plugin manifest (`plugin.json`)
- Skill definitions for:
  - `ats-nlp-setup`: Configure NLP models
  - `ats-preprocessing`: Preprocess job postings
  - `ats-assessment`: Assess job matches
- Usage examples and troubleshooting
- Full documentation

See: https://github.com/pluto-atom-4/copilot-plugin-ats-playground

## Important Note

This is separate from Claude Code configuration. Both systems can work together:
- **Claude Code**: Use skills defined in `.claude/settings.json`
- **GitHub Copilot CLI**: Use skills installed as plugins
