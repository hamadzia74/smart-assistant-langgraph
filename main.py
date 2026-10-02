"""
main.py - start here! Chat with the Smart Assistant in your terminal.

Run:
    python main.py

What happens when it starts:
    1. Connect to the 3 MCP servers (GitHub, Calendar, Gmail)        -> mcp_servers.py
    2. Build the 4 sub-agents (RAG + the 3 MCP agents)                -> *_agent.py
    3. Build the supervisor graph that routes between them            -> supervisor.py
    4. Show a banner with ✅ / ❌ for every agent
    5. Loop: read your message -> run the graph -> answers are printed by the nodes

Commands inside the chat:
    /help              examples
    /upload <file.pdf> add a PDF to Pinecone (the RAG agent can then search it)
    /jobs              scheduled emails waiting to be sent
    /graph             print the supervisor graph as a Mermaid diagram
    /new               new conversation (fresh memory)
    /exit              quit
"""

import asyncio
import uuid
from contextlib import AsyncExitStack

from langchain_core.messages import HumanMessage

import scheduler
import ui
from calendar_agent import build_calendar_agent
from github_agent import build_github_agent
from gmail_agent import build_gmail_agent
from mcp_servers import connect_all
from rag_agent import build_rag_agent
from supervisor import build_supervisor_graph
from utils import chat_model_name, has_key


def setup_rag() -> tuple[object, tuple[bool, str]]:
    """Returns (rag_agent or reason_string, banner_status)."""
    if not (has_key("PINECONE_API_KEY") and has_key("GOOGLE_API_KEY")):
        reason = "PINECONE_API_KEY and GOOGLE_API_KEY needed"
        return reason, (False, reason)
    try:
        from rag_core import INDEX_NAME, count_chunks

        chunks = count_chunks()   # also creates the index on the very first run
        detail = f"Pinecone index '{INDEX_NAME}': {chunks} chunks"
        if chunks == 0:
            detail += " - use /upload <file.pdf>"
        return build_rag_agent(), (True, detail)
    except Exception as e:
        reason = f"Pinecone error: {e}"
        return reason, (False, reason[:80])


async def handle_command(command: str, graph, state: dict) -> bool:
    """
    Handles /commands. Returns False when the app should exit.
    `state` is a dict so we can change thread_id inside this function
    (dicts are passed by reference, so the caller sees the change).
    """
    name, _, argument = command.partition(" ")   # "/upload a b.pdf" -> "/upload", " ", "a b.pdf"

    if name in ("/exit", "/quit"):
        return False
    elif name == "/help":
        ui.help_panel()
    elif name == "/new":
        state["thread_id"] = f"chat-{uuid.uuid4().hex[:8]}"
        ui.success(f"New conversation {state['thread_id']} - memory is empty.")
    elif name == "/jobs":
        jobs = scheduler.list_jobs()
        if not jobs:
            ui.info("No scheduled emails.")
        for when, what in jobs:
            ui.console.print(f"   ⏰ {when}  {what}")
    elif name == "/graph":
        ui.console.print(graph.get_graph().draw_mermaid())
        ui.info("Paste this into https://mermaid.live to see the picture.")
    elif name == "/upload":
        path = argument.strip().strip('"').strip("'")   # allow "C:\My Files\a.pdf"
        if not path:
            ui.warn("Usage: /upload C:\\path\\to\\file.pdf")
            return True
        from rag_core import ingest_pdf

        try:
            with ui.console.status(f"[dim]📤 Reading, embedding and uploading {path}...[/dim]"):
                # ingest_pdf is normal (blocking) code. to_thread runs it in a helper
                # thread so the event loop (and scheduled emails) keep working.
                count = await asyncio.to_thread(ingest_pdf, path)
            ui.success(f"Uploaded {count} chunks to Pinecone. Ask me about it!")
        except Exception as e:
            ui.error(f"Upload failed: {e}")
    else:
        ui.warn(f"Unknown command {name}. Type /help")
    return True


async def main() -> None:
    if not (has_key("GOOGLE_API_KEY") or has_key("GROQ_API_KEY")):
        ui.error("No LLM key. Copy .env.example to .env and add GOOGLE_API_KEY. See docs/01_setup.md")
        return

    # AsyncExitStack keeps the MCP connections open until the `async with` block ends.
    async with AsyncExitStack() as stack:
        # ---------- 1. connect MCP servers ----------
        with ui.console.status("[dim]🔌 Connecting to MCP servers (first run downloads them, ~1 min)...[/dim]"):
            mcp_tools = await connect_all(stack)

        # ---------- 2. build the sub-agents ----------
        agents: dict[str, object] = {}
        statuses: dict[str, tuple[bool, str]] = {}

        agents["rag"], statuses["rag"] = setup_rag()

        builders = {"github": build_github_agent, "calendar": build_calendar_agent, "gmail": build_gmail_agent}
        for key, build in builders.items():
            tools = mcp_tools[key]
            if isinstance(tools, str):              # a string = the reason it is off
                agents[key] = tools
                statuses[key] = (False, tools)
            else:
                agents[key] = build(tools)
                statuses[key] = (True, f"{len(tools)} MCP tools")

        # ---------- 3. supervisor graph + scheduler ----------
        graph = build_supervisor_graph(agents)
        scheduler.start()

        ui.banner(chat_model_name(), statuses)

        # ---------- 4. chat loop ----------
        state = {"thread_id": f"chat-{uuid.uuid4().hex[:8]}"}
        while True:
            try:
                # input() blocks. Running it in a thread lets scheduled emails
                # fire on time even while the app waits for you to type.
                text = await asyncio.to_thread(ui.user_prompt)
            except (EOFError, KeyboardInterrupt):
                break

            text = text.lstrip("\ufeff")   # PowerShell may add an invisible BOM character
            if not text:
                continue
            if text.startswith("/"):
                if not await handle_command(text, graph, state):
                    break
                continue

            config = {"configurable": {"thread_id": state["thread_id"]}}
            try:
                # We send ONLY the new message. The checkpointer adds the saved history.
                # plan=[] resets the plan for this new turn.
                await graph.ainvoke({"messages": [HumanMessage(content=text)], "plan": []}, config)
            except Exception as e:
                ui.error(f"{type(e).__name__}: {e}")
                ui.info("A 429 / quota error means the free tier limit was hit - wait a minute.")
            ui.console.print()

    if scheduler.list_jobs():
        ui.warn("Scheduled emails that had not been sent yet were cancelled (app closed).")
    ui.console.print("👋 Bye!")


# This block runs only when you start the file directly (python main.py),
# not when another file imports it.
if __name__ == "__main__":
    try:
        # asyncio.run starts the event loop and runs main() until it finishes.
        asyncio.run(main())
    except KeyboardInterrupt:
        ui.console.print("\n👋 Bye!")
