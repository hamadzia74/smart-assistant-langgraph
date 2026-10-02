"""
mcp_servers.py - connects to the 3 MCP servers and turns their tools into LangChain tools.

WHAT IS MCP? (Model Context Protocol)
    A standard "plug" between AI apps and outside services.
    Someone writes an MCP SERVER once (e.g. "GitHub"), and ANY AI app (LangGraph,
    Claude Desktop, Cursor...) can use its tools without writing GitHub code itself.

    Our app = MCP CLIENT.    GitHub / Calendar / Gmail = MCP SERVERS.

    Lecture 08 SIMULATED a server inside the same Python file. Here we connect to
    REAL servers, in the two ways MCP supports:

    1. HTTP  ("streamable_http") - the server runs on the internet.
             GitHub hosts its official server at https://api.githubcopilot.com/mcp/
    2. STDIO - we START the server as a child process on our own computer and talk
             to it through its stdin/stdout (like typing into a program and reading
             what it prints). Used for the Google Calendar and Gmail servers.

THE 4 STEPS TO USE ANY MCP SERVER (you will see them in open_server() below):
    1. TRANSPORT  -> open the "pipe" (an HTTP connection, or start a process)
    2. SESSION    -> wrap the pipe in an MCP ClientSession (speaks the protocol)
    3. INITIALIZE -> handshake: "hi, I'm a client, which features do you have?"
    4. LIST TOOLS -> ask for the tools and convert them to LangChain tools
                     (load_mcp_tools from langchain-mcp-adapters does this)

WHY KEEP THE CONNECTION OPEN?
    We open each server ONCE at startup and close it when the app exits.
    Starting a new process for every tool call would be slow, and the Google
    login (which runs a small web server inside the Gmail/Calendar process)
    would die before you finish logging in.
"""

import asyncio
import os
import shutil
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from utils import has_key

PROJECT_DIR = Path(__file__).resolve().parent
LOG_DIR = PROJECT_DIR / "logs"            # each server writes its own log file here
TOKEN_DIR = PROJECT_DIR / ".google_tokens"  # Google login tokens are saved here (git-ignored!)


# ============================================================
# Which tools each agent may use (an "allow-list")
# ============================================================
# Servers expose MANY tools. Fewer tools = the LLM picks the right one more often,
# and it cannot do things we never wanted (like deleting labels).
ALLOWED_TOOLS = {
    "calendar": {
        "list_calendars",     # which calendars do I have?
        "get_events",         # read meetings in a time range
        "manage_event",       # create / update / delete one event
        "query_freebusy",     # am I free at 3pm?
        "start_google_auth",  # first-time Google login
    },
    "gmail": {
        "search_gmail_messages",            # find emails (Gmail search syntax)
        "get_gmail_message_content",        # read one email
        "get_gmail_messages_content_batch", # read several emails
        "get_gmail_thread_content",         # read a whole conversation
        "draft_gmail_message",              # save a draft (does NOT send)
        "send_gmail_message",               # send an email now
        "start_google_auth",                # first-time Google login
    },
    # None = keep every tool the server offers (GitHub is limited by headers below instead).
    "github": None,
}


# ============================================================
# Server settings
# ============================================================
def _uvx_command() -> str:
    """
    Finds the `uvx` program, which downloads and runs Python tools in one go
    (like `npx` for Node). It is installed by `pip install uv` (requirements.txt).
    Path(sys.executable).parent = the folder of the Python that runs this app,
    i.e. .venv/Scripts on Windows, where pip put uvx.exe.
    """
    found = shutil.which("uvx")
    if found:
        return found
    exe = "uvx.exe" if sys.platform == "win32" else "uvx"
    return str(Path(sys.executable).parent / exe)


def _google_server(service: str, port: int) -> dict:
    """
    Settings to start the open-source `workspace-mcp` server for ONE Google service.

    We start it twice: once with "--tools calendar" and once with "--tools gmail",
    so each sub-agent has its OWN server with ONLY its own tools.

    env (environment variables given to the child process):
        GOOGLE_OAUTH_CLIENT_ID / SECRET -> identify OUR app to Google (from Google Cloud)
        USER_GOOGLE_EMAIL               -> whose calendar / mailbox to use
        WORKSPACE_MCP_CREDENTIALS_DIR   -> where the login token is saved
                                           (separate folder per service so they never clash)
        WORKSPACE_MCP_PORT              -> the port of the small login web server
                                           (different per service so both can run together)
    """
    return {
        "transport": "stdio",
        "command": _uvx_command(),
        "args": ["workspace-mcp", "--tools", service, "--tool-tier", "complete", "--single-user"],
        "env": {
            "GOOGLE_OAUTH_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
            "GOOGLE_OAUTH_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "USER_GOOGLE_EMAIL": os.getenv("USER_GOOGLE_EMAIL", ""),
            "WORKSPACE_MCP_CREDENTIALS_DIR": str(TOKEN_DIR / service),
            "WORKSPACE_MCP_PORT": str(port),
            "OAUTHLIB_INSECURE_TRANSPORT": "1",  # allows the http://localhost login redirect (local only)
            "PYTHONIOENCODING": "utf-8",
        },
    }


def server_settings() -> dict[str, dict | str]:
    """
    Returns {server_name: settings} for every server.
    If a key is missing, the value is a STRING explaining what is missing instead,
    so the banner can show "❌ off - GITHUB_TOKEN missing".
    """
    servers: dict[str, dict | str] = {}

    if has_key("GITHUB_TOKEN"):
        servers["github"] = {
            "transport": "streamable_http",
            "url": "https://api.githubcopilot.com/mcp/",
            "headers": {
                # A Personal Access Token proves to GitHub who we are.
                "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
                # Only load these groups of tools ("toolsets") ...
                "X-MCP-Toolsets": "context,repos,issues,pull_requests,users",
                # ... and only the READ tools. The agent can look, but never change your repos.
                "X-MCP-Readonly": "true",
            },
        }
    else:
        servers["github"] = "GITHUB_TOKEN missing in .env"

    google_ready = has_key("GOOGLE_OAUTH_CLIENT_ID") and has_key("GOOGLE_OAUTH_CLIENT_SECRET") \
        and has_key("USER_GOOGLE_EMAIL")
    if google_ready:
        servers["calendar"] = _google_server("calendar", port=8001)
        servers["gmail"] = _google_server("gmail", port=8002)
    else:
        reason = "GOOGLE_OAUTH_CLIENT_ID / SECRET / USER_GOOGLE_EMAIL missing in .env"
        servers["calendar"] = reason
        servers["gmail"] = reason

    return servers


# ============================================================
# Connecting
# ============================================================
async def open_server(stack: AsyncExitStack, name: str, settings: dict) -> list[BaseTool]:
    """
    Opens ONE MCP server and returns its tools as LangChain tools.

    `stack` is an AsyncExitStack: a list of "things to close later".
    Every `await stack.enter_async_context(x)` opens x now AND remembers to close
    it when the stack closes (when the app exits). It is the same as writing
    `async with x:` - but the connection stays open after this function returns.
    """
    # ---- Step 1: TRANSPORT (the pipe) ----
    if settings["transport"] == "stdio":
        LOG_DIR.mkdir(exist_ok=True)
        # The server prints its own logs on stderr. We send them to a file so they
        # don't mix with our nice terminal output. Read logs/<name>.log if something fails.
        log_file = stack.enter_context(open(LOG_DIR / f"{name}.log", "a", encoding="utf-8"))
        params = StdioServerParameters(
            command=settings["command"], args=settings["args"], env=settings["env"]
        )
        read, write = await stack.enter_async_context(stdio_client(params, errlog=log_file))
    else:
        http_client = create_mcp_http_client(headers=settings["headers"])
        read, write, _ = await stack.enter_async_context(
            streamable_http_client(settings["url"], http_client=http_client)
        )

    # ---- Step 2: SESSION (speaks the MCP protocol over the pipe) ----
    session = await stack.enter_async_context(ClientSession(read, write))

    # ---- Step 3: INITIALIZE (the handshake) ----
    # wait_for gives up after 120 s instead of waiting forever (e.g. wrong token,
    # no internet). The FIRST run can take ~1 minute because uvx downloads the server.
    await asyncio.wait_for(session.initialize(), timeout=120)

    # ---- Step 4: LIST TOOLS + convert each to a LangChain BaseTool ----
    # load_mcp_tools reads each tool's name, description and JSON input schema,
    # and builds a LangChain tool that sends a "tools/call" request when used.
    tools = await load_mcp_tools(session)

    allowed = ALLOWED_TOOLS.get(name)
    if allowed is not None:
        tools = [t for t in tools if t.name in allowed]
    return tools


async def connect_all(stack: AsyncExitStack) -> dict[str, list[BaseTool] | str]:
    """
    Opens every configured server. Returns {name: tools} or {name: "error text"}.

    One broken server must NOT stop the others, so each server gets its own
    small exit stack. If it fails, we close just that one and record the error.
    If it works, we hand its "close later" job to the main stack.
    """
    results: dict[str, list[BaseTool] | str] = {}

    for name, settings in server_settings().items():
        if isinstance(settings, str):      # a string means "not configured"
            results[name] = settings
            continue

        server_stack = AsyncExitStack()
        try:
            results[name] = await open_server(server_stack, name, settings)
            stack.push_async_callback(server_stack.aclose)
        except Exception as e:
            await server_stack.aclose()
            results[name] = f"could not connect: {type(e).__name__} (see logs/{name}.log)"

    return results
