# Plan: Task 1 - Call an LLM from Code

## Overview

Build a CLI (`agent.py`) that takes a question as a command-line argument, sends it to an LLM API, and returns a structured JSON response with `answer` and `tool_calls` fields.

## LLM Provider

- **Provider**: Qwen Code API (self-hosted on VM)
- **Endpoint**: `http://10.93.26.44:42005/v1`
- **Model**: `qwen3-coder-plus`
- **Authentication**: Bearer token from `.env.agent.secret`

## Architecture

```
Command line → agent.py → LLM API → JSON response → stdout
                              ↓
                        stderr (debug logs)
```

## Implementation Steps

1. **Parse command-line arguments**
   - Use `sys.argv[1]` to get the question
   - Handle missing argument with error message to stderr

2. **Load environment variables**
   - Read `.env.agent.secret` for `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`
   - Use `python-dotenv` or manual parsing

3. **Call the LLM API**
   - Use `requests` or `httpx` library
   - POST to `{LLM_API_BASE}/chat/completions`
   - Headers: `Authorization: Bearer {LLM_API_KEY}`, `Content-Type: application/json`
   - Body: `{"model": LLM_MODEL, "messages": [{"role": "user", "content": question}]}`

4. **Parse and format response**
   - Extract `choices[0].message.content` as `answer`
   - Set `tool_calls: []` (empty for this task)
   - Output valid JSON to stdout

5. **Error handling**
   - Network errors → stderr message, exit code 1
   - API errors → stderr message, exit code 1
   - Missing question → stderr message, exit code 1

## Testing

- Run `uv run agent.py "What is 2+2?"` and verify JSON output
- Check that `answer` field contains a non-empty string
- Check that `tool_calls` is an empty array
- Verify no debug output goes to stdout

## Files to Create/Modify

- `agent.py` — main CLI implementation
- `AGENT.md` — documentation
- `tests/test_agent.py` — regression test (1 test)
