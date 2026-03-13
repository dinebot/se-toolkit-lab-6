#!/usr/bin/env python3
"""
Agent CLI - Calls an LLM and returns a structured JSON response.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "tool_calls": []}
    All debug output goes to stderr.
"""

import json
import os
import sys
from pathlib import Path

import httpx


def load_env() -> dict[str, str]:
    """
    Load environment variables from .env.agent.secret.
    
    Returns:
        Dictionary with LLM_API_KEY, LLM_API_BASE, LLM_MODEL
    
    Raises:
        SystemExit: If file is missing or required variables are not set.
    """
    env_path = Path(__file__).parent / ".env.agent.secret"
    
    if not env_path.exists():
        print(f"Error: {env_path} not found", file=sys.stderr)
        print("Copy .env.agent.example to .env.agent.secret and fill in your credentials", file=sys.stderr)
        sys.exit(1)
    
    env_vars: dict[str, str] = {}
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()
    
    # Validate required variables
    required = ["LLM_API_KEY", "LLM_API_BASE", "LLM_MODEL"]
    for var in required:
        if var not in env_vars or not env_vars[var]:
            print(f"Error: {var} is not set in .env.agent.secret", file=sys.stderr)
            sys.exit(1)
    
    return env_vars


def call_llm(question: str, api_key: str, api_base: str, model: str) -> str:
    """
    Call the LLM API and get a response.
    
    Args:
        question: The user's question
        api_key: API key for authentication
        api_base: Base URL of the API endpoint
        model: Model name to use
    
    Returns:
        The LLM's text response
    
    Raises:
        SystemExit: If the API request fails
    """
    url = f"{api_base}/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": question}
        ],
    }
    
    print(f"Calling LLM at {url}...", file=sys.stderr)
    
    try:
        # 60-second timeout as per task requirements
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract the answer from the response
            # OpenAI-compatible format: choices[0].message.content
            if "choices" not in data or not data["choices"]:
                print("Error: No choices in API response", file=sys.stderr)
                sys.exit(1)
            
            answer = data["choices"][0]["message"].get("content", "")
            
            if not answer:
                print("Warning: Empty response from LLM", file=sys.stderr)
            
            return answer
            
    except httpx.TimeoutException:
        print("Error: LLM request timed out (60s limit)", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"Error: API returned status {e.response.status_code}", file=sys.stderr)
        print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except httpx.RequestError as e:
        print(f"Error: Failed to connect to LLM API: {e}", file=sys.stderr)
        sys.exit(1)


def format_response(answer: str) -> dict:
    """
    Format the response as required by the task.
    
    Args:
        answer: The LLM's text response
    
    Returns:
        Dictionary with 'answer' and 'tool_calls' fields
    """
    return {
        "answer": answer,
        "tool_calls": []  # Empty for Task 1, will be populated in Task 2
    }


def main() -> None:
    """Main entry point."""
    # Parse command-line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"<your question>\"", file=sys.stderr)
        sys.exit(1)
    
    question = sys.argv[1]
    
    # Load environment configuration
    env = load_env()
    
    # Call the LLM
    answer = call_llm(
        question=question,
        api_key=env["LLM_API_KEY"],
        api_base=env["LLM_API_BASE"],
        model=env["LLM_MODEL"],
    )
    
    # Format and output the response
    response = format_response(answer)
    
    # Output valid JSON to stdout (single line, no pretty printing)
    print(json.dumps(response))
    
    # Exit with success
    sys.exit(0)


if __name__ == "__main__":
    main()

