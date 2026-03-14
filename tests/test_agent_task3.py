"""Regression tests for agent.py CLI - Task 3 (System Agent).

These tests run agent.py as a subprocess and verify the JSON output structure
and tool usage for the query_api tool.

Run with: uv run pytest tests/test_agent_task3.py -v

Note: These tests require:
1. A working LLM API connection (.env.agent.secret)
2. A running backend API (.env.docker.secret with LMS_API_KEY)
"""

import json
import re
import subprocess
from pathlib import Path


# Path to the project root (where agent.py lives)
PROJECT_ROOT = Path(__file__).parent.parent
AGENT_PATH = PROJECT_ROOT / "agent.py"


def run_agent(question: str) -> subprocess.CompletedProcess:
    """Run agent.py with the given question."""
    return subprocess.run(
        ["uv", "run", "agent.py", question],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )


class TestSystemAgentTools:
    """Tests for agent.py tool usage in Task 3."""

    def test_backend_framework_uses_read_file(self):
        """Test that agent uses read_file for source code questions.

        Question: "What Python web framework does the backend use?"
        Expected: Agent reads backend source code to find FastAPI.
        """
        result = run_agent("What Python web framework does the backend use?")

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

        # Check that read_file was used
        tools_used = [tc.get("tool") for tc in output["tool_calls"]]
        assert "read_file" in tools_used, (
            f"Expected 'read_file' in tool_calls, got: {tools_used}"
        )

        # Check answer contains FastAPI
        assert "FastAPI" in output["answer"], (
            f"Expected 'FastAPI' in answer, got: {output['answer']}"
        )

    def test_item_count_uses_query_api(self):
        """Test that agent uses query_api for data questions.

        Question: "How many items are currently stored in the database?"
        Expected: Agent queries /items/ endpoint to get the count.
        """
        result = run_agent("How many items are currently stored in the database?")

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

        # Check that query_api was used
        tools_used = [tc.get("tool") for tc in output["tool_calls"]]
        assert "query_api" in tools_used, (
            f"Expected 'query_api' in tool_calls, got: {tools_used}"
        )

        # Check answer contains a number > 0
        numbers = re.findall(r'\d+', output["answer"])
        assert any(int(n) > 0 for n in numbers), (
            f"Expected a positive number in answer, got: {output['answer']}"
        )

    def test_status_code_uses_query_api(self):
        """Test that agent uses query_api for status code questions.

        Question: "What HTTP status code does the API return when you request /items/ without authentication?"
        Expected: Agent queries API without auth header to get 401 or 403.
        """
        result = run_agent("What HTTP status code does the API return when you request /items/ without an authentication header?")

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

        # Check that query_api was used
        tools_used = [tc.get("tool") for tc in output["tool_calls"]]
        assert "query_api" in tools_used, (
            f"Expected 'query_api' in tool_calls, got: {tools_used}"
        )

        # Check answer contains 401 or 403
        assert "401" in output["answer"] or "403" in output["answer"] or "401" in str(output) or "403" in str(output), (
            f"Expected '401' or '403' in answer, got: {output['answer']}"
        )

    def test_wiki_branch_protection_uses_read_file(self):
        """Test that agent uses read_file for wiki questions.

        Question: "According to the project wiki, what steps are needed to protect a branch?"
        Expected: Agent reads wiki files to find branch protection steps.
        """
        result = run_agent("According to the project wiki, what steps are needed to protect a branch on GitHub?")

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

        # Check that read_file or list_files was used (wiki navigation)
        tools_used = [tc.get("tool") for tc in output["tool_calls"]]
        assert "read_file" in tools_used or "list_files" in tools_used, (
            f"Expected 'read_file' or 'list_files' in tool_calls, got: {tools_used}"
        )

        # Check answer contains relevant keywords
        answer_lower = output["answer"].lower()
        assert "branch" in answer_lower or "protect" in answer_lower, (
            f"Expected 'branch' or 'protect' in answer, got: {output['answer']}"
        )
