# Agent Architecture

This document describes the architecture of the documentation agent implemented in `agent.py`.

## Overview

The agent is a CLI tool that answers questions by querying an LLM and using tools to access project documentation. It implements an **agentic loop** that allows the LLM to request tool calls, receive results, and iterate until it has enough information to provide a final answer.

## Tools

The agent has two tools available:

### `read_file`

Reads the contents of a file from the project repository.

**Parameters:**
- `path` (string, required): Relative path from project root (e.g., `wiki/git-workflow.md`)

**Returns:**
- File contents as a string
- Error message if file doesn't exist or path is invalid

**Security:**
- Rejects paths containing `..` (path traversal prevention)
- Validates that resolved path stays within project root directory

### `list_files`

Lists files and directories at a given path.

**Parameters:**
- `path` (string, required): Relative directory path from project root (e.g., `wiki`)

**Returns:**
- Newline-separated listing of entries (directories suffixed with `/`)
- Error message if directory doesn't exist or path is invalid

**Security:**
- Same path validation as `read_file`

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
│     │     → Extract source reference                           │
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

The system prompt instructs the LLM on how to use the tools effectively:

```
You are a documentation assistant. You have access to tools that let you 
read files and list directories in a project wiki.

When answering questions:
1. First use `list_files` to discover what files exist in the wiki directory
2. Then use `read_file` to read relevant files and find the answer
3. Always include a source reference in your answer using the format: 
   `filepath.md#section-name`
4. The section name should be a lowercase anchor with hyphens 
   (e.g., `#resolving-merge-conflicts`)

Be concise and accurate. Only use information from the files you read.
```

### Key Instructions

- **Discovery first**: Use `list_files` before `read_file` to explore the wiki
- **Source attribution**: Always include a `filepath.md#section` reference
- **Grounding**: Only use information from files actually read

## Output Format

The agent outputs JSON to stdout:

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "..."
    }
  ]
}
```

### Fields

- `answer` (string, required): The final answer from the LLM
- `source` (string, required): Wiki section reference (`filepath.md#section`)
- `tool_calls` (array, required): All tool calls made during execution

## Path Security

The agent prevents directory traversal attacks:

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

## Usage

```bash
# Ask a question
uv run agent.py "How do you resolve a merge conflict?"

# Output goes to stdout as JSON
# Debug logs go to stderr
```

## Implementation Details

- **LLM API**: OpenAI-compatible chat completions endpoint
- **Timeout**: 60 seconds per API call
- **Tool call limit**: Maximum 10 tool calls per question
- **Debug output**: All progress messages go to stderr (not stdout)
