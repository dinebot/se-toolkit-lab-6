#!/usr/bin/env python3
"""
Agent CLI - Calls an LLM to answer questions.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "tool_calls": []}
    Debug logs to stderr.
"""

import json
import os
import sys
from pathlib import Path

import httpx


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


def call_lllm(question: str, api_base: str, api_key: str, model: str) -> str:
    """Call the LLM API and return the answer."""
    url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": question}],
    }

    print(f"Calling LLM at {url}...", file=sys.stderr)

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    answer = data["choices"][0]["message"]["content"]
    print(f"LLM response received.", file=sys.stderr)
    return answer


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

    answer = call_lllm(question, api_base, api_key, model)

    result = {
        "answer": answer,
        "tool_calls": [],
    }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
