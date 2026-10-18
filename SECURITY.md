# Security Policy

## Reporting Vulnerabilities

**Please do not publicly disclose security vulnerabilities** found in ATS Showcase. Instead:

1. **Email Security Concern**: Send an email to the repository maintainers describing the vulnerability
2. **Include Details**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if you have one)
3. **Expect Response**: Maintainers will respond within 48 hours to acknowledge receipt
4. **Collaborative Fix**: Work with maintainers to develop and test a fix
5. **Coordinated Disclosure**: We'll release a security update before public disclosure

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x | ✅ Yes (current development) |
| < 1.0 | ❌ No (pre-release) |

## Security Best Practices

### For Contributors

- **Never commit secrets**: API keys, tokens, passwords must never be in version control
- **Use `.env` files**: Store sensitive data in `.env` (never commit `.env`, only `.env.example`)
- **Validate input**: All user input validated with Pydantic models before processing
- **SQL injection**: All database queries use parameterized statements (SQLite with Pydantic)
- **Error handling**: Error messages must not expose sensitive information
- **Dependencies**: Keep dependencies up-to-date; Dependabot will alert on vulnerabilities

### For Users

- **API Keys**: Store `ANTHROPIC_API_KEY` in environment variables, never hardcode
- **Database**: Secure the `ats_playground.db` file if it contains sensitive job data
- **User CVs**: Treat CV data as private; consider encryption at rest
- **Logs**: Review logs (`logs/app.log`) for sensitive information before sharing

## Security Controls

### Branch Protection
- Main branch requires 2 code reviews before merge
- All automated checks must pass (tests, linting, type checking, security scans)
- Force pushes disabled on main

### Secret Scanning
- GitHub secret scanning enabled to detect accidentally committed credentials
- Pre-commit hooks check for common secret patterns
- Immediate remediation if secrets are exposed

### Dependency Scanning
- Dependabot monitors all dependencies for known vulnerabilities
- Automated PRs for security updates and version upgrades
- Weekly review and merge of dependency updates

### Code Scanning
- CodeQL static analysis runs on all pull requests
- Bandit security linting checks for common Python security issues
- All high-severity findings must be resolved before merge

### Access Control
- Limited collaborator access with appropriate roles
- Audit logging enabled for repository access
- Regular access reviews and cleanup of inactive contributors

## Known Issues & Mitigations

See [KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) for documented security considerations and mitigations.

## Security Standards

ATS Showcase follows these security standards and best practices:

- **OWASP Top 10**: https://owasp.org/www-project-top-ten/
- **Python Security**: https://python.readthedocs.io/en/stable/library/security_considerations.html
- **CWE/SANS Top 25**: https://cwe.mitre.org/top25/

## Incident Response

If a security incident is suspected:

1. **Contain**: Stop ongoing operations if necessary
2. **Alert**: Notify maintainers immediately
3. **Investigate**: Document what happened
4. **Fix**: Develop and test a remediation
5. **Disclose**: Follow responsible disclosure timeline
6. **Review**: Post-incident analysis to prevent recurrence

See [INCIDENT_RESPONSE.md](docs/INCIDENT_RESPONSE.md) for detailed procedures.

## Environment Variables (Secrets)

**Keep these secret** — never commit to version control:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...  # Claude API key

# Optional
DATABASE_PATH=data/ats_playground.db
SPACY_MODEL=en_core_web_md
LOG_LEVEL=INFO
```

See `.env.example` for all available variables.

## Dependency Management

Dependencies are managed with `uv`:

```bash
# Check for vulnerable packages
uv pip audit

# Update all packages safely
uv sync --upgrade

# Review Dependabot alerts
# See GitHub Settings > Code security & analysis > Dependabot alerts
```

## Security Review Checklist

Before submitting a PR, verify:

- [ ] No secrets committed (run `git-secrets --scan`)
- [ ] No hardcoded credentials in code
- [ ] All user input validated with Pydantic
- [ ] Database queries use parameterized statements
- [ ] Error messages don't leak sensitive info
- [ ] All tests pass locally
- [ ] Type checking passes (`mypy`)
- [ ] Linting passes (`ruff`, `black`)
- [ ] No new high-risk dependencies

## Questions?

For security questions or concerns, contact the maintainers privately rather than opening public issues.

---

**Last Updated**: 2026-05-19
**Status**: Initial Security Policy
**Next Review**: 2026-08-19 (quarterly)
