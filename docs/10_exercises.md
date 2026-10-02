# 10 · ✏️ Exercises: practise by changing the code

Start easy; each exercise names the file(s) to touch. Hints are in the collapsible sections.

---

### 1 · Change an agent's look ⭐
Make the GitHub agent white with a 🐱 icon.

<details><summary>Hint</summary>

`ui.py` → `AGENTS["github"]`. Nothing else needs to change. That's why UI lives in one file.
</details>

### 2 · Retrieve more chunks ⭐
Make the RAG agent read 6 chunks instead of 4. Ask the same question before and after, and compare the `📥` preview and the answer.

<details><summary>Hint</summary>

`rag_agent.py` → `search_kwargs={"k": 4}`.
</details>

### 3 · Add a tool to the RAG agent ⭐⭐
Write a tool `list_uploaded_pdfs()` that returns the file names in the index.

<details><summary>Hint</summary>

In `rag_core.py`: `get_pinecone_index().list()` yields **pages of ids** like `"handbook.pdf#p1#c0"`. Take the part before the first `#`, put the names in a `set`. In `rag_agent.py`, add a `@tool` with a clear docstring and add it to the list passed to `build_tool_agent`.
</details>

### 4 · A 5th agent: weather 🌦️ ⭐⭐
Add a `weather` agent with one `@tool get_weather(city)` (call `https://wttr.in/{city}?format=3` with `urllib.request`).

<details><summary>Hint</summary>

Steps:
1. New file `weather_agent.py` (copy `rag_agent.py`'s shape).
2. `ui.py`: add `"weather"` to `AGENTS`.
3. `supervisor.py`: add it to `AgentName`, the prompt's agent list, the node loop and `destinations`.
4. `main.py`: build it and add a banner status.
</details>

### 5 · Approval with `interrupt()` (like lecture 06) ⭐⭐⭐
Replace `ui.ask_approval(...)` inside `approval_node` with LangGraph's `interrupt(...)`, and resume from `main.py`.

<details><summary>Hint</summary>

* `from langgraph.types import interrupt, Command`
* In the node: `answer = interrupt({"tool": c["name"], "args": c["args"]})`.
* Subgraphs need a checkpointer to pause: compile the sub-agents with `checkpointer=True` (they then use the parent's).
* In `main.py`, after `ainvoke`, check `result.get("__interrupt__")`. Ask the user, then `await graph.ainvoke(Command(resume=True_or_False), config)`.
* Why bother? This is how approval works in **web apps**, where the "yes" arrives in a later HTTP request.
</details>

### 6 · Scheduled emails that survive restarts ⭐⭐⭐
<details><summary>Hint</summary>

Save each job (to, subject, body, send_at) to a JSON file in `schedule_email`. On start-up, read the file and `add_job` again for times still in the future. (APScheduler's `SQLAlchemyJobStore` is another option, but our job uses a live MCP tool, which can't be saved. So store the *data*, not the function.)
</details>

### 7 · Memory that survives restarts ⭐⭐
<details><summary>Hint</summary>

`pip install langgraph-checkpoint-sqlite`, then use `AsyncSqliteSaver` instead of `MemorySaver` in `supervisor.py`, and keep a fixed `thread_id` in `main.py`.
</details>

### 8 · Let GitHub write (carefully!) ⭐⭐⭐
Allow creating issues, but only with approval.

<details><summary>Hint</summary>

* `mcp_servers.py`: remove `X-MCP-Readonly`.
* `github_agent.py`: pass `sensitive_tools={"create_issue", "add_issue_comment", ...}` to `build_tool_agent`.
* Your token needs **Issues: Read and write**.
* Think: which other write tools now appear? Should they be in the allow-list at all?
</details>

### 9 · Watch the trace in LangSmith ⭐⭐
<details><summary>Hint</summary>

Like your study-buddy project: add `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY=...` to `.env`. Every supervisor decision, sub-agent loop and tool call appears as a tree at smith.langchain.com. No code change needed.
</details>
