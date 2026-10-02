"""
github_agent.py - 🐙 the GitHub sub-agent, powered by GitHub's official MCP server.

Notice how SHORT this file is. We wrote ZERO GitHub code: no API calls, no URLs.
All tools (search repositories, list issues, read files, ...) come from the MCP
server. That is the whole point of MCP - mcp_servers.py connects, and the tools
arrive ready to use.

The server is opened in READ-ONLY mode (see mcp_servers.py), so this agent can
look at anything you can see on GitHub, but it can never change your repos.
"""

from langchain_core.tools import BaseTool

from agent_builder import build_tool_agent

SYSTEM_PROMPT = (
    "You are the GitHub Agent. You answer questions about GitHub repositories, "
    "issues, pull requests, commits, files and users, using your GitHub tools. "
    "If the user says 'my repos' or 'my account', first call get_me to learn their username. "
    "If the owner of a repo is not given, search for it or ask. "
    "Summarise results clearly: use bullet points, include links (html_url) when available, "
    "and never dump raw JSON."
)


def build_github_agent(mcp_tools: list[BaseTool]):
    """Returns the compiled GitHub sub-agent graph, using the tools from the MCP server."""
    # Read-only tools -> nothing needs approval.
    return build_tool_agent("github", mcp_tools, SYSTEM_PROMPT)
