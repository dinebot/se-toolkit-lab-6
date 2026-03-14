# Task 3 Plan: The System Agent

## Overview

This task extends the Task 2 documentation agent by adding a `query_api` tool. The agent can now query the deployed backend API to answer questions about system state (items count, status codes, analytics) in addition to reading documentation.

---

## 1. Environment Variables

The agent must read all configuration from environment variables:

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for `query_api` | Optional, defaults to `http://localhost:42002` |

### Implementation

Extend `load_env()` to also load `.env.docker.secret` for `LMS_API_KEY`:

```python
def load_env() -> dict[str, str]:
    """Load environment variables from .env files."""
    env_vars = {}
    
    # Load LLM config from .env.agent.secret
    for env_file, required in [(".env.agent.secret", True), (".env.docker.secret", False)]:
        path = Path(__file__).parent / env_file
        if not path.exists():
            if required:
                print(f"Error: {env_file} not found", file=sys.stderr)
                sys.exit(1)
            continue
        
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
    
    return env_vars
```

---

## 2. query_api Tool Schema

### Function Definition

```python
def query_api(method: str, path: str, body: str | None = None) -> str:
    """
    Call the backend API.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path (e.g., '/items/')
        body: Optional JSON request body for POST/PUT
    
    Returns:
        JSON string with status_code and body
    """
```

### Tool Schema for LLM

```json
{
  "type": "function",
  "function": {
    "name": "query_api",
    "description": "Query the backend API. Use this to get live data from the system (item counts, analytics, status codes). Use read_file for source code questions.",
    "parameters": {
      "type": "object",
      "properties": {
        "method": {
          "type": "string",
          "description": "HTTP method (GET, POST, etc.)"
        },
        "path": {
          "type": "string",
          "description": "API path (e.g., '/items/', '/analytics/completion-rate?lab=lab-1')"
        },
        "body": {
          "type": "string",
          "description": "Optional JSON request body for POST/PUT requests"
        }
      },
      "required": ["method", "path"]
    }
  }
}
```

### Implementation with Authentication

```python
def query_api(method: str, path: str, body: str | None = None) -> str:
    """Query the backend API with authentication."""
    env = load_env()
    api_key = env.get("LMS_API_KEY")
    api_base = env.get("AGENT_API_BASE_URL", "http://localhost:42002")
    
    if not api_key:
        return json.dumps({"status_code": 500, "body": {"error": "LMS_API_KEY not set"}})
    
    url = f"{api_base}{path}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    try:
        with httpx.Client(timeout=30.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                data = json.loads(body) if body else {}
                response = client.post(url, headers=headers, json=data)
            else:
                return json.dumps({"status_code": 400, "body": {"error": f"Unsupported method: {method}"}})
        
        return json.dumps({
            "status_code": response.status_code,
            "body": response.json() if response.content else {}
        })
    except Exception as e:
        return json.dumps({"status_code": 500, "body": {"error": str(e)}})
```

---

## 3. System Prompt Update

The system prompt must guide the LLM on when to use each tool:

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

---

## 4. execute_tool Update

Add `query_api` to the tool dispatcher:

```python
def execute_tool(tool_name: str, args: dict[str, object]) -> str:
    """Execute a tool and return its result."""
    if tool_name == "read_file":
        path = args.get("path", "")
        return read_file(path if isinstance(path, str) else "")
    elif tool_name == "list_files":
        path = args.get("path", "")
        return list_files(path if isinstance(path, str) else "")
    elif tool_name == "query_api":
        method = args.get("method", "GET")
        path = args.get("path", "")
        body = args.get("body")
        return query_api(
            method if isinstance(method, str) else "GET",
            path if isinstance(path, str) else "",
            body if isinstance(body, str) else None
        )
    else:
        return f"Error: Unknown tool '{tool_name}'"
```

---

## 5. Testing Strategy

### Test 1: Framework Detection (read_file)

```python
def test_backend_framework():
    """Test that agent uses read_file for source code questions."""
    result = run_agent("What Python web framework does this project use?")
    output = json.loads(result.stdout)
    
    assert result.returncode == 0
    assert "read_file" in [tc["tool"] for tc in output["tool_calls"]]
    assert "FastAPI" in output["answer"]
```

### Test 2: Item Count (query_api)

```python
def test_item_count():
    """Test that agent uses query_api for data questions."""
    result = run_agent("How many items are in the database?")
    output = json.loads(result.stdout)
    
    assert result.returncode == 0
    assert "query_api" in [tc["tool"] for tc in output["tool_calls"]]
    # Check answer contains a number > 0
    import re
    numbers = re.findall(r'\d+', output["answer"])
    assert any(int(n) > 0 for n in numbers)
```

---

## 6. Benchmark Questions Analysis

| # | Question | Required Tool | Key Challenge |
|---|----------|---------------|---------------|
| 0 | Wiki: protect branch | `read_file` | Navigate wiki, find anchor |
| 1 | Wiki: SSH connection | `read_file` | Summarize key steps |
| 2 | Framework from source | `read_file` | Find framework in backend code |
| 3 | API router modules | `list_files` | List backend/routers directory |
| 4 | Item count | `query_api` | GET /items/, parse response |
| 5 | Status code without auth | `query_api` | Query without header, get 401/403 |
| 6 | ZeroDivisionError bug | `query_api` + `read_file` | Query endpoint, find bug in source |
| 7 | TypeError in top-learners | `query_api` + `read_file` | Query, diagnose NoneType error |
| 8 | Request lifecycle | `read_file` | Read docker-compose, Dockerfile, trace hops |
| 9 | ETL idempotency | `read_file` | Read ETL code, explain external_id check |

---

## 7. Implementation Steps

1. Extend `load_env()` to load `.env.docker.secret`
2. Implement `query_api()` function with authentication
3. Add `query_api` tool schema to `get_tool_schemas()`
4. Update `execute_tool()` to dispatch `query_api`
5. Update `SYSTEM_PROMPT` to guide tool selection
6. Create tests directory and add 2 regression tests
7. Run `run_eval.py` and iterate on failures
8. Update `AGENT.md` with final architecture

---

## 8. Initial Benchmark Score

**Local Testing Results:**

| # | Question | Tool Used | Status |
|---|----------|-----------|--------|
| 0 | Wiki: protect branch | `list_files`, `read_file` | ✓ Pass - contains "branch", "protect" |
| 1 | Wiki: SSH connection | - | Not tested |
| 2 | Framework from source | `read_file` | ✓ Pass - returns "FastAPI" |
| 3 | API router modules | `list_files` | Not tested |
| 4 | Item count | `query_api` | ✓ Pass - returns 3 items |
| 5 | Status code without auth | `query_api` (auth=false) | ✓ Pass - returns 401 |
| 6 | ZeroDivisionError bug | - | Not tested |
| 7 | TypeError in top-learners | - | Not tested |
| 8 | Request lifecycle | - | Not tested |
| 9 | ETL idempotency | - | Not tested |

### First Failures and Fixes

1. **Framework detection failed** - LLM couldn't find backend files
   - **Fix**: Added explicit path rules to system prompt ("backend/app/main.py" not "app/main.py")
   - **Fix**: Increased max tool calls from 10 to 20

2. **Status code question failed** - Agent always sent auth header
   - **Fix**: Added `auth` parameter to `query_api` tool with default `true`
   - **Fix**: Updated tool description to mention `auth=false` for testing unauthenticated access

### Iteration Strategy

1. Test remaining questions (6-9) that require multi-step reasoning
2. For bug diagnosis questions, ensure agent chains `query_api` → `read_file`
3. For reasoning questions, ensure agent reads multiple relevant files

---

## 9. Lessons Learned

*To be filled after completing the task*
