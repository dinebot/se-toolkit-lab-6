# Agent Architecture

This document describes the architecture of the system agent implemented in `agent.py`. The agent answers questions by querying an LLM and using tools to access project documentation, source code, and the running backend API. It implements an **agentic loop** that allows the LLM to request tool calls, receive results, and iterate until it has enough information to provide a final answer.

## Overview

The agent is a CLI tool built for Task 3 of the software engineering lab. It extends the Task 2 documentation agent by adding a `query_api` tool that enables interaction with the deployed backend. This allows the agent to answer both static questions (documentation, source code) and dynamic questions (live data from the API).

## Tools

The agent has three tools available:

### `read_file`

Reads the contents of a file from the project repository.

**Parameters:**
- `path` (string, required): Relative path from project root (e.g., `wiki/git-workflow.md`, `backend/app/main.py`)

**Returns:**
- File contents as a string
- Error message if file doesn't exist or path is invalid

**Security:**
- Rejects paths containing `..` (path traversal prevention)
- Validates that resolved path stays within project root directory

**When to use:** Use for finding specific information in documentation or source code files.

### `list_files`

Lists files and directories at a given path.

**Parameters:**
- `path` (string, required): Relative directory path from project root (e.g., `wiki`, `backend/app/routers`)

**Returns:**
- Newline-separated listing of entries (directories suffixed with `/`)
- Error message if directory doesn't exist or path is invalid

**When to use:** Use to discover what files exist in a directory before reading them.

### `query_api`

Queries the deployed backend API with authentication.

**Parameters:**
- `method` (string, required): HTTP method (GET, POST, etc.)
- `path` (string, required): API path (e.g., `/items/`, `/analytics/completion-rate?lab=lab-1`)
- `body` (string, optional): JSON request body for POST/PUT requests

**Returns:**
- JSON string with `status_code` and `body` fields
- Error message if authentication fails or request errors

**Authentication:** Uses `LMS_API_KEY` from `.env.docker.secret` for Bearer token authentication.

**When to use:** Use for live data questions (item counts, status codes, analytics) that require querying the running system. Do not use for source code questions.

## Environment Variables

The agent reads all configuration from environment variables:

| Variable | Purpose | Source File |
|----------|---------|-------------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for backend API | Optional, defaults to `http://localhost:42002` |

The `load_env()` function loads both `.env.agent.secret` (required) and `.env.docker.secret` (optional) to gather all credentials.

## Agentic Loop

The agent implements a loop that continues until the LLM provides a final answer or reaches the maximum tool call limit:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Agentic Loop Flow                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Initialize messages with system prompt + user question      │
│                                                                 │
│  2. Send messages + tool schemas to LLM                         │
│                                                                 │
│  3. Parse response                                              │
│     ┌─────────────────────────────────────────────────────┐     │
│     │ Has tool_calls?                                     │     │
│     │  YES → Execute each tool                            │     │
│     │         → Append results as "tool" role messages    │     │
│     │         → Increment call counter                    │     │
│     │         → If counter >= 10, exit loop               │     │
│     │         → Go to step 2                              │     │
│     └─────────────────────────────────────────────────────┘     │
│     │                                                           │
│     │ NO  → Extract answer from "content" field                │
│     │     → Extract source reference (if present)              │
│     │     → Output JSON and exit                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Message Format

Messages are tracked in OpenAI-compatible format:

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After tool call:
    {"role": "assistant", "tool_calls": [...]},
    {"role": "tool", "tool_call_id": "...", "content": "result"},
    # ... more iterations
]
```

### Exit Conditions

1. **Success**: LLM returns a message with `content` (no `tool_calls`)
2. **Max calls**: 10 tool calls reached (safety limit)
3. **Error**: Tool execution fails

## System Prompt Strategy

The system prompt instructs the LLM on how to select the appropriate tool:

```
You are a documentation and system assistant. You have access to tools that let you:
1. Read files and list directories in the project wiki and source code
2. Query the running backend API for live system data

When answering questions:
- For wiki/documentation questions (e.g., "how to protect a branch"): use `list_files` and `read_file` on the wiki/ directory
- For source code questions (e.g., "what framework does this use"): use `read_file` on backend/ files
- For live data questions (e.g., "how many items", "what status code"): use `query_api` to query the running API
- For bug diagnosis: first use `query_api` to reproduce the error, then use `read_file` to find the buggy code

Always include a source reference in your answer using the format: `filepath.md#section-name`
For API queries, cite the endpoint path as the source.

Be concise and accurate. Only use information from files you read or API responses you receive.
```

### Key Instructions

- **Tool selection**: The LLM must choose the right tool based on question type
- **Discovery first**: Use `list_files` before `read_file` to explore directories
- **Source attribution**: Include a `filepath.md#section` reference for file-based answers
- **Grounding**: Only use information from files actually read or API responses received

## Output Format

The agent outputs JSON to stdout:

```json
{
  "answer": "There are 120 items in the database.",
  "source": "/items/",
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/"},
      "result": "{\"status_code\": 200, \"body\": [...]}"
    }
  ]
}
```

### Fields

- `answer` (string, required): The final answer from the LLM
- `source` (string, optional): Reference to the source (file path with anchor, or API endpoint)
- `tool_calls` (array, required): All tool calls made during execution

## Path Security

The agent prevents directory traversal attacks for file operations:

1. **String check**: Rejects any path containing `..`
2. **Resolution check**: After resolving to absolute path, verifies it starts with project root
3. **Error handling**: Returns clear error messages for invalid paths

```python
def validate_path(path: str) -> Path:
    if ".." in path:
        raise ValueError("Path traversal (..) not allowed")

    full_path = (PROJECT_ROOT / path).resolve()

    if not str(full_path).startswith(str(PROJECT_ROOT)):
        raise ValueError("Path escapes project directory")

    return full_path
```

Note: `query_api` does not use path validation since it queries an external API, not the filesystem.

## Usage

```bash
# Ask a documentation question
uv run agent.py "How do you resolve a merge conflict?"

# Ask a source code question
uv run agent.py "What Python web framework does the backend use?"

# Ask a live data question
uv run agent.py "How many items are in the database?"

# Output goes to stdout as JSON
# Debug logs go to stderr
```

## Implementation Details

- **LLM API**: OpenAI-compatible chat completions endpoint
- **Timeout**: 60 seconds per API call, 30 seconds for backend queries
- **Tool call limit**: Maximum 10 tool calls per question
- **Debug output**: All progress messages go to stderr (not stdout)
- **Null handling**: Uses `(msg.get("content") or "")` instead of `msg.get("content", "")` to handle LLM responses where `content` is `null` rather than missing

## Lessons Learned

### Tool Selection
The LLM needs clear guidance on when to use each tool. Initially, the agent would sometimes try to read source code files for live data questions. Adding explicit examples in the system prompt ("how many items" → `query_api`, "what framework" → `read_file`) significantly improved tool selection accuracy.

### Authentication Handling
The `query_api` tool must authenticate with `LMS_API_KEY` from `.env.docker.secret`, which is different from the `LLM_API_KEY` used for LLM calls. Mixing these up causes authentication failures. Loading both `.env` files in `load_env()` ensures all credentials are available.

### Error Handling
Backend API queries can fail for various reasons (network issues, database errors, invalid endpoints). The `query_api` tool wraps all errors in a consistent JSON format with `status_code` and `body.error` fields, making it easier for the LLM to understand and report errors.

### Benchmark Iteration
Running `run_eval.py` revealed several issues:
1. The agent didn't initially use `query_api` for status code questions — fixed by clarifying the tool description
2. Bug diagnosis questions required chaining `query_api` then `read_file` — the system prompt now explicitly instructs this two-step approach
3. Some answers were too short for LLM-judged questions — the prompt now encourages more detailed explanations

### Content Null Handling
A subtle bug occurred when the LLM returned `content: null` (which happens when making tool calls). Using `msg.get("content", "")` returns `""` for missing keys but `None` for `null` values. The fix was to use `(msg.get("content") or "")` which handles both cases correctly.

## Testing

Two regression tests verify tool usage:

1. **`test_backend_framework_uses_read_file`**: Verifies the agent uses `read_file` for source code questions and correctly identifies FastAPI
2. **`test_item_count_uses_query_api`**: Verifies the agent uses `query_api` for live data questions and returns a positive number

Additional tests cover status code queries and wiki questions.

## Benchmark Performance

The agent is evaluated against 10 local questions plus hidden questions from the autochecker:

| # | Question Type | Required Tool(s) |
|---|---------------|------------------|
| 0-1 | Wiki lookup | `read_file`, `list_files` |
| 2-3 | Source code | `read_file`, `list_files` |
| 4-5 | Live data | `query_api` |
| 6-7 | Bug diagnosis | `query_api` + `read_file` |
| 8-9 | Reasoning | `read_file` (multi-file) |

*Final eval score to be updated after autochecker evaluation.*
