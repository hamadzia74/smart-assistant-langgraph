# 07 · 🧭 `supervisor.py` + ▶ `main.py`: tying everything together

---

# Part A · `supervisor.py`

```
                         ┌────────────┐
    START ─────────────▶ │ supervisor │  one LLM call → plan = ["calendar", "gmail"]
                         └────────────┘
                               │ next_step()  → plan[0]
       ┌──────────┬────────────┼────────────┬──────────┐
       ▼          ▼            ▼            ▼          ▼
     rag       github      calendar       gmail       chat
       └──────────┴──── next_step() ──────┴──────────┘
                 next planned agent, or END
```

## A1. The prompt: the router's job description

```python
SUPERVISOR_PROMPT = """You are the supervisor of a team of assistant agents.
Read the conversation and plan which agent(s) must handle the user's LATEST message.

Agents:
- rag: questions about the user's uploaded PDF documents ...
- github: anything about GitHub ...
...
Rules:
- Usually choose exactly ONE agent.
- Choose two (in order) only if the request clearly needs two ...
- Use earlier messages for context: "send it" after a draft email -> gmail."""
```

* 💡 The router is only as good as these **descriptions**. If it picks the wrong agent, improve the description first: that's "prompt engineering".
* 💡 "Use earlier messages for context" is why a follow-up like *"send it now"* goes to Gmail even though it doesn't mention email.
* 🔤 `"""..."""` is a multi-line string.

## A2. The state

```python
class AssistantState(MessagesState):
    plan: list[str]
```

* 🎯 The supervisor graph's state = `messages` (inherited) + `plan`.
* 💡 `plan` holds the agents **still waiting** in this turn. Each agent node removes itself (`plan[1:]`). When the plan is empty, the turn ends.
* 🔤 `plan` has **no reducer**, so a node's update **replaces** it. (`messages` has `add_messages`, so updates are **appended**.)

## A3. Structured output

```python
AgentName = Literal["rag", "github", "calendar", "gmail", "chat"]

class RoutePlan(BaseModel):
    steps: list[AgentName] = Field(description="Agents to run, in order. Usually just one.")
    reason: str = Field(description="Very short reason, max 8 words.")

router = get_chat_model().with_structured_output(RoutePlan)
```

* 🎯 `with_structured_output` makes the LLM answer with a **`RoutePlan` object** instead of free text.
* 💡 Parsing free text like *"I think the calendar agent should handle this"* is fragile. With structured output we get `decision.steps == ["calendar"]`, guaranteed to be valid names, thanks to `Literal`.
* 💡 Why **one** planning call instead of asking the supervisor again after every agent? It saves LLM requests (the Gemini free tier has a per-minute limit) and keeps the flow predictable.

## A4. `supervisor_node`

```python
async def supervisor_node(state: AssistantState) -> dict:
    with ui.console.status("[dim]🧭 Supervisor is choosing an agent...[/dim]"):
        decision: RoutePlan = await router.ainvoke(
            [SystemMessage(content=SUPERVISOR_PROMPT)] + state["messages"]
        )
    steps = list(dict.fromkeys(decision.steps))[:3] or ["chat"]
    for step in steps:
        ui.show_route(step, decision.reason)
    return {"plan": steps}
```

* 🎯 Asks the router, cleans the plan, prints `🧭 Supervisor → ...`, and saves the plan in the state.
* 💡 Safety cleanup:
  * duplicates removed (`dict.fromkeys`);
  * at most 3 steps (`[:3]`);
  * an empty plan becomes `["chat"]` (`or`).
  
  Never fully trust LLM output.
* 🔤 `decision: RoutePlan = ...` is a type hint on a variable. It's just a note for readers and the editor.

## A5. `next_step`: the conditional edge

```python
def next_step(state: AssistantState) -> str:
    return state["plan"][0] if state["plan"] else END
```

* 🎯 Returns the **name of the next node**: the first agent in the plan, or `END`.
* 💡 The same function is used after the supervisor **and** after every agent. That's what makes multi-step plans work: calendar → gmail → END.

## A6. `make_agent_node`: a sub-agent graph as one node

```python
def make_agent_node(key: str, agent):
    async def node(state: AssistantState) -> dict:
        remaining = state["plan"][1:]

        if isinstance(agent, str):                 # the agent is OFF
            text = f"⚠️ The {ui.AGENTS[key][1]} is not available: {agent}. ..."
            ui.show_answer(key, text)
            return {"messages": [AIMessage(content=text, name=key)], "plan": remaining}

        try:
            result = await agent.ainvoke({"messages": state["messages"]}, {"recursion_limit": 30})
            text = message_text(result["messages"][-1])
        except Exception as e:
            text = f"❌ Error: {type(e).__name__}: {e}"
            remaining = []

        ui.show_answer(key, text)
        return {"messages": [AIMessage(content=text, name=key)], "plan": remaining}
    return node
```

| Code | 💡 Why |
|---|---|
| factory + closure | 4 agents, 1 piece of code. Each `node` remembers its own `key` and `agent`. |
| `isinstance(agent, str)` | `main.py` passes a **string** (the reason) for agents that are off. Instead of crashing, we explain how to switch it on. |
| `agent.ainvoke({"messages": state["messages"]}, ...)` | Runs the **whole** sub-agent loop (agent → approval → tools → …) with the full conversation. This is a **subgraph** call. |
| `recursion_limit: 30` | Max steps inside the sub-agent. Stops an agent that keeps calling tools forever. |
| `except Exception` | For example, a `429` rate limit. Show it, **cancel the rest of the plan** (`remaining = []`), keep the app alive. |
| Return **only the final answer** | The sub-agent's tool calls and results stay inside the sub-agent. Memory keeps just *question → answer*. That makes the history short (cheaper, faster) and easy for the **next** agent to read. Example: Gmail sees *"✅ Meeting created, Meet link: https://meet.google.com/abc"* and can put that link in the email. |
| `AIMessage(..., name=key)` | Labels which agent wrote the message. |

## A7. `chat_node`

A plain LLM call with no tools, for "hi", "what can you do?" and general questions. `temperature=0.5` makes small talk sound more natural.

## A8. Building and compiling

```python
builder = StateGraph(AssistantState)
builder.add_node("supervisor", supervisor_node)
builder.add_node("chat", chat_node)
for key in ("rag", "github", "calendar", "gmail"):
    builder.add_node(key, make_agent_node(key, agents[key]))

destinations = ["rag", "github", "calendar", "gmail", "chat", END]
builder.add_edge(START, "supervisor")
builder.add_conditional_edges("supervisor", next_step, destinations)
for key in ("rag", "github", "calendar", "gmail", "chat"):
    builder.add_conditional_edges(key, next_step, destinations)

return builder.compile(checkpointer=MemorySaver())
```

* 💡 `destinations` is a **list** (not a dict like in `agent_builder.py`) because `next_step` already returns real node names. The list just tells LangGraph which targets are possible, so it can draw the graph (`/graph`).
* 💡 `checkpointer=MemorySaver()`: after **every** step the state is saved under the conversation's `thread_id`. That's the memory from lecture 05.

---

# Part B · `main.py`

## B1. `setup_rag`

```python
if not (has_key("PINECONE_API_KEY") and has_key("GOOGLE_API_KEY")):
    return reason, (False, reason)
try:
    chunks = count_chunks()
    ...
    return build_rag_agent(), (True, detail)
except Exception as e:
    ...
```

* 🎯 Checks the keys, talks to Pinecone once (this also **creates** the index on the very first run), and returns `(agent, banner_status)`.
* 🔤 Returning a **tuple** lets one function give back two things: `agents["rag"], statuses["rag"] = setup_rag()`.

## B2. `main()`: start-up

```python
async with AsyncExitStack() as stack:
    with ui.console.status("🔌 Connecting to MCP servers ..."):
        mcp_tools = await connect_all(stack)

    agents["rag"], statuses["rag"] = setup_rag()
    builders = {"github": build_github_agent, "calendar": build_calendar_agent, "gmail": build_gmail_agent}
    for key, build in builders.items():
        tools = mcp_tools[key]
        if isinstance(tools, str):
            agents[key] = tools; statuses[key] = (False, tools)
        else:
            agents[key] = build(tools); statuses[key] = (True, f"{len(tools)} MCP tools")

    graph = build_supervisor_graph(agents)
    scheduler.start()
    ui.banner(chat_model_name(), statuses)
```

* 💡 `async with AsyncExitStack() as stack:` means **all MCP connections live as long as this block**. When you type `/exit`, the block ends and every server process is closed cleanly.
* 🔤 `builders` is a dict of **functions** (no brackets = the function itself, not a call). `build(tools)` calls whichever one we're looping over.

## B3. The chat loop

```python
state = {"thread_id": f"chat-{uuid.uuid4().hex[:8]}"}
while True:
    try:
        text = await asyncio.to_thread(ui.user_prompt)
    except (EOFError, KeyboardInterrupt):
        break
    ...
    if text.startswith("/"):
        if not await handle_command(text, graph, state):
            break
        continue

    config = {"configurable": {"thread_id": state["thread_id"]}}
    try:
        await graph.ainvoke({"messages": [HumanMessage(content=text)], "plan": []}, config)
    except Exception as e:
        ui.error(...)
```

| Code | 💡 Why |
|---|---|
| `uuid.uuid4().hex[:8]` | A random id like `chat-3f9a1c2b`: a new conversation each time the app starts. |
| `asyncio.to_thread(ui.user_prompt)` | `input()` **blocks**. In a thread, the event loop stays free, so scheduled emails can fire while you type. |
| `except (EOFError, KeyboardInterrupt)` | Ctrl+C / Ctrl+Z quits nicely instead of showing a traceback. |
| `{"configurable": {"thread_id": ...}}` | Tells the checkpointer **which conversation** to load and save. |
| send **only** the new `HumanMessage` | The checkpointer adds the history itself (lecture 05). |
| `"plan": []` | Starts every turn with an empty plan. |
| We don't print the result | The **nodes** already printed everything live (routes, tools, answers). |

## B4. `handle_command`

| Command | Does |
|---|---|
| `/help` | `ui.help_panel()`, example questions |
| `/upload <pdf>` | `await asyncio.to_thread(ingest_pdf, path)`: index a PDF without leaving the chat |
| `/jobs` | lists scheduled emails |
| `/graph` | prints the supervisor graph as Mermaid text (paste at <https://mermaid.live>) |
| `/new` | new `thread_id` = empty memory |
| `/exit` | returns `False`, so the loop breaks |

* 🔤 `state` is a **dict**, so `handle_command` can change `state["thread_id"]` and `main` sees the change. (Reassigning a plain string variable inside a function would not change the caller's variable.)

## B5. `asyncio.run(main())`

Starts Python's event loop and runs `main()` until it returns. It's the one and only place where "normal" code enters the async world.
