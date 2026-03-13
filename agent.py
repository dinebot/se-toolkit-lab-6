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


# System prompt for the documentation agent
SYSTEM_PROMPT = """You are a documentation assistant. You have access to tools that let you read files and list directories in a project wiki.

When answering questions:
1. First use `list_files` to discover what files exist in the wiki directory
2. Then use `read_file` to read relevant files and find the answer
3. Always include a source reference in your answer using the format: `filepath.md#section-name`
4. The section name should be a lowercase anchor with hyphens (e.g., `#resolving-merge-conflicts`)

Be concise and accurate. Only use information from the files you read.
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
    else:
        return f"Error: Unknown tool '{tool_name}'"


def load_env() -> dict[str, str]:
    """Load environment variables from .env.agent.secret."""
    env_file = Path(__file__).parent / ".env.agent.secret"
    env_vars: dict[str, str] = {}

    if not env_file.exists():
        print(f"Error: {env_file} not found", file=sys.stderr)
        sys.exit(1)

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
    max_tool_calls = 10
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
            final_answer = assistant_message.get("content", "")

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
