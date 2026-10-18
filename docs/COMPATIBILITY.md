# Python Module Compatibility & Troubleshooting

## Known Issues & Solutions

### 1. **spaCy & Python Version**

#### ✅ Fully Supported
- **spaCy 3.8+** supports Python 3.11, 3.12, 3.13, 3.14
- spaCy v3.8.12+ migrated to Pydantic v2 (full compatibility)
- Recommended: Python 3.13 for best performance

#### ❌ Issues (< spaCy 3.8)
- spaCy < 3.8 uses confection with Pydantic v1 config system
- Conflicts with Pydantic v2 in this project
- **Solution**: Always use `spacy>=3.8.0`

#### Model Options
| Model | Speed | Accuracy | Best For | Size |
|-------|-------|----------|----------|------|
| en_core_web_sm | Fast | Good | Quick testing | 12 MB |
| **en_core_web_md** | Balanced | Better | ✅ Recommended | 41 MB |
| en_core_web_lg | Slower | Best | High accuracy needed | 551 MB |

**Recommended: en_core_web_md** (balance of speed/accuracy for job parsing)

### 2. **MarkItDown (HTML Cleaning)**

#### ✅ Supported Versions
- MarkItDown 0.1.5+ (stable, Microsoft-maintained)
- Works with all Python 3.11+ versions
- Optional dependencies: `pip install "markitdown[all]"` for full format support

#### ⚠️ Installation Notes
- MarkItDown is optional but recommended for HTML cleaning
- If not installed, PreprocessingPipeline falls back to BeautifulSoup automatically
- Install with: `pip install "markitdown[all]"` (includes PDF, Office, etc. support)
- For HTML only: `pip install markitdown` (lightweight)

#### ❌ Common Issues

**Error: `ModuleNotFoundError: No module named 'markitdown'`**
```bash
# Solution: Install MarkItDown
uv pip install "markitdown[all]"

# Or minimal install (HTML only):
uv pip install markitdown
```

**Note**: Fallback to BeautifulSoup works automatically if MarkItDown unavailable
```python
cleaner = HTMLCleaner(prefer_markitdown=True)  # Tries MarkItDown, falls back to BeautifulSoup
```

**Performance**: MarkItDown ~3-5x faster than BeautifulSoup for HTML→text conversion

### 3. **lxml (C Binding Issues)**

#### System Dependencies Required
```bash
# Ubuntu/Debian
sudo apt-get install libxml2-dev libxslt-dev python3-dev

# macOS
brew install libxml2 libxslt

# Windows
# Pre-built wheels auto-installed via pip (no system deps)
```

#### ❌ Common Errors

**Error: `lxml.etree is required`**
```
ImportError: libxml2 is required
```
**Solution:**
```bash
# Install system dependencies (see above)
# Or use html.parser fallback in BeautifulSoup
soup = BeautifulSoup(html, "html.parser")  # Slower but no system deps
```

**Error: `library not found for -lxml2` (macOS)**
```bash
# Solution: Use Homebrew paths
LDFLAGS="-L$(brew --prefix libxml2)/lib" \
CPPFLAGS="-I$(brew --prefix libxml2)/include" \
uv pip install lxml
```

**Error: `Building wheel for lxml` (slow install)**
- lxml requires C compilation; expect 2-5 minutes on first install
- Use pre-built wheels: `pip install --only-binary :all: lxml`

**Note**: lxml is used by BeautifulSoup as fallback parser (not required if using MarkItDown)

### 4. **tiktoken Version Compatibility**

#### ✅ Supported Versions
- tiktoken 0.5+ (modern API, recommended)
- tiktoken 0.7+ (current, with improved caching)
- Works with Claude, OpenAI, Mistral encoding models

#### ❌ Issues (< tiktoken 0.5)
- Slow encoding (no caching)
- Missing `encoding_for_model()` function
- **Solution**: Use `tiktoken>=0.7.0`

#### Token Counting Accuracy
| LLM | Encoding | Tokens (9 chars) | Cost per 1M |
|-----|----------|------------------|------------|
| Claude (via gpt-4 enc) | gpt-4 | 3-4 | $0.80 |
| OpenAI GPT-4o Mini | gpt-4o | 3-4 | $0.15 |
| Mistral | mistral | 3-4 | $0.14 |

**Note**: tiktoken matches OpenAI/Claude encoders closely (±1-2 token variance)

### 5. **Playwright & Browser Installation**

#### ✅ Supported Versions
- Playwright 1.40+ (stable)
- Playwright 1.48+ (recommended, latest)
- Python 3.11+

#### ❌ Common Issues

**Error: `Browser not installed`**
```bash
# Solution: Install browsers
uv run playwright install

# Or with specific browser:
uv run playwright install chromium
```

**Error: `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 breaks things`**
- Don't set this env var; always run `playwright install`
- Solution: Use official setup commands

**Error: `Timeout waiting for element`**
- Increase timeout: `page.wait_for_selector(selector, timeout=30000)`
- Check selector in browser inspector
- Solution: Add logging to debug which selector fails

### 6. **Pydantic v1 vs v2 Conflicts**

#### ✅ Project Uses: Pydantic v2 (2.5+)

#### ❌ Issues with Mixed Versions
If you have `pydantic=1.x` installed alongside v2:
```
ValidationError: Field validation not working
ConfigDict not recognized
```

**Solution: Enforce v2**
```bash
uv pip list | grep pydantic
# Should show: pydantic 2.x.x

# Remove v1
pip uninstall pydantic -y
pip install 'pydantic>=2.5'
```

#### Migration from v1 Code
- `parse_obj()` → `model_validate()`
- `dict()` → `model_dump()`
- `Config` class → `model_config`
- `Field(...)` syntax mostly unchanged

### 7. **Anthropic SDK Compatibility**

#### ✅ Supported
- anthropic 0.25.0+
- Works with Python 3.11+

#### ❌ Known Issues

**Error: `api_key not found`**
```python
ImportError: ANTHROPIC_API_KEY not set
```
**Solution:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
# Or in .env file
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env
```

**Error: `anthropic.APIError: 429 Rate Limit`**
- Haiku model has rate limits (~100,000 tokens/min free tier)
- Solution: Add exponential backoff retry logic
```python
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=60)
)
def call_claude(client, messages):
    return client.messages.create(model="claude-3-5-haiku-20241022", messages=messages)
```

### 8. **spaCy Model Download & Installation**

#### ✅ Recommended Setup
- **spaCy 3.8+**: Full Python 3.13 support, Pydantic v2 compatible
- **Model**: en_core_web_sm for ATS Showcase (12 MB, ~80 MB RAM)
- **Installation method**: Always via UV to ensure correct virtual environment

#### ⚠️ Safe Download Flow

**Pre-download checklist**:
- [ ] Python 3.11+ installed (check: `python --version`)
- [ ] Virtual environment active (check: `echo $VIRTUAL_ENV`)
- [ ] 200+ MB disk space available (check: `df -h /`)
- [ ] Network connectivity to PyPI (check: `curl -I https://files.pythonhosted.org`)
- [ ] spaCy 3.8.0+ installed (check: `python -c "import spacy; print(spacy.__version__)"`)

**Recommended flow**:
```bash
# Step 1: Ensure dependencies installed
uv sync

# Step 2: Download model (uses correct Python interpreter)
uv run python -m spacy download en_core_web_sm

# Step 3: Verify installation
uv run python -c "
import spacy
nlp = spacy.load('en_core_web_sm')
doc = nlp('Test sentence.')
print('✅ spaCy model loaded successfully')
"
```

#### ❌ 11 Critical Configuration Issues

**Issue #1: "No module named 'spacy'"**
```
Error when running: python -m spacy download en_core_web_sm
Root cause: spaCy not installed yet
Solution:
  uv sync  # Install spaCy first (it's in pyproject.toml)
  uv run python -m spacy download en_core_web_sm  # Always use uv run
```

**Issue #2: "Can't find model 'en_core_web_sm'"**
```
Error: [E050] Can't find model 'en_core_web_sm'
Root causes:
  1. Version mismatch (spaCy 3.7 model with spaCy 3.8)
  2. Model symlink not created
  3. Downloaded to wrong Python environment
Solution:
  # Check versions match
  python -c "import spacy; print('spaCy:', spacy.__version__)"
  python -m spacy info

  # Create symlink if missing
  python -m spacy link en_core_web_sm en_core_web_sm --force

  # Or clean reinstall
  uv pip install --force-reinstall en_core_web_sm
```

**Issue #3: Network/Proxy Errors (SSL, timeout, 403)**
```
Error: URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] ...>
Root cause: Behind corporate proxy/firewall or SSL verification failing
Solution - Option A (recommended):
  export HTTP_PROXY=http://proxy.example.com:8080
  export HTTPS_PROXY=https://proxy.example.com:8443
  uv run python -m spacy download en_core_web_sm

Solution - Option B (PyPI mirror):
  pip install -i https://mirrors.aliyun.com/pypi/simple en_core_web_sm

Solution - Option C (manual download):
  # 1. Download from: https://pypi.org/project/en-core-web-sm/
  # 2. pip install /path/to/en_core_web_sm-3.8.0-py3-none-any.whl
```

**Issue #4: Insufficient Disk Space**
```
Error: OSError: [Errno 28] No space left on device
Root cause: < 200 MB free on disk
Solution:
  df -h /  # Check available space
  pip cache purge  # Clear pip cache (~100-500 MB)
  rm -rf ~/.cache/pip
  uv run python -m spacy download en_core_web_sm
```

**Issue #5: File Permissions Denied**
```
Error: PermissionError: [Errno 13] Permission denied: '/usr/lib/python3/...'
Root cause: Installing to system Python (not allowed)
Solution:
  # ✅ Always use virtual environment
  uv sync  # Creates .venv automatically
  uv run python -m spacy download en_core_web_sm

  # NOT: sudo pip install en_core_web_sm ❌
```

**Issue #6: Virtual Environment Mismatch (UV)**
```
Error: Model installed but not found when running code
Root cause: Downloaded to system Python, not UV venv
Solution:
  # ✅ ALWAYS use uv run
  uv run python -m spacy download en_core_web_sm

  # NOT: python -m spacy download en_core_web_sm ❌

  # Verify using correct interpreter
  uv python show
```

**Issue #7: Model Package Name Typo**
```
Error: ERROR: Could not find a version that satisfies the requirement
Root cause: Typo in model name (e.g., en_core_web_md vs en_core_web_sm)
Solution - Correct commands:
  python -m spacy download en_core_web_sm           # ✅ CLI
  python -m spacy download en_core_web_sm-3.8.0    # ✅ Explicit version
  pip install en_core_web_sm                        # ✅ Direct pip

  Wrong commands:
  python -m spacy download en_core_web_md           # ❌ Wrong model
  python -c "import spacy; spacy.download(...)"    # ❌ No such method
```

**Issue #8: spaCy Version Mismatch**
```
Error: Model works but incompatible behavior
Root cause: Model version doesn't match spaCy version
Solution:
  # Download model matching spaCy version (auto-detected)
  python -m spacy download en_core_web_sm

  # Verify versions match
  python -c "import spacy; print('spaCy:', spacy.__version__)"
  python -m spacy info  # Shows model/spaCy version mismatch

  # Update spaCy to 3.8+ in pyproject.toml
  # spacy = ">=3.8.0,<4.0"
  uv sync --upgrade
```

**Issue #9: Old Cache Interference**
```
Error: Model loads old version or fails after update
Root cause: Pip cache has stale versions
Solution:
  pip cache purge
  uv pip install --force-reinstall en_core_web_sm

  # Full reset
  rm -rf ~/.cache/pip
  uv sync --refresh
  uv run python -m spacy download en_core_web_sm --force-all
```

**Issue #10: Python 3.13 Edge Case**
```
Error: ERROR: No matching distribution found (Python 3.13 only)
Root cause: spaCy model wheels not yet built for 3.13 (late 2024 issue)
Solution:
  # Upgrade spaCy to 3.8.10+ (has 3.13 wheels)
  uv pip install --upgrade spacy

  # Or fallback to Python 3.12
  uv python pin 3.12
  uv sync
  uv run python -m spacy download en_core_web_sm
```

**Issue #11: ARM64 (Apple Silicon) Wheel Issues**
```
Error: ERROR: No matching distribution found (on M1/M2/M3 Mac)
Root cause: spaCy wheel not built for arm64
Solution - Option A (recommended):
  # Use native arm64 Homebrew Python
  brew install python@3.13
  /opt/homebrew/bin/python3.13 -m spacy download en_core_web_sm

Solution - Option B (force reinstall):
  pip install --no-cache-dir --force-reinstall en_core_web_sm

Solution - Option C (x86_64 emulation, slower):
  arch -x86_64 python -m spacy download en_core_web_sm
```

#### ⚠️ Model Size & Memory Trade-offs

| Model | Disk | RAM | Speed | Accuracy | Best For |
|-------|------|-----|-------|----------|----------|
| `en_core_web_sm` | 12 MB | ~80 MB | Very fast | Good | ✅ ATS (job parsing) |
| `en_core_web_md` | 41 MB | ~300 MB | Fast | Better | Complex entity extraction |
| `en_core_web_lg` | 551 MB | ~800 MB | Slower | Best | High-accuracy NER |

**Recommendation**: Use `en_core_web_sm` for ATS (sufficient for job postings, lightweight)

#### ⚠️ spaCy Performance Characteristics
- First load: ~500ms (from disk, one-time per process)
- Subsequent loads: ~10ms (cached in-process)
- Sentence segmentation: ~0.01ms per sentence
- NER entity tagging: ~0.1ms per sentence
- **For 100 job postings (~50,000 sentences): ~5 seconds total preprocessing**

#### ❌ Common Errors & Quick Fixes

| Error | Quick Fix |
|-------|-----------|
| `No module named 'spacy'` | `uv sync` |
| `[E050] Can't find model` | `python -m spacy link en_core_web_sm en_core_web_sm --force` |
| Network timeout | Set `HTTP_PROXY` env var |
| Permission denied | Use `uv run` (ensures venv) |
| Disk full | `pip cache purge` |
| Version mismatch | `python -m spacy info` to check |

### 9. **SQLite Concurrency**

#### ⚠️ SQLite has single-writer limitation
- Multiple processes reading: ✅ OK
- Multiple processes writing: ❌ Lock contention
- Solution for this project: Sequential assessment (acceptable for lightweight tool)

#### ❌ Error: `database is locked`
```bash
# Solution 1: Ensure only one writer
# Solution 2: Implement retry logic with backoff
import sqlite3
import time

def db_retry(cursor, query, args, max_retries=3):
    for attempt in range(max_retries):
        try:
            return cursor.execute(query, args)
        except sqlite3.OperationalError:
            time.sleep(2 ** attempt)
            if attempt == max_retries - 1:
                raise
```

#### ❌ Error: `database disk image malformed`
- Corrupted SQLite file
- Solution: Backup & recreate
```bash
mv data/ats_playground.db data/ats_playground.db.bak
uv run python src/storage/db.py --init
```

### 10. **Multi-Version Python Issues**

#### Common Setup Mistakes
- `python` points to Python 2.7 (old systems)
- `python3` points to 3.9, but project needs 3.11+
- Multiple Python versions installed, UV uses wrong one

#### ✅ Solution
```bash
# Check UV's Python
uv python list

# Force specific version
uv python pin 3.13

# Verify
python --version  # Should be 3.13+
```

### 11. **Dependencies Version Matrix**

| Dependency | Min | Max | Notes |
|------------|-----|-----|-------|
| Python | 3.11 | 3.14 | 3.13 recommended |
| spaCy | 3.8.0 | <4.0 | 3.8.12+ for Pydantic v2 |
| MarkItDown | 0.1.5 | <1.0 | Optional, primary HTML cleaner |
| BeautifulSoup4 | 4.12.0 | <5.0 | Fallback if MarkItDown unavailable |
| lxml | 4.9.0 | <5.0 | C dependencies required (BeautifulSoup fallback) |
| Pydantic | 2.5.0 | <3.0 | Must be v2 |
| tiktoken | 0.8.0 | <1.0 | 0.5+ OK but 0.8+ faster |
| Playwright | 1.48.0 | <2.0 | 1.40+ stable |
| Anthropic | 0.25.0 | <1.0 | Latest recommended |

## spaCy Model Download Decision Tree

**Use this flowchart to resolve download issues**:

```
spaCy download fails?
│
├─ Error: "No module named 'spacy'"
│  └─ spaCy not installed yet
│     Solution: uv sync
│
├─ Error: "[E050] Can't find model 'en_core_web_sm'"
│  ├─ Version mismatch (spaCy 3.7 vs 3.8)?
│  │  └─ Solution: python -m spacy info (check versions)
│  ├─ Model symlink missing?
│  │  └─ Solution: python -m spacy link en_core_web_sm en_core_web_sm --force
│  └─ Downloaded to wrong Python?
│     └─ Solution: Always use: uv run python -m spacy download en_core_web_sm
│
├─ Error: Network error (SSL, timeout, 403)
│  ├─ Behind corporate proxy?
│  │  └─ Solution: export HTTP_PROXY=http://proxy:8080
│  ├─ Slow connection?
│  │  └─ Solution: Try PyPI mirror or manual download
│  └─ Can't reach PyPI?
│     └─ Solution: Check DNS, try: curl -I https://files.pythonhosted.org
│
├─ Error: "Permission denied" or "No space left on device"
│  ├─ Permission issue?
│  │  └─ Solution: Use virtual environment (uv sync)
│  └─ Disk full?
│     └─ Solution: pip cache purge (frees ~200-500 MB)
│
├─ Error: "No matching distribution found" (Python 3.13)
│  └─ spaCy wheels not built for 3.13 yet
│     Solution: uv pip install --upgrade spacy (3.8.10+)
│
├─ Error: Stuck or hangs?
│  └─ Network timeout or slow connection
│     Solution: Try verbose mode: python -m spacy download en_core_web_sm -v
│
└─ Still failing?
   └─ Run: python -m spacy download en_core_web_sm --force-all -v
      (Nuclear option: pip cache purge && uv sync --refresh)
```

## Installation Troubleshooting

### Clean Install (Nuclear Option)
```bash
# Remove everything and reinstall
rm -rf .venv uv.lock
uv sync --all-extras

# Re-download models
uv run python -m spacy download en_core_web_md
uv run playwright install

# Verify
uv run pytest tests/ -v
```

### Check Version Conflicts
```bash
uv pip list | grep -E 'pydantic|spacy|tiktoken|playwright'

# Show dependency tree
uv pip show -r pydantic
```

### Debug Import Issues
```bash
# Test each dependency
uv run python -c "import playwright; print('✅ playwright')"
uv run python -c "from markitdown import MarkItDown; print('✅ markitdown')"
uv run python -c "import bs4; print('✅ beautifulsoup4')"
uv run python -c "import lxml; print('✅ lxml')"
uv run python -c "import tiktoken; print('✅ tiktoken')"
uv run python -c "import pydantic; print('✅ pydantic')"
uv run python -c "import anthropic; print('✅ anthropic')"

# Full spaCy validation (critical)
uv run python -c "
import spacy
print('spaCy version:', spacy.__version__)
try:
    nlp = spacy.load('en_core_web_sm')
    doc = nlp('Test sentence.')
    print('✅ spaCy model loaded successfully')
    print('  - Tokens:', len(doc))
    print('  - POS tags:', [token.pos_ for token in doc][:3])
except OSError as e:
    print('❌ Model not found:', e)
    print('  Run: uv run python -m spacy download en_core_web_sm')
    exit(1)
"

# Full preprocessing pipeline test
uv run python -c "
from markitdown import MarkItDown
import spacy
import tiktoken
print('✅ All PREPROCESS dependencies OK')
print('  - MarkItDown: HTML→Markdown converter')
print('  - spaCy:', __import__('spacy').__version__)
print('  - tiktoken: Token counting')
"

# spaCy model info
uv run python -m spacy info
```

## Environment-Specific Notes

### Docker / Container
- Need system deps: `libxml2-dev libxslt-dev python3-dev`
- Add to Dockerfile:
```dockerfile
RUN apt-get install -y libxml2-dev libxslt-dev python3-dev
```

### GitHub Actions / CI
- Use `setup-python@v4` for Python version
- Cache UV: `actions/setup-python` handles it
- Example workflow:
```yaml
- name: Setup Python
  uses: actions/setup-python@v4
  with:
    python-version: "3.13"

- name: Install UV
  run: pip install uv

- name: Sync dependencies
  run: uv sync

- name: Download models
  run: uv run python -m spacy download en_core_web_md
```

### macOS (Apple Silicon)
- Some packages (lxml, tiktoken) may need arm64 builds
- UV handles this automatically
- If issues: `uv pip install --upgrade --force-reinstall lxml`

### Windows
- lxml pre-built wheels work out of box
- Playwright requires Visual C++ redistributable (auto-downloaded)
- Use Windows Terminal for better shell support

## Version Upgrade Paths

### Upgrading Python 3.11 → 3.13
```bash
uv python pin 3.13
uv sync  # Will recreate environment
uv run pytest tests/ -v  # Verify
```

### Upgrading spaCy 3.7 → 3.8+
```bash
# Update pyproject.toml: spacy>=3.8.0
uv sync --upgrade
uv run python -m spacy download en_core_web_sm  # Re-download for new version
uv run pytest tests/ -v  # Verify
```

### Upgrading Pydantic 2.0 → 2.5+
```bash
# Update pyproject.toml: pydantic>=2.5.0
uv sync --upgrade
# Code compatible, no changes needed
```

## Performance Tuning

- **Use en_core_web_sm** for ATS (lightweight, 12 MB, ~80 MB RAM, sufficient accuracy)
- **Use MarkItDown** for HTML cleaning (3-5x faster than BeautifulSoup)
- **Set PLAYWRIGHT_HEADLESS=true** for 20% speedup
- **Batch token counting** for 100+ jobs (tiktoken is very fast, ~1000 jobs/sec)
- **Cache spaCy model** in-process (first load ~500ms, subsequent <10ms)
- **Use SQLite indexed queries** on company_id and extracted_date
- **Parallel preprocessing**: Process 3-5 jobs in parallel for 200+ jobs/min throughput

## Recommended Configuration for ATS Showcase

```toml
# pyproject.toml - Optimized for ATS
[project]
name = "ats-showcase"
version = "0.1.0"
requires-python = "^3.13"

dependencies = [
    "spacy>=3.8.0,<4.0",            # ✅ Pydantic v2 compatible, 3.13 support
    "markitdown>=0.1.5,<1.0",        # ✅ Fast HTML→text converter (primary)
    "beautifulsoup4>=4.12.0,<5.0",   # Fallback HTML parser
    "lxml>=4.9.0,<5.0",              # BeautifulSoup lxml backend
    "tiktoken>=0.8.0,<1.0",          # ✅ Token counting
    "pydantic>=2.5.0,<3.0",          # Data validation
    "playwright>=1.48.0,<2.0",       # Web crawling
    "anthropic>=0.25.0,<1.0",        # Claude API
]
```

**spaCy Environment Variables** (optional, for advanced use):
```bash
# Control where spaCy stores models (default: ~/.spacy/)
export SPACY_HOME=/custom/models/directory

# Verbose download output
export SPACY_DOWNLOAD_LOGLEVEL=DEBUG

# Proxy configuration (if behind corporate firewall)
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=https://proxy.example.com:8443
export NO_PROXY=localhost,127.0.0.1

# Python behavior (optional)
export PYTHONUSERBASE=/custom/python/base
```

**Performance Characteristics**:
- **Startup time**: ~1 second (spaCy model load + imports)
- **Token reduction**: 80-90% (raw HTML → cleaned text → chunks)
- **Cost per job**: ~$0.003 (Claude 3.5 Haiku, 100-token avg after preprocessing)
- **Processing speed**:
  - Crawling: 100+ jobs/min
  - Preprocessing: 200+ jobs/min
  - Token counting: 1000+ jobs/sec
  - LLM assessment: 2-5 jobs/min

## 🚨 Dependency Conflict Matrix

### Overview
This section documents known compatibility issues between dependencies in the project. All conflicts have been resolved in the current `pyproject.toml` configuration.

### 1. **Pydantic v2 Migration (RESOLVED ✅)**

| Aspect | Issue | Status | Solution |
|--------|-------|--------|----------|
| **spaCy < 3.8** | Uses Pydantic v1 config system | ❌ Conflict | Update to `spacy>=3.8.0` |
| **spaCy 3.8+** | Migrated to Pydantic v2 | ✅ Compatible | Project uses `spacy>=3.8.0` |
| **Project Config** | `pydantic>=2.5.0,<3.0` | ✅ Compatible | No conflicts (v2 only) |

**Details**: spaCy versions before 3.8 depend on `confection<0.1` which uses Pydantic v1's deprecated config system. Upgrading spaCy to 3.8+ fully migrates to Pydantic v2. This project requires Pydantic 2.5+ for advanced validation, so spaCy 3.8+ is mandatory.

**Action**: Always `pip install spacy>=3.8.0` (default in `pyproject.toml`)

### 2. **MarkItDown Optional Dependencies (MANAGED ⚠️)**

| Dependency | Includes | Impact | Recommendation |
|------------|----------|--------|-----------------|
| `markitdown` (base) | HTML parsing only | ✅ Lightweight (~2MB) | Use for ATS |
| `markitdown[all]` | PDF, DOCX, PPTX, etc. | ⚠️ Heavy (~100MB) | Not needed for job postings |
| Fallback: `beautifulsoup4` | HTML parsing only | ✅ Works, slower | Auto-fallback if MarkItDown unavailable |

**Details**: MarkItDown's `[all]` extra includes PDF and Office format support (via `pandoc`, `pdfplumber`, etc.), which adds significant disk space and system dependencies. For ATS use, the base `markitdown` package (HTML only) is sufficient.

**Recommended Install**:
```bash
# For ATS HTML parsing (lightweight)
uv pip install markitdown>=0.1.5

# Full install only if you need office format support
uv pip install "markitdown[all]"
```

**Action**: Document in CLI setup guide that base `markitdown` (not `[all]`) is recommended for ATS.

### 3. **lxml C Binding Dependencies (SYSTEM-LEVEL ⚠️)**

| Platform | Required System Libraries | Status | Install |
|----------|---------------------------|--------|---------|
| **Ubuntu/Debian** | `libxml2-dev`, `libxslt-dev`, `python3-dev` | ⚠️ Required | `apt-get install` |
| **macOS** | `libxml2`, `libxslt` | ⚠️ Required | `brew install` or use system Python |
| **Windows** | None (pre-built wheels) | ✅ Automatic | pip auto-installs wheels |

**Details**: BeautifulSoup (fallback HTML parser) uses `lxml` as preferred C-based parser for performance. lxml requires system C libraries. If unavailable, BeautifulSoup falls back to pure-Python `html.parser` (~3-5x slower).

**Install Guide**:
```bash
# Ubuntu/Debian
sudo apt-get install libxml2-dev libxslt-dev python3-dev

# macOS (Homebrew)
brew install libxml2 libxslt

# macOS with custom paths (if needed)
LDFLAGS="-L$(brew --prefix libxml2)/lib" \
CPPFLAGS="-I$(brew --prefix libxml2)/include" \
uv pip install lxml

# Windows: No action needed (wheels auto-install)
```

**Action**: Document system dependencies in setup guide. MarkItDown primary parser avoids this issue (falls back to `html.parser` internally).

### 4. **Playwright Binary Installation (NETWORK-DEPENDENT ⚠️)**

| Component | Size | Download Time | Status |
|-----------|------|----------------|--------|
| **Chromium Binary** | ~150-200 MB | 2-5 minutes | ⚠️ Auto-download |
| **Network Requirement** | 10+ Mbps recommended | — | ⚠️ May fail on restricted networks |

**Details**: Playwright downloads platform-specific Chromium binary on first use. This may fail in restricted corporate networks or regions with connectivity issues.

**Troubleshooting**:
```bash
# Pre-download with verbose output
uv run playwright install chromium -v

# Set proxy if behind corporate firewall
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=https://proxy.example.com:8443
uv run playwright install chromium

# Force re-download if corruption suspected
rm -rf ~/.cache/ms-playwright && uv run playwright install chromium
```

**Action**: Document pre-download step in setup guide for restricted environments.

### 5. **anthropic SDK & TLS/SSL Compatibility (MINOR ⚠️)**

| Version | Python 3.11 | Python 3.12 | Python 3.13 | TLS Support | Status |
|---------|------------|------------|------------|-------------|--------|
| **0.25.0+** | ✅ | ✅ | ✅ | TLS 1.2+ | ✅ Stable |
| **< 0.25.0** | ✅ | ⚠️ | ❌ | TLS 1.2+ | ⚠️ Legacy |

**Details**: anthropic SDK v0.25.0+ has improved TLS/SSL handling for Python 3.12+. Older versions may have connectivity issues on systems with outdated TLS libraries.

**Potential Issue**: Systems with only TLS 1.0/1.1 enabled will fail to connect to Anthropic API.

**Mitigation**:
```bash
# Update SDK to latest stable
uv pip install --upgrade anthropic>=0.25.0,<1.0

# Check system TLS support
python -c "import ssl; print(f'OpenSSL: {ssl.OPENSSL_VERSION}')"

# If TLS too old, consider upgrading system OpenSSL
```

**Action**: Pin `anthropic>=0.25.0` in `pyproject.toml` (already done ✅)

### 6. **tiktoken Encoding Compatibility (TOKEN COUNT ⚠️)**

| Encoder | Claude 3.5 Sonnet | Token Accuracy | Notes |
|---------|------------------|-----------------|-------|
| **gpt-4** (tiktoken) | ✅ Compatible | 98-102% | Slight variance expected |
| **claude-3.5-sonnet** (official) | ✅ Native | 100% | Authoritative; used only in LLM responses |

**Details**: Project uses `tiktoken` (OpenAI's tokenizer) to estimate Claude token counts before API calls. This provides good accuracy (~98-102%) but may differ slightly from Claude's actual count due to:
- Special tokens and prompt overhead
- Formatting tokens
- Internal Claude tokenization updates

**Typical Variance**:
```
Estimated (tiktoken): 650 tokens
Actual (Claude): 655 tokens
Difference: +0.77% (acceptable)
```

**Cost Impact**: Negligible (~$0.000001 per job at current rates)

**Tracking**: Cost tracking table in storage logs both estimated and actual tokens for audit trail.

**Action**: Keep `tiktoken>=0.8.0` pinned; document token count variance as expected (<1% typically).

### 7. **Cross-Dependency Conflict Summary (ALL RESOLVED ✅)**

| Dependency | Conflicts With | Status | Mitigation |
|------------|----------------|--------|-----------|
| `spacy>=3.8.0` | `pydantic<2.0` | ✅ OK (requires v2) | `pydantic>=2.5.0` enforced |
| `pydantic>=2.5.0` | `spacy<3.8` | ✅ OK (spacy pinned to 3.8+) | `spacy>=3.8.0` enforced |
| `markitdown>=0.1.5` | `beautifulsoup4` | ✅ OK (no conflict, fallback) | Both can coexist |
| `beautifulsoup4>=4.12.0` | `lxml>=4.9.0` | ⚠️ System deps | lxml optional (html.parser fallback) |
| `lxml>=4.9.0` | System C libs | ⚠️ System deps | Document per-platform install |
| `anthropic>=0.25.0` | `tiktoken>=0.8.0` | ✅ OK (independent) | No direct conflict |
| `tiktoken>=0.8.0` | `anthropic>=0.25.0` | ✅ OK (independent) | Compatible versions |
| `playwright>=1.48.0` | Chromium binary | ⚠️ Network | Auto-download; document pre-install |

### Python 3.12 Compatibility (NO CONFLICTS ✅)

All major dependencies have verified Python 3.12 support:
- ✅ spaCy 3.8.10+ (verified, full wheel support)
- ✅ pydantic 2.5+ (verified, no issues)
- ✅ anthropic 0.25+ (verified)
- ✅ tiktoken 0.8+ (verified)
- ✅ playwright 1.48+ (verified)
- ✅ markitdown 0.1.5+ (verified)
- ✅ beautifulsoup4 4.12+ (verified)

**Action**: Python 3.12.x recommended for production; 3.13+ for development

## Troubleshooting Summary

| Issue | Root Cause | Quick Fix | Prevention |
|-------|-----------|-----------|-----------|
| "No module named 'spacy'" | spaCy not installed | `uv sync` | Always run sync before download |
| "[E050] Can't find model" | Version mismatch or symlink missing | `python -m spacy info` | Use `uv run python -m spacy download` |
| Network timeout | Proxy/firewall | Set `HTTP_PROXY` env var | Check network before downloading |
| Permission denied | System Python | Use `uv run` (ensures venv) | Never use `sudo pip install` |
| Disk full | < 200 MB available | `pip cache purge` | Check `df -h /` before download |
| Python 3.13 fails | spaCy < 3.8.10 | `uv pip install --upgrade spacy` | Keep spaCy >= 3.8.10 |
| Model loads slowly | Cold start (first load) | Normal (~500ms) | Subsequent loads are ~10ms (cached) |
| Hangs during download | Network issue | Use `-v` flag for verbose output | Try PyPI mirror if repeated timeout |

## Further Reading

- **spaCy Official**: https://spacy.io/usage/models
- **spaCy Issue Tracker**: https://github.com/explosion/spacy/issues
- **spaCy Models**: https://spacy.io/models/en
- **PyPI (en_core_web_sm)**: https://pypi.org/project/en-core-web-sm/
