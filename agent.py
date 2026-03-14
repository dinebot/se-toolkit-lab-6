#!/usr/bin/env python3
"""
Agent CLI - Calls an LLM with tools to answer questions based on documentation.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
    Debug logs to stderr.
"""

import json
import re
import sys
from pathlib import Path

import httpx

# Project root directory (where agent.py lives)
PROJECT_ROOT = Path(__file__).parent


def get_project_root() -> Path:
    """Get the absolute path to the project root."""
    return PROJECT_ROOT.resolve()


def validate_path(path: str) -> Path:
    """
    Validate that a path stays within the project directory.
    
    Args:
        path: Relative path from project root
        
    Returns:
        Absolute Path object
        
    Raises:
        ValueError: If path tries to escape project directory
    """
    # Reject .. in path string (prevent traversal attacks)
    if ".." in path:
        raise ValueError("Path traversal (..) not allowed")
    
    # Resolve to absolute path
    project_root = get_project_root()
    full_path = (project_root / path).resolve()
    
    # Verify the resolved path is still within project root
    if not str(full_path).startswith(str(project_root)):
        raise ValueError("Path escapes project directory")
    
    return full_path


def read_file(path: str) -> str:
    """
    Read the contents of a file.
    
    Args:
        path: Relative path from project root
        
    Returns:
        File contents as string, or error message
    """
    try:
        full_path = validate_path(path)
        
        if not full_path.exists():
            return f"Error: File not found: {path}"
        
        if not full_path.is_file():
            return f"Error: Not a file: {path}"
        
        return full_path.read_text()
        
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error reading file: {e}"


def list_files(path: str) -> str:
    """
    List files and directories at a given path.

    Args:
        path: Relative directory path from project root

    Returns:
        Newline-separated listing of entries, or error message
    """
    try:
        full_path = validate_path(path)

        if not full_path.exists():
            return f"Error: Directory not found: {path}"

        if not full_path.is_dir():
            return f"Error: Not a directory: {path}"

        entries = []
        for entry in sorted(full_path.iterdir()):
            suffix = "/" if entry.is_dir() else ""
            entries.append(f"{entry.name}{suffix}")

        return "\n".join(entries)

    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error listing directory: {e}"


def query_api(method: str, path: str, body: str | None = None, auth: bool = True) -> str:
    """
    Query the backend API.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path (e.g., '/items/', '/analytics/completion-rate?lab=lab-1')
        body: Optional JSON request body for POST/PUT requests
        auth: Whether to include authentication header (default: True)

    Returns:
        JSON string with status_code and body, or error message
    """
    env = load_env()
    api_key = env.get("LMS_API_KEY")
    api_base = env.get("AGENT_API_BASE_URL", "http://localhost:42002")

    url = f"{api_base}{path}"
    headers = {
        "Content-Type": "application/json",
    }
    
    # Only add auth header if requested
    if auth and api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif not api_key and auth:
        return json.dumps({"status_code": 500, "body": {"error": "LMS_API_KEY not set"}})

    print(f"Querying API: {method} {url} (auth={auth})...", file=sys.stderr)

    try:
        with httpx.Client(timeout=30.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                data = json.loads(body) if body else {}
                response = client.post(url, headers=headers, json=data)
            else:
                return json.dumps({"status_code": 400, "body": {"error": f"Unsupported method: {method}"}})

        result = {
            "status_code": response.status_code,
            "body": response.json() if response.content else {}
        }
        print(f"API response: {result['status_code']}", file=sys.stderr)
        return json.dumps(result)

    except json.JSONDecodeError as e:
        return json.dumps({"status_code": response.status_code, "body": {"error": f"Invalid JSON response: {e}"}})
    except Exception as e:
        return json.dumps({"status_code": 500, "body": {"error": str(e)}})


# System prompt for the documentation agent
SYSTEM_PROMPT = """You are a documentation and system assistant. You have access to tools that let you:
1. Read files and list directories in the project wiki and source code
2. Query the running backend API for live system data

When answering questions:
- For wiki/documentation questions (e.g., "how to protect a branch"): use `list_files` and `read_file` on the wiki/ directory
- For source code questions (e.g., "what framework does this use"): use `read_file` on backend/ files
- For live data questions (e.g., "how many items", "what status code"): use `query_api` to query the running API
- For bug diagnosis: first use `query_api` to reproduce the error, then use `read_file` to find the buggy code

Path rules:
- All paths are relative to the project root (where agent.py lives)
- To access backend code, use paths like "backend/app/main.py" or "backend/app/routers/"
- To access wiki files, use paths like "wiki/github.md"
- When listing a directory, use the full path from project root (e.g., "backend/app/routers" not just "routers")

Always include a source reference in your answer using the format: `filepath.md#section-name`
For API queries, cite the endpoint path as the source.

Be concise and accurate. Only use information from files you read or API responses you receive.
"""


def get_tool_schemas() -> list[dict[str, object]]:
    """
    Define tool schemas for function calling.

    Returns:
        List of tool definitions in OpenAI-compatible format
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file at the given path. Use this to find specific information in documentation files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')"
                        }
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories at the given path. Use this to discover what files exist in a directory before reading them.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative directory path from project root (e.g., 'wiki')"
                        }
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_api",
                "description": "Query the backend API. Use this to get live data from the system (item counts, analytics, status codes). Use read_file for source code questions. Set auth=false to test unauthenticated access.",
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
                        },
                        "auth": {
                            "type": "boolean",
                            "description": "Whether to include authentication header (default: true). Set to false to test unauthenticated access."
                        }
                    },
                    "required": ["method", "path"]
                }
            }
        }
    ]


def execute_tool(tool_name: str, args: dict[str, object]) -> str:
    """
    Execute a tool and return its result.

    Args:
        tool_name: Name of the tool to execute
        args: Arguments for the tool

    Returns:
        Tool result as string
    """
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
        auth = args.get("auth", True)
        return query_api(
            method if isinstance(method, str) else "GET",
            path if isinstance(path, str) else "",
            body if isinstance(body, str) else None,
            auth if isinstance(auth, bool) else True
        )
    else:
        return f"Error: Unknown tool '{tool_name}'"


def load_env() -> dict[str, str]:
    """Load environment variables from .env.agent.secret and .env.docker.secret."""
    env_vars: dict[str, str] = {}

    # Load from both .env files
    for env_file_name, required in [(".env.agent.secret", True), (".env.docker.secret", False)]:
        env_file = Path(__file__).parent / env_file_name
        if not env_file.exists():
            if required:
                print(f"Error: {env_file} not found", file=sys.stderr)
                sys.exit(1)
            continue

        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()

    return env_vars


def call_llm(
    messages: list[dict[str, object]],
    api_base: str,
    api_key: str,
    model: str,
    tools: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """
    Call the LLM API and return the full response.

    Args:
        messages: Conversation history
        api_base: Base URL of the API
        api_key: API key for authentication
        model: Model name to use
        tools: Optional list of tool schemas

    Returns:
        Full response data from API
    """
    url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload: dict[str, object] = {
        "model": model,
        "messages": messages,
    }

    # Add tools if provided
    if tools:
        payload["tools"] = tools

    print(f"Calling LLM at {url}...", file=sys.stderr)

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    print(f"LLM response received.", file=sys.stderr)
    return data


def run_agentic_loop(
    question: str,
    api_base: str,
    api_key: str,
    model: str,
) -> dict[str, object]:
    """
    Run the agentic loop: send question, execute tool calls, return final answer.

    Args:
        question: User's question
        api_base: Base URL of the API
        api_key: API key for authentication
        model: Model name to use

    Returns:
        Dictionary with answer, source, and tool_calls
    """
    # Initialize conversation history
    messages: list[dict[str, object]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    # Get tool schemas
    tool_schemas = get_tool_schemas()

    # Track all tool calls for output
    tool_calls_log: list[dict[str, object]] = []

    # Maximum tool calls limit
    max_tool_calls = 20
    tool_call_count = 0

    while tool_call_count < max_tool_calls:
        # Call LLM with current messages and tool definitions
        response_data = call_llm(messages, api_base, api_key, model, tools=tool_schemas)

        # Extract the assistant message
        assistant_message = response_data["choices"][0]["message"]

        # Check if LLM wants to call tools
        tool_calls = assistant_message.get("tool_calls")

        if tool_calls:
            # LLM wants to call tools
            print(f"Tool calls detected: {len(tool_calls)}", file=sys.stderr)

            # Add assistant message with tool_calls to history
            messages.append(assistant_message)

            # Execute each tool call
            for tool_call in tool_calls:
                tool_call_count += 1

                # Extract tool info (OpenAI format)
                function_info = tool_call.get("function", {})
                tool_name = function_info.get("name", "unknown")

                # Parse arguments (they come as JSON string)
                try:
                    tool_args = json.loads(function_info.get("arguments", "{}"))
                except json.JSONDecodeError:
                    tool_args = {}

                # Execute the tool
                print(f"Executing tool: {tool_name} with args: {tool_args}", file=sys.stderr)
                result = execute_tool(tool_name, tool_args)
                print(f"Tool result: {result[:100]}...", file=sys.stderr)

                # Log the tool call for output
                tool_calls_log.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result,
                })

                # Add tool result to messages (OpenAI format)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": result,
                })

            # Continue loop - LLM will process tool results
            continue

        else:
            # No tool calls - LLM provided final answer
            print("No tool calls - extracting final answer", file=sys.stderr)
            # Use (msg.get("content") or "") instead of msg.get("content", "") 
            # because the field may be present but null, not missing
            final_answer = assistant_message.get("content") or ""

            # Extract source from the answer (look for filepath.md#anchor pattern)
            source_match = re.search(r"(\w+/[\w-]+\.md#[\w-]+)", final_answer)
            source = source_match.group(1) if source_match else ""

            return {
                "answer": final_answer,
                "source": source,
                "tool_calls": tool_calls_log,
            }

    # Max tool calls reached
    print(f"Max tool calls ({max_tool_calls}) reached", file=sys.stderr)
    return {
        "answer": "I reached the maximum number of tool calls. Here's what I found so far.",
        "source": "",
        "tool_calls": tool_calls_log,
    }


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Error: No question provided", file=sys.stderr)
        print("Usage: uv run agent.py \"Your question\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
    print(f"Question: {question}", file=sys.stderr)

    env = load_env()
    api_base = env.get("LLM_API_BASE")
    api_key = env.get("LLM_API_KEY")
    model = env.get("LLM_MODEL")

    if not all([api_base, api_key, model]):
        print("Error: Missing LLM_API_BASE, LLM_API_KEY, or LLM_MODEL", file=sys.stderr)
        sys.exit(1)

    # Run the agentic loop
    result = run_agentic_loop(question, api_base, api_key, model)

    # Output JSON to stdout
    print(json.dumps(result))


if __name__ == "__main__":
    main()
