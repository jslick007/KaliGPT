# KaliGPT — Agent Instructions

## Project

Python CLI tool that provides a unified interface to multiple AI providers (Gemini, OpenAI, OpenRouter, Ollama) for offensive security assistance. Ships a bash installer for Debian/Termux.

## Structure & Entrypoints

- `agents/` — Python package; run from repo root via `python -m agents [prompt]` or `python -m agents.{gemini,chatgpt,ollama,openrouter} [prompt]`
- `agents/__main__.py` — entrypoint: dispatches to `--setup-keys` or the default provider agent
- `agents/gemini.py`, `agents/chatgpt.py`, `agents/ollama.py`, `agents/openrouter.py` — each is a standalone interactive loop with tool-calling
- `install.sh` — OS/environment detection, downloads platform-specific installer
- `installers/installer.deb.sh` — full system setup (apt pkgs, pip venv, launcher script)
- No standard Python packaging (no `setup.py`/`pyproject.toml`)

## Config

- `agents/utils/api.config.json` — API keys, models, default provider. Plaintext keys. Auto-created with defaults if missing/corrupted.
- Agents validate keys on launch:
  - Gemini: must contain `AIza`
  - OpenRouter: must contain `sk-or-v1-`
  - ChatGPT: must contain `sk-`
  - Ollama: uses `http://localhost:11434` as "api_key" (the Ollama server URL)

## Dependencies

- `requirements/pip-requirements.txt` — `openai`, `ollama`, `google-genai`, `rich`, `requests`, `newspaper3k`, `lxml_html_clean`, `beautifulsoup4`, `flask`, `ddgs`, `curl_cffi`, `nodriver`, `pyvirtualdisplay`, `prompt_toolkit`
- System deps for building: `libxml2`, `libxslt`, `libjpeg-turbo`, `libpng`, `freetype`, `make`, `pkg-config`, `clang`, `rust`

## Running

```bash
# Run from repo root
python -m agents "find XSS on target.com"
python -m agents.gemini "scan for subdomains"
python -m agents --setup-keys
```

## Linting & Formatting

After every file change, run:
```bash
ruff check --fix agents/
ruff format agents/
```
Install ruff: `pip install ruff`

## Tools System

`agents/utils/tools/` registers Python functions the AI can call. All 4 agents (gemini, chatgpt, ollama, openrouter) load the same tool set via `get_tools_info()`. OpenAI-compatible agents (chatgpt, openrouter) also wrap tools through `openai_tool_adapter()` for schema translation.

### Function Map

| Function | Source | Args | Returns | Dependency |
|---|---|---|---|---|
| `check_search_connection` | `tools/opensearchapi.py:18` | `timeout: int=10` | `bool` | OpenSearchAPI at `:5000` |
| `keyword_search` | `tools/opensearchapi.py:74` | `keyword: str`, `engines: str="google"`, `top_n: int=4`, `timeout: int=30` | `list[tuple[str,str]]` | OpenSearchAPI at `:5000` |
| `search_as_RAG` | `tools/opensearchapi.py:171` | `list_of_keywords: list[str]` | `list[dict]` | OpenSearchAPI at `:5000` |
| `get_local_server_content` | `tools/locals.py:13` | `url: str`, `timeout: int=5` | `dict` | none |
| `execute_generic_linux_command` | `tools/locals.py:68` | `command: str` | `dict` | none |
| `web_request_analysis` | `tools/web_request_framework.py:32` | `url: str`, `method: str="GET"`, `payload: str=None`, `headers: str=None`, `timeout: int=10` | `dict` | none |
| `get_raw_response` | `tools/web_request_framework.py:254` | `url: str`, `method: str="GET"`, `payload: str=None`, `headers: str=None`, `timeout: int=10`, `full_res_body: bool=False` | `dict` | none |

OpenSearchAPI (`http://127.0.0.1:5000`) is started/stopped via `agents/utils/openserp_management.py` (not auto-managed; agents call `check_search_connection` before using search tools).

### Prompts

All 4 agent modules import and use `WEB_BUG_BOUNTY_AGENT` (aliased as `SYSTEM_PROMPT`). The unused prompts remain in `prompts.py` for reference.

| Variable | Line | Used by | Purpose |
|---|---|---|---|
| `SYSTEM_PROMPT_OLD` | 6 | (unused) | Original v1.1 KaliGPT prompt |
| `SYSTEM_PROMPT` | 18 | (unused) | Jailbreak-style v1.3 prompt with roleplay framing |
| `WEB_BUG_BOUNTY_AGENT` | 49 | gemini, chatgpt, ollama, openrouter | Web app security testing agent with autonomous workflow |
| `WEB_PENTESTER_AGENT` | 117 | (unused) | Structured web/API pentesting methodology prompt |
| `RED_TEAM_AGENT` | 304 | (unused) | Red team privilege escalation agent |

`__init__.py` imports `SYSTEM_PROMPT` and `SYSTEM_PROMPT_OLD` but only `__main__.py` uses those imports transitively — the actual agents all override with `WEB_BUG_BOUNTY_AGENT`.

### Git Hooks

A pre-commit hook is installed at `.githooks/pre-commit`. Enable it with:

```bash
git config core.hooksPath .githooks
```

It runs `ruff check --fix` and `ruff format` on staged `.py` files. Install ruff: `pip install ruff`.

## Notables

- Run `ruff check --fix agents/ && ruff format agents/` after every code change

- No test suite, no lint/typecheck config, no CI beyond a stats tracker
- System prompts in `agents/utils/prompts.py` (~365 lines) contain jailbreak-style instructions — be careful when modifying
- Terminal output uses `rich` (Panels, Markdown, Syntax highlighting); interactive selection uses `prompt_toolkit`
- `agents/web_launcher.py` opens AI web chats in a local browser (used via `kaligpt --web`)
