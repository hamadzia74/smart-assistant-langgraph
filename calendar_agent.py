"""
calendar_agent.py - 📅 the Google Calendar sub-agent, powered by the workspace-mcp server.

Tools it gets from the MCP server (filtered in mcp_servers.ALLOWED_TOOLS):
    list_calendars, get_events, query_freebusy -> READ   (safe, no approval)
    manage_event                               -> WRITE  (create / update / delete,
                                                          needs your approval)
    start_google_auth                          -> the first-time Google login
"""

import os

from langchain_core.tools import BaseTool

from agent_builder import build_tool_agent

# Tools that change your calendar. The approval node asks you before they run.
SENSITIVE_TOOLS = {"manage_event"}


def system_prompt() -> str:
    """Built in a function so it reads USER_GOOGLE_EMAIL from .env at the right time."""
    email = os.getenv("USER_GOOGLE_EMAIL", "")
    return (
        "You are the Calendar Agent. You read and manage the user's Google Calendar. "
        f"The user's Google email is {email}; pass it as user_google_email to every tool. "
        "Use RFC3339 times with the user's UTC offset, e.g. 2026-10-03T15:00:00+05:00. "
        "Meetings are 30 minutes long unless the user says otherwise. "
        "To create a meeting call manage_event with action='create'; put guest emails in "
        "attendees and set send_updates='all' so guests receive the invitation email. "
        "Set add_google_meet=true when the user asks for an online / Meet / video meeting. "
        "Before creating, check for clashes with get_events or query_freebusy. "
        "When listing meetings show: time, title, attendees and the Meet link if any. "
        "If a tool says authentication is needed, show the user the login link exactly "
        "and ask them to open it, then try again."
    )


def build_calendar_agent(mcp_tools: list[BaseTool]):
    """Returns the compiled Calendar sub-agent graph."""
    return build_tool_agent("calendar", mcp_tools, system_prompt(), SENSITIVE_TOOLS)
