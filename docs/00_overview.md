# 00 · The big picture

> Read this first. No code yet, just *what* the pieces are and *how* a message travels through them.

## 1. What we are building

A chatbot in the terminal that can **do things for you**: read your PDFs, look at GitHub, manage your Google Calendar and write or send emails.

One LLM cannot do all of this well alone. So we build a **team**:

```
                        👤 You
                          │  "Book a meeting with Ali at 3pm and email him the agenda"
                          ▼
                 ┌──────────────────┐
                 │  🧭 Supervisor   │  "This needs Calendar, then Gmail."
                 └──────────────────┘
        ┌─────────┬──────────┼───────────┬──────────┐
        ▼         ▼          ▼           ▼          ▼
   📚 RAG     🐙 GitHub  📅 Calendar  📧 Gmail   💬 Chat
   Pinecone   MCP server  MCP server  MCP server  (no tools)
```

* The **Supervisor** is a *router*. It never does the work itself. It only decides **who** should do it.
* Each **sub-agent** is a specialist with its **own tools** and its **own instructions** (system prompt).
* Specialists are better than one "do-everything" agent. Each one sees only 3–15 tools instead of 40, so it picks the right one more often, and its prompt can contain detailed rules ("always ask before sending").

## 2. The life of one message

Let's follow **"What meetings do I have tomorrow?"** step by step.

| Step | File | What happens |
|---|---|---|
| 1 | `main.py` | `ui.user_prompt()` reads your text. It is wrapped in a `HumanMessage` and given to the graph with `graph.ainvoke(...)`. |
| 2 | `supervisor.py` | The **checkpointer** (memory) loads the earlier messages of this conversation and adds your new one. |
| 3 | `supervisor.py` → `supervisor_node` | One LLM call with **structured output** returns `RoutePlan(steps=["calendar"], reason="reading meetings")`. The terminal shows `🧭 Supervisor → 📅 Calendar Agent`. |
| 4 | `supervisor.py` → `next_step` | Looks at `plan[0]` → `"calendar"`, so the graph moves to the calendar node. |
| 5 | `agent_builder.py` → `agent_node` | The Calendar LLM sees the conversation + its tools and replies with a **tool call**: `get_events(time_min=..., time_max=...)`. |
| 6 | `agent_builder.py` → `approval_node` | `get_events` only reads, so it is not "sensitive" and passes straight through. |
| 7 | `agent_builder.py` → `tools_node` | `ToolNode` runs the tool. The tool is an **MCP tool**, so the request goes to the `workspace-mcp` process, which calls the Google Calendar API. The result comes back as a `ToolMessage`. |
| 8 | `agent_node` again | The LLM reads the events and writes a friendly answer (no more tool calls) → the sub-agent ends. |
| 9 | `supervisor.py` → agent node wrapper | Shows the answer in a green panel and saves **only the final answer** into memory. `plan` is now empty → `END`. |
| 10 | `main.py` | Waits for your next message. |

## 3. The two kinds of "graph" in this project

**Supervisor graph** (`supervisor.py`), one per app, *with memory*:

```
START → supervisor → [rag | github | calendar | gmail | chat] → (next in plan, or END)
```

**Sub-agent graph** (`agent_builder.py`), one per specialist, *no memory of its own*:

```
START → agent ⇄ approval → tools → agent → ... → END
```

A compiled graph can be used **inside** another graph's node. That is called a **subgraph**. Our supervisor's `calendar` node simply runs the whole calendar sub-agent graph.

## 4. Glossary

| Word | Meaning in one line |
|---|---|
| **LLM** | Large Language Model, the "brain" (here Google Gemini). Text in, text (or tool calls) out. |
| **Agent** | An LLM in a loop that can **decide** to call tools, read the results and decide again. |
| **Tool** | A Python function the LLM can ask us to run. The LLM sees its name, description and arguments. |
| **Tool call** | The LLM's reply saying "please run `get_events` with these arguments" instead of plain text. |
| **ReAct** | *Reason + Act*: think → call a tool → read the result → think again → … → answer. |
| **System prompt** | Hidden instructions at the start of every LLM call: the agent's job description. |
| **State** | The data that flows through a LangGraph graph. Here mainly `messages` (+ `plan`). |
| **Node** | One step in a graph, a Python function that receives the state and returns an update. |
| **Edge** | An arrow between nodes. A **conditional edge** picks the next node with a function. |
| **Reducer** | A rule for merging updates into state. `add_messages` *appends* instead of replacing. |
| **Checkpointer** | Saves the state after every step, which gives us memory. `MemorySaver` keeps it in RAM. |
| **thread_id** | The id of one conversation. Same id = same memory. `/new` makes a new id. |
| **Structured output** | Forcing the LLM to reply in a fixed shape (a Pydantic class) instead of free text. |
| **RAG** | *Retrieval-Augmented Generation*: search your documents first, then let the LLM answer from what was found. |
| **Embedding** | A list of numbers that represents the *meaning* of a text. Similar meaning → similar numbers. |
| **Vector database** | A database that stores embeddings and finds the most similar ones fast. |
| **Pinecone** | A *hosted* (cloud) vector database. Our PDFs' embeddings live there. |
| **Chunk** | A small piece of a document (~1000 characters). We embed and search chunks, not whole files. |
| **MCP** | *Model Context Protocol*: a standard plug between AI apps (clients) and services (servers). |
| **MCP server** | A program that offers tools over MCP, e.g. GitHub's server offers `list_issues`, `get_file_contents`… |
| **MCP client** | Our app. It connects, asks for the tool list, and calls the tools. |
| **stdio / HTTP transport** | The two ways to reach an MCP server: start it as a local process, or call it over the internet. |
| **OAuth** | The "Sign in with Google" flow. Gives our app permission to your Calendar/Gmail without your password. |
| **Human-in-the-loop (HITL)** | Pausing to ask a human before a risky action (sending email, creating meetings). |
| **async / await** | Python's way to wait for slow things (network, LLM) efficiently. MCP tools require it. |

## 5. Reading order for the code

1. `utils.py`, `ui.py`: small helpers ([doc 03](03_utils_and_ui.md))
2. `rag_core.py` → `ingest.py` → `rag_agent.py` ([doc 04](04_rag_agent.md))
3. `agent_builder.py`: the heart of every sub-agent ([doc 05](05_agent_builder.md))
4. `mcp_servers.py` → `github_agent.py`, `calendar_agent.py`, `gmail_agent.py`, `scheduler.py` ([doc 06](06_mcp_agents.md))
5. `supervisor.py` → `main.py`: everything tied together ([doc 07](07_supervisor_and_main.md))

If some Python syntax looks strange (`async def`, `@tool`, `Literal[...]`, `dict[str, list]`…), keep [doc 02](02_python_syntax.md) open next to the code.
