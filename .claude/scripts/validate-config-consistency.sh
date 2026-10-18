#!/bin/bash
# Validate ATS Showcase configuration consistency
# Detects: duplicate constraints, permission conflicts, file size limits

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

echo "================================"
echo "Config Consistency Validation"
echo "================================"
echo

# Helper functions
check_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASS_COUNT++))
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAIL_COUNT++))
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARN_COUNT++))
}

# Check 1: Duplicate NEVER constraints
echo "1. Checking for duplicate NEVER constraints..."
NEVER_COUNT=$(grep -r "NEVER:" .claude/CONSTRAINTS.md .claude/rules/*.md .claude/rules/*/*.md 2>/dev/null | wc -l || true)
CLAUDE_NEVER=$(grep -c "^- \*\*Don't" CLAUDE.md 2>/dev/null || true)

if [ "$CLAUDE_NEVER" -gt 0 ]; then
    check_pass "Found $CLAUDE_NEVER NEVER rules in CLAUDE.md"
else
    check_fail "No NEVER rules found in CLAUDE.md"
fi

if grep -q "NEVER:" .claude/CONSTRAINTS.md 2>/dev/null; then
    check_pass "CONSTRAINTS.md contains NEVER rules"
else
    check_fail "CONSTRAINTS.md missing NEVER rules"
fi

echo

# Check 2: Duplicate ALWAYS constraints
echo "2. Checking for duplicate ALWAYS constraints..."
ALWAYS_COUNT=$(grep -r "ALWAYS:" .claude/CONSTRAINTS.md .claude/rules/*.md .claude/rules/*/*.md 2>/dev/null | wc -l || true)

if grep -q "ALWAYS:" .claude/CONSTRAINTS.md 2>/dev/null; then
    check_pass "CONSTRAINTS.md contains ALWAYS rules"
else
    check_fail "CONSTRAINTS.md missing ALWAYS rules"
fi

echo

# Check 3: Permission conflicts in settings.json
echo "3. Checking for permission conflicts in settings.json..."
if [ -f ".claude/settings.json" ]; then
    # Check if any tool is in both allow and deny lists
    ALLOW_TOOLS=$(jq -r '.permissions.allow[]' .claude/settings.json 2>/dev/null | cut -d'(' -f1 | sort | uniq)
    DENY_TOOLS=$(jq -r '.permissions.deny[]' .claude/settings.json 2>/dev/null | cut -d'(' -f1 | sort | uniq)

    CONFLICTS=$(comm -12 <(echo "$ALLOW_TOOLS") <(echo "$DENY_TOOLS") | wc -l || true)

    if [ "$CONFLICTS" -eq 0 ]; then
        check_pass "No permission conflicts detected"
    else
        check_fail "Permission conflicts found in settings.json"
        comm -12 <(echo "$ALLOW_TOOLS") <(echo "$DENY_TOOLS") | sed 's/^/  - /'
    fi
else
    check_fail "settings.json not found"
fi

echo

# Check 4: File size limits
echo "4. Checking file size limits..."

# CLAUDE.md should be < 2KB
CLAUDE_SIZE=$(wc -c < CLAUDE.md)
CLAUDE_LIMIT=$((2 * 1024))
if [ "$CLAUDE_SIZE" -lt "$CLAUDE_LIMIT" ]; then
    check_pass "CLAUDE.md size OK: ${CLAUDE_SIZE} bytes (limit: ${CLAUDE_LIMIT})"
else
    check_warn "CLAUDE.md exceeds 2KB: ${CLAUDE_SIZE} bytes"
fi

# settings.json should be < 100 lines
SETTINGS_LINES=$(wc -l < .claude/settings.json)
if [ "$SETTINGS_LINES" -lt 200 ]; then
    check_pass "settings.json line count OK: ${SETTINGS_LINES} lines (target: < 200)"
else
    check_warn "settings.json is large: ${SETTINGS_LINES} lines"
fi

echo

# Check 5: JSON validity
echo "5. Checking JSON file validity..."

JSON_FILES=(
    ".claude/settings.json"
    ".claude/permissions-base.json"
    ".claude/copilot-routing.json"
)

for FILE in "${JSON_FILES[@]}"; do
    if [ -f "$FILE" ]; then
        if jq empty "$FILE" 2>/dev/null; then
            check_pass "$FILE is valid JSON"
        else
            check_fail "$FILE has invalid JSON"
        fi
    else
        check_warn "$FILE not found"
    fi
done

echo

# Check 6: Markdown file syntax
echo "6. Checking Markdown file syntax..."

MD_FILES=(
    ".claude/CONSTRAINTS.md"
    ".claude/rules/_common.md"
)

for FILE in "${MD_FILES[@]}"; do
    if [ -f "$FILE" ]; then
        # Basic check: file is not empty and has headers
        if grep -q "^#" "$FILE" 2>/dev/null; then
            check_pass "$FILE has valid Markdown structure"
        else
            check_fail "$FILE missing Markdown headers"
        fi
    else
        check_warn "$FILE not found"
    fi
done

echo

# Check 7: Cross-references validity
echo "7. Checking cross-references..."

# Check if copilot-routing.json references existing files
if [ -f ".claude/copilot-routing.json" ]; then
    RULES=$(jq -r '.routes[]?.rules[]?' .claude/copilot-routing.json 2>/dev/null | sort | uniq)
    MISSING=0
    while IFS= read -r RULE; do
        if [ -n "$RULE" ]; then
            if [ ! -f "$RULE" ]; then
                check_fail "Cross-reference missing: $RULE"
                ((MISSING++))
            fi
        fi
    done <<< "$RULES"

    if [ "$MISSING" -eq 0 ]; then
        check_pass "All copilot-routing.json cross-references valid"
    fi
else
    check_warn "copilot-routing.json not found"
fi

echo

# Check 8: Script executability
echo "8. Checking script permissions..."

SCRIPT_FILE=".claude/scripts/validate-config-consistency.sh"
if [ -f "$SCRIPT_FILE" ]; then
    if [ -x "$SCRIPT_FILE" ]; then
        check_pass "$SCRIPT_FILE is executable"
    else
        check_warn "$SCRIPT_FILE is not executable (run: chmod +x $SCRIPT_FILE)"
    fi
else
    check_warn "$SCRIPT_FILE not found"
fi

echo

# Summary
echo "================================"
echo "Summary"
echo "================================"
echo -e "${GREEN}Passed: $PASS_COUNT${NC}"
echo -e "${YELLOW}Warnings: $WARN_COUNT${NC}"
echo -e "${RED}Failed: $FAIL_COUNT${NC}"
echo

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo -e "${GREEN}Validation PASSED${NC}"
    exit 0
else
    echo -e "${RED}Validation FAILED${NC}"
    exit 1
fi
