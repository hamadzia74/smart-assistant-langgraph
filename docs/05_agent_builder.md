# 05 · 🔁 `agent_builder.py`: one function that builds every sub-agent

All four sub-agents work the same way: *think → (ask permission) → use tool → think again → answer*. Only their **tools** and **instructions** differ. So we write the graph **once** and call `build_tool_agent(...)` four times.

This is lecture 04's **ReAct loop** plus lecture 06's **human-in-the-loop**:

```
        START
          │
          ▼
      ┌───────┐ tool calls? ┌──────────┐ approved ┌───────┐
      │ agent │ ──────────▶ │ approval │ ───────▶ │ tools │
      └───────┘             └──────────┘          └───────┘
        ▲  │                     │ rejected           │
        │  │ no tool calls       ▼                    │
        │  ▼                (back to agent)           │
        │ END                                         │
        └─────────────────────────────────────────────┘
```

---

## 1. The function signature

```python
def build_tool_agent(
    agent_key: str,
    tools: list[BaseTool],
    system_prompt: str,
    sensitive_tools: set[str] = frozenset(),
):
```

* 🎯 The 4 things that make each agent different.
* 💡 `sensitive_tools` lists tool **names** that need a human "yes", e.g. `{"send_gmail_message", "schedule_email"}`. By default it's empty: nothing needs approval.
* 🔤 `set[str]` is a collection of unique strings with very fast `in` checks. `frozenset()` is an empty set that can't be changed. Using it as a default avoids Python's "mutable default argument" trap.

## 2. Model + tools

```python
llm_with_tools = get_chat_model().bind_tools(tools)
tool_node = ToolNode(tools, handle_tool_errors=True)
```

* 🎯 `bind_tools` attaches the tool descriptions to **every** request to the LLM. Now the LLM can answer with a *tool call* (`{"name": "get_events", "args": {...}}`) instead of text.
* 🎯 `ToolNode` is LangGraph's prebuilt "tool runner". It reads the tool calls from the last AI message, runs the matching tools (in parallel when there are several) and returns one `ToolMessage` per call.
* 💡 `handle_tool_errors=True`: if a tool fails (wrong date format, API error), the **error text goes back to the LLM** as a ToolMessage. The LLM can then fix its arguments and retry, or explain the problem. Without it, one bad tool call would crash the whole app.

## 3. Node 1: `agent_node` (the LLM decides)

```python
async def agent_node(state: MessagesState) -> dict:
    now = datetime.now().astimezone()
    system = SystemMessage(
        content=f"{system_prompt}\n\nCurrent date and time: {now:%A, %d %B %Y, %H:%M} "
                f"(UTC offset {now:%z})."
    )
    with ui.console.status(f"[dim]⏳ {ui.AGENTS[agent_key][1]} is thinking...[/dim]"):
        response = await llm_with_tools.ainvoke([system] + state["messages"])

    for call in response.tool_calls:
        ui.show_tool_call(agent_key, call["name"], call["args"])

    return {"messages": [response]}
```

Line by line:

| Code | 🎯 What | 💡 Why |
|---|---|---|
| `async def` | an async node | MCP tools are async-only, so the whole graph runs with `ainvoke`. LangGraph happily runs async nodes. |
| `datetime.now().astimezone()` | the current local time, **with** time zone | The LLM has **no clock**. Without this, "tomorrow at 3pm" is impossible to convert into a real date. The UTC offset (`+0500` for Pakistan) lets it build correct times like `2026-10-03T15:00:00+05:00`. |
| `SystemMessage(...)` | the agent's instructions | Added **fresh on every call** and **not stored** in the state, so memory doesn't fill up with copies of the prompt, and the time is always current. |
| `ui.console.status(...)` | a spinner | The LLM can take a few seconds; a spinner shows the app hasn't frozen. |
| `[system] + state["messages"]` | prompt + conversation | `+` joins two lists. |
| `await ... ainvoke(...)` | call Gemini | `await` waits for the network answer without blocking the event loop. |
| `response.tool_calls` | the tools the LLM wants | A list of dicts: `name`, `args`, `id`. Empty if the LLM answered with text. |
| `return {"messages": [response]}` | a **state update** | `MessagesState` uses the `add_messages` **reducer**, so this **appends** the response; it doesn't replace the history. |

## 4. Node 2: `approval_node` (human-in-the-loop)

```python
def approval_node(state: MessagesState) -> dict:
    last_message = state["messages"][-1]
    risky_calls = [c for c in last_message.tool_calls if c["name"] in sensitive_tools]

    if not risky_calls:
        return {}

    approved = all(ui.ask_approval(agent_key, c["name"], c["args"]) for c in risky_calls)
    if approved:
        return {}

    ui.warn("Cancelled - nothing was sent or changed.")
    cancelled = [
        ToolMessage(content="The user REJECTED this action. ...", tool_call_id=call["id"])
        for call in last_message.tool_calls
    ]
    return {"messages": cancelled}
```

* 🎯 Before any risky tool runs, it shows you the exact arguments and asks **✅ Approve? [y/n]**.
* 💡 Step by step:
  * `state["messages"][-1]` is the AI message that contains the tool calls (`[-1]` = last item).
  * Only calls whose name is in `sensitive_tools` need approval. Reading meetings or searching mail just passes through: `return {}` = "no change to the state".
  * If you say **no**, we must still **answer every tool call**. LLM APIs require every tool call `id` to be followed by a `ToolMessage` with the same `tool_call_id`, otherwise the next request fails. So we answer each call with "the user rejected this". The LLM then tells you it was cancelled.
* 💡 **How is this different from lecture 06?** Lecture 06 used `interrupt_before=[...]` and resumed the graph with `app.invoke(None, ...)`. That's the production approach for web apps, where the "human" answers later from another request. Ours is a **terminal** app where the human is right there, so the node simply asks with `input()`. Simpler code, same safety. (Exercise 5 in [doc 10](10_exercises.md) switches it to `interrupt()`.)
* 🔤 `all(generator)` stops at the **first** "no", so you're not asked about the rest.

## 5. Node 3: `tools_node`

```python
async def tools_node(state: MessagesState) -> dict:
    with ui.console.status("[dim]⏳ running tool...[/dim]"):
        result = await tool_node.ainvoke(state)
    for msg in result["messages"]:
        ui.show_tool_result(message_text(msg))
    return result
```

* 🎯 Runs the prebuilt `ToolNode`, then prints a short preview of each result (`📥 ...`).
* 💡 We wrap `ToolNode` in our own function **only** to add the spinner and the preview. The real work is done by `ToolNode`.

## 6. The router after approval

```python
def after_approval(state: MessagesState) -> str:
    if isinstance(state["messages"][-1], ToolMessage):
        return "agent"
    return "tools"
```

* 🎯 Picks the next node.
* 💡 If approval added "rejected" ToolMessages, the last message is now a `ToolMessage`, so go back to the **agent** (to explain). Otherwise the last message is still the AI's tool request, so go to **tools**.

## 7. Wiring the graph

```python
builder = StateGraph(MessagesState)
builder.add_node("agent", agent_node)
builder.add_node("approval", approval_node)
builder.add_node("tools", tools_node)

builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition, {"tools": "approval", END: END})
builder.add_conditional_edges("approval", after_approval, {"tools": "tools", "agent": "agent"})
builder.add_edge("tools", "agent")

return builder.compile(name=f"{agent_key}_agent")
```

| Line | Meaning |
|---|---|
| `StateGraph(MessagesState)` | A graph whose state is `{"messages": [...]}`. |
| `add_node("agent", agent_node)` | Register a node: a **name** + the **function** to run. |
| `add_edge(START, "agent")` | Always begin at `agent`. |
| `add_conditional_edges("agent", tools_condition, {...})` | After `agent`, call `tools_condition(state)`. It returns `"tools"` if the last message has tool calls, otherwise `END`. The dict **maps** those return values to our node names. We send `"tools"` to **approval** first. |
| `add_conditional_edges("approval", after_approval, {...})` | After approval: our own function decides between `tools` and `agent`. |
| `add_edge("tools", "agent")` | After tools, **always** back to the agent, which reads the results. That's the **loop**. |
| `compile(name=...)` | Checks the graph and turns it into a runnable object (`ainvoke`, `astream`, …). |

* 💡 **No checkpointer here.** Memory lives in the **supervisor** graph ([doc 07](07_supervisor_and_main.md)). The supervisor gives each sub-agent the full conversation, so the sub-agent doesn't need its own memory.

---

### 🧪 Mental test: "Send Ali an email saying I'm late"

1. **agent** → tool call `send_gmail_message(to=..., subject=..., body=...)` → `tools_condition` says "tools".
2. **approval** → `send_gmail_message` is sensitive → red box → you press **y** → `return {}`.
3. `after_approval` → last message is still the AIMessage → "tools".
4. **tools** → the MCP server sends the email → `📥 Email sent! Message ID: ...`
5. **agent** → reads the result → replies with text "✅ Sent to Ali" → no tool calls → **END**.
