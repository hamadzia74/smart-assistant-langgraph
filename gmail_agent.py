"""
gmail_agent.py - 📧 the Gmail sub-agent, powered by the workspace-mcp server.

Tools:
    from the MCP server (filtered in mcp_servers.ALLOWED_TOOLS):
        search_gmail_messages, get_gmail_message_content, ... -> READ   (safe)
        draft_gmail_message                                   -> saves a DRAFT (safe,
                                                                 you still press Send yourself)
        send_gmail_message                                    -> SENDS  (needs approval)
    our own tool (scheduler.py):
        schedule_email                                        -> sends LATER (needs approval)
"""

import os

from langchain_core.tools import BaseTool

from agent_builder import build_tool_agent
from scheduler import make_schedule_email_tool

SENSITIVE_TOOLS = {"send_gmail_message", "schedule_email"}


def system_prompt() -> str:
    email = os.getenv("USER_GOOGLE_EMAIL", "")
    name = os.getenv("USER_NAME", "")
    return (
        "You are the Gmail Agent. You read, write, draft and send emails for the user. "
        f"The user's Gmail address is {email}; pass it as user_google_email to Gmail tools. "
        + (f"Sign emails with the user's name: {name}. " if name else "")
        + "Write clear, polite, well-structured emails with a subject line. "
        "Decide the tool from the user's words: "
        "'draft' / 'write' / 'prepare' -> draft_gmail_message; "
        "'send' -> send_gmail_message; "
        "'send at <time>' / 'schedule' -> schedule_email (ISO time with UTC offset). "
        "If the recipient's email address is missing, ask for it - never guess an address. "
        "To find emails use Gmail search syntax in search_gmail_messages, "
        "e.g. 'from:ali is:unread newer_than:2d'. "
        "If a tool says authentication is needed, show the user the login link exactly "
        "and ask them to open it, then try again."
    )


def build_gmail_agent(mcp_tools: list[BaseTool]):
    """Returns the compiled Gmail sub-agent graph (MCP tools + our schedule_email tool)."""
    tools = list(mcp_tools)

    # Find the MCP "send" tool and build schedule_email on top of it.
    send_tool = next((t for t in mcp_tools if t.name == "send_gmail_message"), None)
    if send_tool is not None:
        tools.append(make_schedule_email_tool(send_tool))

    return build_tool_agent("gmail", tools, system_prompt(), SENSITIVE_TOOLS)
