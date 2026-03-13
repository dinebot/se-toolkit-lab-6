"""Regression tests for agent.py CLI.

These tests run agent.py as a subprocess and verify the JSON output structure.
Run with: uv run pytest backend/tests/unit/test_agent.py -v

Note: These tests require a working LLM API connection.
Set up .env.agent.secret with valid credentials before running.
"""

import json
import subprocess
from pathlib import Path


# Path to the project root (where agent.py lives)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
AGENT_PATH = PROJECT_ROOT / "agent.py"


def run_agent(question: str) -> subprocess.CompletedProcess:
    """Run agent.py with the given question."""
    return subprocess.run(
        ["uv", "run", "agent.py", question],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )


class TestAgentOutput:
    """Tests for agent.py output structure."""

    def test_agent_returns_valid_json(self):
        """Test that agent.py outputs valid JSON with required fields.
        
        This test verifies:
        - Exit code is 0
        - stdout contains valid JSON
        - 'answer' field exists and is a non-empty string
        - 'tool_calls' field exists and is a list
        """
        result = run_agent("What is 2+2?")

        # Check exit code
        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        # Parse stdout as JSON
        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise AssertionError(
                f"Agent output is not valid JSON: {result.stdout!r}"
            ) from e

        # Check required fields exist
        assert "answer" in output, "Missing 'answer' field in output"
        assert "tool_calls" in output, "Missing 'tool_calls' field in output"

        # Check field types
        assert isinstance(output["answer"], str), "'answer' must be a string"
        assert isinstance(output["tool_calls"], list), "'tool_calls' must be an array"

        # Check answer is non-empty
        assert len(output["answer"]) > 0, "'answer' should not be empty"

    def test_tool_calls_is_empty_list(self):
        """Test that tool_calls is an empty list for Task 1 (no tools yet)."""
        result = run_agent("Hello!")

        assert result.returncode == 0

        output = json.loads(result.stdout)
        assert output["tool_calls"] == [], "tool_calls should be an empty list"

    def test_stderr_contains_debug_output(self):
        """Test that debug output goes to stderr, not stdout.
        
        stdout should only contain the JSON response (single line).
        All debug/progress messages should go to stderr.
        """
        result = run_agent("Test question")

        # stdout should only contain JSON (single line, no debug messages)
        stdout_lines = result.stdout.strip().split("\n")
        assert len(stdout_lines) == 1, "stdout should contain only one line (JSON)"

        # Verify it's valid JSON
        json.loads(result.stdout)

        # Agent should complete successfully
        assert result.returncode == 0

    def test_agent_handles_missing_question(self):
        """Test that agent.py shows usage when no question is provided."""
        result = subprocess.run(
            ["uv", "run", "agent.py"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )

        # Should exit with non-zero code
        assert result.returncode != 0

        # Should show usage on stderr
        assert "Usage" in result.stderr or "question" in result.stderr.lower()

        # stdout should be empty
        assert result.stdout.strip() == ""

    def test_merge_conflict_question_uses_read_file(self):
        """Test that asking about merge conflicts uses read_file tool.

        This test verifies:
        - Agent uses read_file tool to find information in wiki
        - Source field contains wiki/git-workflow.md reference
        """
        result = run_agent("How do you resolve a merge conflict?")

        # Check exit code
        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        # Parse stdout as JSON
        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise AssertionError(
                f"Agent output is not valid JSON: {result.stdout!r}"
            ) from e

        # Check that tool_calls contains read_file
        tool_calls = output.get("tool_calls", [])
        assert len(tool_calls) > 0, "Expected at least one tool call"

        tool_names = [call.get("tool") for call in tool_calls]
        assert "read_file" in tool_names, "Expected read_file to be called"

        # Check that source field contains wiki/git-workflow.md
        source = output.get("source", "")
        assert "wiki/git-workflow.md" in source, \
            f"Expected 'wiki/git-workflow.md' in source, got: {source}"

    def test_wiki_files_question_uses_list_files(self):
        """Test that asking about wiki files uses list_files tool.

        This test verifies:
        - Agent uses list_files tool to discover wiki contents
        """
        result = run_agent("What files are in the wiki?")

        # Check exit code
        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        # Parse stdout as JSON
        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise AssertionError(
                f"Agent output is not valid JSON: {result.stdout!r}"
            ) from e

        # Check that tool_calls contains list_files
        tool_calls = output.get("tool_calls", [])
        assert len(tool_calls) > 0, "Expected at least one tool call"

        tool_names = [call.get("tool") for call in tool_calls]
        assert "list_files" in tool_names, "Expected list_files to be called"

