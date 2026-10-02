# 06 · 🔌 MCP and the three MCP sub-agents

Files: `mcp_servers.py`, `github_agent.py`, `calendar_agent.py`, `gmail_agent.py`, `scheduler.py`.

## What problem does MCP solve?

Without MCP, to let an agent use GitHub you'd write code for every GitHub API call: list issues, read a file, search code… Then the same again for Calendar, and again for Gmail. And again for every AI framework.

With **MCP (Model Context Protocol)**, someone writes an **MCP server** for a service **once**. Any AI app (an **MCP client**, like ours) can connect and get **ready-made tools**:

```
   Our app (MCP CLIENT)                     MCP SERVERS                       Real services
 ┌───────────────────────┐   HTTP    ┌──────────────────────────┐
 │ 🐙 github_agent       │ ◀───────▶ │ GitHub's hosted server   │ ───▶ GitHub API
 │ 📅 calendar_agent     │ ◀─stdio─▶ │ workspace-mcp --calendar │ ───▶ Google Calendar API
 │ 📧 gmail_agent        │ ◀─stdio─▶ │ workspace-mcp --gmail    │ ───▶ Gmail API
 └───────────────────────┘           └──────────────────────────┘
```

Lecture 08 **simulated** a server inside one Python file. Here the servers are **real**, and notice how short the agent files are: **zero** lines of GitHub/Calendar/Gmail API code.

**Two transports** (ways to reach a server):
* **HTTP (`streamable_http`)**: the server runs on the internet. GitHub hosts its own at `https://api.githubcopilot.com/mcp/`.
* **stdio**: we **start** the server as a child process on our computer and talk through its *standard input/output* (like typing into a program and reading what it prints).

---

# Part A · `mcp_servers.py`

## A1. The allow-list

```python
ALLOWED_TOOLS = {
    "calendar": {"list_calendars", "get_events", "manage_event", "query_freebusy", "start_google_auth"},
    "gmail": {"search_gmail_messages", ..., "draft_gmail_message", "send_gmail_message", "start_google_auth"},
    "github": None,
}
```

* 🎯 Which tools each agent is allowed to keep.
* 💡 Servers offer **many** tools (the Gmail server also has label and filter management…). **Fewer tools = better choices** by the LLM, and it can't do things we never wanted. GitHub is limited a different way (headers, see A4), so `None` = "keep all".

## A2. Finding `uvx`

```python
def _uvx_command() -> str:
    found = shutil.which("uvx")
    if found:
        return found
    exe = "uvx.exe" if sys.platform == "win32" else "uvx"
    return str(Path(sys.executable).parent / exe)
```

* 🎯 Finds the `uvx` program. It's installed by `pip install uv` (in `requirements.txt`).
* 💡 `uvx workspace-mcp` = "download the `workspace-mcp` Python package into a private cache and run it", like `npx` for Node. We never `pip install` the server into **our** environment, so its libraries can't clash with ours.
* 💡 `shutil.which` searches your PATH (works when `.venv` is activated). If it fails, we look next to the Python running this app (`.venv\Scripts\uvx.exe`).
* 🔤 `Path(...) / "uvx.exe"` joins paths with `/`, which works on Windows too.

## A3. `_google_server`: one Google server per service

```python
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
        "OAUTHLIB_INSECURE_TRANSPORT": "1",
        "PYTHONIOENCODING": "utf-8",
    },
}
```

* 🎯 The command line + environment to start `workspace-mcp` for **one** service.
* 💡 We call this **twice** (`"calendar"`, port 8001 and `"gmail"`, port 8002), so each agent has its **own server process with only its own tools**. That's what makes them 3 *separate* MCP sub-agents.

| Setting | Why |
|---|---|
| `--tools calendar` | Load only Calendar tools in this process. |
| `--tool-tier complete` | Load all tiers (so `start_google_auth` and `draft_gmail_message` exist); our allow-list then filters them. |
| `--single-user` | "One person uses this server", so use the saved login token directly. |
| `GOOGLE_OAUTH_CLIENT_ID/SECRET` | Identify **our app** to Google (from [setup step 5](01_setup.md)). |
| `WORKSPACE_MCP_CREDENTIALS_DIR` | Where the login token is saved. A **separate folder per service**, so the two servers never overwrite each other's token. |
| `WORKSPACE_MCP_PORT` | Port of the tiny login web server Google redirects to. Different ports, so both servers can run at once. |
| `OAUTHLIB_INSECURE_TRANSPORT=1` | Allows the `http://localhost` redirect (no https locally). Fine on your own computer only. |

## A4. `server_settings`: which servers can start?

```python
if has_key("GITHUB_TOKEN"):
    servers["github"] = {
        "transport": "streamable_http",
        "url": "https://api.githubcopilot.com/mcp/",
        "headers": {
            "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
            "X-MCP-Toolsets": "context,repos,issues,pull_requests,users",
            "X-MCP-Readonly": "true",
        },
    }
else:
    servers["github"] = "GITHUB_TOKEN missing in .env"
```

* 🎯 Builds the settings for each server, **or** a string explaining what's missing.
* 💡 Header by header:
  * `Authorization: Bearer <token>` is the standard HTTP way to prove who you are.
  * `X-MCP-Toolsets` loads only these **groups** of GitHub tools (not Actions, security alerts, etc.).
  * `X-MCP-Readonly: true` means GitHub's server **removes every write tool**. Even if the LLM wanted to, it can't create issues or push code. Safety by design, not by prompt.
* 💡 Returning a **string** for "off" agents lets the banner show *why* (`❌ off  GITHUB_TOKEN missing in .env`).

## A5. `open_server`: the 4 steps to use ANY MCP server ⭐

```python
# Step 1: TRANSPORT
if settings["transport"] == "stdio":
    log_file = stack.enter_context(open(LOG_DIR / f"{name}.log", "a", encoding="utf-8"))
    params = StdioServerParameters(command=..., args=..., env=...)
    read, write = await stack.enter_async_context(stdio_client(params, errlog=log_file))
else:
    http_client = create_mcp_http_client(headers=settings["headers"])
    read, write, _ = await stack.enter_async_context(
        streamable_http_client(settings["url"], http_client=http_client))

# Step 2: SESSION
session = await stack.enter_async_context(ClientSession(read, write))
# Step 3: INITIALIZE
await asyncio.wait_for(session.initialize(), timeout=120)
# Step 4: LIST TOOLS -> LangChain tools
tools = await load_mcp_tools(session)
```

| Step | 🎯 What | 💡 Why |
|---|---|---|
| 1 TRANSPORT | Opens a **pipe**: starts the process (stdio) or opens an HTTP connection. Gives a `read` stream and a `write` stream. | MCP messages are JSON; they need a way to travel. |
| `errlog=log_file` | The server's own log output goes to `logs/<name>.log`. | Otherwise its log lines would mess up our nice terminal. Check that file when something fails! |
| 2 SESSION | `ClientSession` speaks the MCP protocol (JSON-RPC) over the pipe. | It matches requests to answers, handles ids, etc. |
| 3 INITIALIZE | The **handshake**: "Hi, I'm a client, protocol version X, what can you do?" | Required by MCP before anything else. `wait_for(..., 120)` = don't wait forever (bad token, no internet). |
| 4 LIST TOOLS | `load_mcp_tools` asks the server for `tools/list` and wraps each one as a LangChain `BaseTool`. | After this, MCP tools look **exactly like** our own `@tool` functions: same `bind_tools`, same `ToolNode`. |

* 🔤 **Why `stack.enter_async_context(...)` and not `async with`?** `async with` would close the connection at the end of the function. The stack keeps it **open** until `main.py`'s `async with AsyncExitStack()` block ends (when you quit). See [doc 02 §11](02_python_syntax.md).
* 💡 **Why keep it open?** Starting a new process for each tool call is slow (seconds), and the Google login web server lives **inside** that process. It must stay alive while you log in.

## A6. `connect_all`: one failure doesn't stop the others

```python
for name, settings in server_settings().items():
    if isinstance(settings, str):
        results[name] = settings
        continue
    server_stack = AsyncExitStack()
    try:
        results[name] = await open_server(server_stack, name, settings)
        stack.push_async_callback(server_stack.aclose)
    except Exception as e:
        await server_stack.aclose()
        results[name] = f"could not connect: {type(e).__name__} (see logs/{name}.log)"
```

* 🎯 Opens each server inside its own small stack.
* 💡 If GitHub fails (expired token), we close **only** GitHub's half-open connection and keep Calendar/Gmail running. On success, `push_async_callback` hands the "close later" job to the main stack.
* 🔤 `continue` skips to the next loop round.

---

# Part B · The three agent files

## B1. `github_agent.py`

```python
SYSTEM_PROMPT = (
    "You are the GitHub Agent. ... "
    "If the user says 'my repos' or 'my account', first call get_me to learn their username. "
    "... never dump raw JSON."
)

def build_github_agent(mcp_tools):
    return build_tool_agent("github", mcp_tools, SYSTEM_PROMPT)
```

* 💡 The whole agent is a **prompt + MCP tools**. `get_me` is a tool of GitHub's server that returns *your* username, so "list my repos" works without you typing your name.
* 💡 No sensitive tools: the server is read-only anyway.

## B2. `calendar_agent.py`

```python
SENSITIVE_TOOLS = {"manage_event"}

def system_prompt() -> str:
    email = os.getenv("USER_GOOGLE_EMAIL", "")
    return (
        "You are the Calendar Agent. ... "
        f"The user's Google email is {email}; pass it as user_google_email to every tool. "
        "Use RFC3339 times with the user's UTC offset, e.g. 2026-10-03T15:00:00+05:00. "
        "Meetings are 30 minutes long unless the user says otherwise. "
        "To create a meeting call manage_event with action='create'; put guest emails in "
        "attendees and set send_updates='all' so guests receive the invitation email. "
        "Set add_google_meet=true when the user asks for an online / Meet / video meeting. "
        "Before creating, check for clashes with get_events or query_freebusy. ..."
    )
```

* 🎯 `manage_event` can **create, update and delete** events, so it always needs your approval.
* 💡 Each prompt rule fixes a real problem:
  * **email**: every workspace-mcp tool has a `user_google_email` argument.
  * **RFC3339 + offset**: the Calendar API needs exact times. Without an offset, "3pm" could be read as 3pm UTC (8pm in Pakistan!).
  * **default 30 minutes**: users rarely say an end time.
  * **`send_updates='all'`**: otherwise guests are added silently with no invite email.
  * **`add_google_meet`**: creates the video link.
  * **check clashes**: a good assistant warns you before double-booking.
* 🔤 `system_prompt()` is a **function**, not a constant, so it reads `.env` at the moment the agent is built.

## B3. `gmail_agent.py`

```python
SENSITIVE_TOOLS = {"send_gmail_message", "schedule_email"}

def build_gmail_agent(mcp_tools):
    tools = list(mcp_tools)
    send_tool = next((t for t in mcp_tools if t.name == "send_gmail_message"), None)
    if send_tool is not None:
        tools.append(make_schedule_email_tool(send_tool))
    return build_tool_agent("gmail", tools, system_prompt(), SENSITIVE_TOOLS)
```

* 🎯 MCP tools **plus one of our own** (`schedule_email`). An agent can freely mix MCP tools and normal `@tool` functions.
* 💡 **Draft vs send:**
  * `draft_gmail_message` only saves a draft. You still click Send in Gmail, so it's safe and needs no approval.
  * `send_gmail_message` and `schedule_email` actually send, so they need approval.
* 💡 The prompt maps words to tools: "draft/write/prepare" → draft, "send" → send, "send at <time>" → schedule. It also says *"never guess an address"*, so the LLM asks you instead of inventing `ali@gmail.com`.
* 🔤 `list(mcp_tools)` makes a **copy**, so we don't modify the list we were given.

---

# Part C · `scheduler.py`: "send it tomorrow at 9am"

The Gmail API has **no** schedule-send feature for apps, so we build one with **APScheduler** (an "alarm clock" for Python functions).

```python
scheduler = AsyncIOScheduler()

def make_schedule_email_tool(send_tool):
    async def send_now(to, subject, body):
        await send_tool.ainvoke({"user_google_email": ..., "to": to, "subject": subject, "body": body})
        ui.success(f"📧 Scheduled email sent to {to}: {subject}")

    @tool
    def schedule_email(to: str, subject: str, body: str, send_at: str) -> str:
        """Schedule an email to be sent automatically at a future time. ..."""
        when = datetime.fromisoformat(send_at)
        ...
        scheduler.add_job(send_now, trigger="date", run_date=when, args=[to, subject, body], name=...)
        return f"Scheduled: the email to {to} will be sent at {when:%A %d %B %Y %H:%M}."

    return schedule_email
```

| Piece | 🎯 What | 💡 Why |
|---|---|---|
| `AsyncIOScheduler` | Runs jobs **inside our asyncio event loop**. | The job uses the Gmail **MCP** tool, whose connection lives in that same loop. |
| factory `make_schedule_email_tool(send_tool)` | Builds the tool **after** we have the MCP send tool. | The inner functions **remember** `send_tool` (a closure). |
| `send_now` | The job that runs at the chosen time. | It reuses the **same** MCP `send_gmail_message` tool: no new Gmail code. |
| `datetime.fromisoformat(send_at)` | Text → datetime. | The LLM writes ISO times like `2026-10-03T09:00:00+05:00`. |
| `if when <= now: return "Error..."` | Refuse past times. | The error **string** goes back to the LLM, which asks you for a new time. |
| `add_job(..., trigger="date", run_date=when)` | "Run once at this date". | Other triggers exist: `"interval"` (every N minutes), `"cron"`. |

* ⚠️ **Limitation:** jobs live in **memory**. If you close the app before the time, the email is not sent. `/jobs` shows what's waiting. (Exercise 6 in [doc 10](10_exercises.md) makes jobs survive restarts.)
* 💡 `main.py` reads your input with `await asyncio.to_thread(ui.user_prompt)`, so the event loop stays **free** while you're typing, and the job fires on time.

---

### 🔐 First-time Google login, what really happens

1. You ask "What's on my calendar today?" and the agent calls `get_events`.
2. The server has no token, so it starts a tiny web server on `localhost:8001`, **opens your browser** at Google's login page, and returns *"ACTION REQUIRED: Google Authentication Needed…"* with the link.
3. You log in. Google redirects to `http://localhost:8001/oauth2callback?code=...`. The server swaps the code for a **token** and saves it in `.google_tokens/calendar/`.
4. You ask again, and now it works. Next time the saved token is used automatically (and refreshed when needed).
