# Task 2 Plan: The Documentation Agent

## Overview

This task extends the Task 1 CLI to support tool-calling. The agent will have two tools (`read_file`, `list_files`) to navigate the project wiki and answer questions based on actual documentation.

---

## 1. Tool Schema Design

### Tools to Define

Two tools will be registered as function-calling schemas:

| Tool | Parameter | Type | Description |
|------|-----------|------|-------------|
| `read_file` | `path` | string | Read the contents of a file at the given path. Use this to find specific information in documentation files. |
| `list_files` | `path` | string | List files and directories at the given path. Use this to discover what files exist in a directory before reading them. |

### Schema Format

Tools will be defined using OpenAI-compatible function-calling format:

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read the contents of a file...",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Relative path from project root"
        }
      },
      "required": ["path"]
    }
  }
}
```

### System Prompt Strategy

The system prompt will instruct the LLM to:
1. Use `list_files` first to discover wiki files when asked about documentation
2. Use `read_file` to find specific information in relevant files
3. Include a source reference (file path + section anchor) in the final answer
4. Not attempt to read files outside the project directory

---

## 2. Agentic Loop Implementation

### Loop Flow

```
1. Initialize messages list with system prompt + user question
2. Send messages + tool definitions to LLM
3. Parse response:
   - If tool_calls present:
     a. Execute each tool
     b. Append tool results as "tool" role messages
     c. Increment call counter
     d. If counter >= 10, stop and use current answer
     e. Go back to step 2
   - If no tool_calls (content field has text):
     a. Extract answer and source from content
     b. Output JSON and exit
```

### Message Structure

Messages will be tracked in a conversation history:

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After tool call:
    {"role": "assistant", "tool_calls": [...]},
    {"role": "tool", "tool_call_id": "...", "content": "..."},
    # ... more iterations
]
```

### Tool Call Tracking

Each tool call will be recorded for the output:

```python
tool_calls_log = [
    {
        "tool": "read_file",
        "args": {"path": "wiki/git-workflow.md"},
        "result": "file contents here..."
    }
]
```

### Exit Conditions

- **Success:** LLM returns a message with `content` (no `tool_calls`)
- **Max calls:** 10 tool calls reached (safety limit)
- **Error:** Tool execution fails (return error message)

---

## 3. Path Security

### Threat Model

Attackers could try to:
- Read sensitive files: `../../.env`, `/etc/passwd`
- Escape project directory using `../` traversal

### Defense Strategy

1. **String check:** Reject any path containing `..`
2. **Resolve check:** After resolving to absolute path, verify it starts with project root
3. **Error handling:** Return clear error message if path is invalid

### Implementation

```python
def validate_path(path: str) -> Path:
    """Validate path stays within project root."""
    # Reject .. in path string
    if ".." in path:
        raise ValueError("Path traversal not allowed")
    
    # Resolve to absolute and check prefix
    project_root = Path(__file__).parent.parent
    full_path = (project_root / path).resolve()
    
    if not str(full_path).startswith(str(project_root)):
        raise ValueError("Path escapes project directory")
    
    return full_path
```

### Error Messages

- `"Error: Path traversal (..) not allowed"`
- `"Error: File not found: {path}"`
- `"Error: Not a directory: {path}"`

---

## 4. Response Format

### Output JSON Structure

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

### Field Requirements

- `answer` (string, required): The final answer extracted from LLM response
- `source` (string, required): Wiki section reference (file path + anchor)
- `tool_calls` (array, required): All tool calls made during the loop

### Source Extraction

The system prompt will instruct the LLM to include source references in a consistent format:
- Format: `{file_path}#{section_anchor}`
- Example: `wiki/git-workflow.md#resolving-merge-conflicts`

---

## 5. Implementation Steps

1. Define `read_file()` and `list_files()` functions with path validation
2. Create tool schemas (JSON format for LLM)
3. Implement agentic loop with message tracking
4. Add system prompt with tool usage instructions
5. Update output format to include `source` and `tool_calls`
6. Test with sample questions

---

## 6. Testing Strategy

### Test Cases

1. **"How do you resolve a merge conflict?"**
   - Expected: `read_file` in tool_calls, `wiki/git-workflow.md` in source

2. **"What files are in the wiki?"**
   - Expected: `list_files` in tool_calls

### Test Approach

- Run `agent.py` as subprocess
- Parse JSON output
- Assert on `tool_calls` array contents
- Assert on `source` field format

---

## 7. Documentation Updates

Update `AGENT.md` to document:
- Tool definitions and their purposes
- Agentic loop flow diagram
- System prompt strategy
- Path security approach
