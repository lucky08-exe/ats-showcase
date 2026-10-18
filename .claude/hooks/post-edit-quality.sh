#!/bin/bash
# Post-edit quality checks for ATS Showcase
# Runs code quality tools on edited files: ruff, mypy, bandit, and relevant tests

set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Mode 1: PostToolUse hook (single file from stdin JSON)
# Extract file path from stdin hook payload (Write/Edit tool)
if [ -t 0 ]; then
    # stdin is a TTY, not piped - fallback to git diff
    CHANGED_FILES=$(git diff --name-only --diff-filter=ACM | grep '\.py$' || true)
    MODE="batch"
else
    # stdin has data - PostToolUse hook payload
    FILE=$(jq -r '.tool_input.file_path // .tool_response.filePath' 2>/dev/null || echo "")
    if [ -z "$FILE" ]; then
        # Could not extract file from JSON, fallback to git diff
        CHANGED_FILES=$(git diff --name-only --diff-filter=ACM | grep '\.py$' || true)
        MODE="batch"
    elif [[ "$FILE" == *.py ]]; then
        CHANGED_FILES="$FILE"
        MODE="single"
    else
        # Non-Python file, skip checks
        exit 0
    fi
fi

if [ -z "$CHANGED_FILES" ]; then
    echo "✓ No Python files to check"
    exit 0
fi

echo "🔍 Running quality checks on edited file(s)..."
echo "📝 Files:"
echo "$CHANGED_FILES" | sed 's/^/   /'

# Run ruff on changed files
echo ""
echo "▶ Running ruff (linting + formatting)..."
uv run ruff check --fix $CHANGED_FILES || true

# Run mypy on changed files
echo ""
echo "▶ Running mypy (type checking)..."
uv run mypy $CHANGED_FILES --ignore-missing-imports 2>/dev/null || true

# Run bandit on changed files (security)
echo ""
echo "▶ Running bandit (security scan)..."
uv run bandit -r $CHANGED_FILES 2>/dev/null || true

# Run relevant tests
if [ "$MODE" = "single" ]; then
    # Single file mode: extract module name from path
    for file in $CHANGED_FILES; do
        module=$(echo "$file" | sed 's|src/||; s|/|_|g; s|\.py$||')
        if [ -n "$module" ]; then
            echo ""
            echo "▶ Running tests for module: $module"
            uv run pytest tests/ -k "$module" -v --tb=short 2>/dev/null || true
        fi
    done
else
    # Batch mode: run all changed modules
    echo ""
    echo "▶ Running tests for changed modules..."
    TEST_ARGS=""
    for file in $CHANGED_FILES; do
        if [[ $file == src/* ]]; then
            module=$(echo "$file" | sed 's|src/||; s|/|_|g; s|\.py$||')
            TEST_ARGS="$TEST_ARGS -k $module"
        fi
    done

    if [ -n "$TEST_ARGS" ]; then
        uv run pytest tests/ $TEST_ARGS -v --tb=short 2>/dev/null || true
    else
        echo "✓ No module-specific tests to run"
    fi
fi

echo ""
echo "✓ Quality checks complete"
exit 0
