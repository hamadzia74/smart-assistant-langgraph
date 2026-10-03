# 02 · Python syntax used in this project

> Every "strange-looking" Python feature in the code, explained with a tiny example and a pointer to where it's used.
> Keep this page open while you read the other docs.

---

## 1. Imports

```python
import os                                   # import a whole module, use it as os.getenv(...)
from pathlib import Path                    # import ONE name from a module, use it as Path(...)
from langgraph.graph import END, START      # import several names at once
import ui                                   # our OWN file ui.py, used as ui.show_answer(...)
```

**Why** both styles? `import ui` keeps the prefix (`ui.success(...)`), so you always know where a function comes from. `from x import y` is shorter for names used very often.

**Import inside a function** (`utils.py`):

```python
if has_key("GOOGLE_API_KEY"):
    from langchain_google_genai import ChatGoogleGenerativeAI
```

The import only runs if that branch runs. So a user of Groq doesn't need the Gemini package loaded.

---

## 2. Type hints: `x: str`, `-> dict`, `list[str]`, `dict[str, tuple[bool, str]]`

```python
def has_key(name: str) -> bool:
```

- `name: str` → "name should be a string"
- `-> bool` → "this function returns True/False"

Python does **not** enforce them at runtime. They are notes for humans and editors (VS Code shows errors and autocomplete). **But** LangChain and Pydantic **do read them**: `@tool` turns `query: str` into the tool's argument schema the LLM sees.

| Hint                    | Means                              | Example value                     |
| ----------------------- | ---------------------------------- | --------------------------------- |
| `list[str]`             | list of strings                    | `["rag", "gmail"]`                |
| `dict[str, int]`        | keys are str, values int           | `{"page": 3}`                     |
| `tuple[bool, str]`      | exactly 2 items: a bool then a str | `(True, "4 MCP tools")`           |
| `str \| Path`           | either a str **or** a Path         | `"a.pdf"` or `Path("a.pdf")`      |
| `list[BaseTool] \| str` | tools, or an error string          | used in `mcp_servers.connect_all` |

---

## 3. `Literal[...]`: "only these exact values"

```python
from typing import Literal
AgentName = Literal["rag", "github", "calendar", "gmail", "chat"]
```

Used in `supervisor.py`. With structured output, the LLM's answer is **validated**: if it says `"email"` instead of `"gmail"`, Pydantic rejects it. So the router can never invent an agent that doesn't exist.

---

## 4. Classes, inheritance, Pydantic models

```python
class AssistantState(MessagesState):   # AssistantState INHERITS everything MessagesState has
    plan: list[str]                    # ... and adds one more field
```

```python
class RoutePlan(BaseModel):            # Pydantic model = a class that validates its data
    steps: list[AgentName] = Field(description="Agents to run, in order.")
    reason: str = Field(description="Very short reason.")
```

`Field(description=...)` is sent to the LLM as an instruction for that field.

---

## 5. f-strings

```python
f"Pinecone index '{INDEX_NAME}': {chunks} chunks"
f"{now:%A, %d %B %Y, %H:%M}"           # format a datetime: Friday, 02 October 2026, 15:30
f"{len(chunks) / len(pages):.1f}"      # number with 1 decimal: 2.5
f"{pages[0].page_content[:120]!r}"     # !r = show it like Python would (with quotes, \n visible)
```

Anything inside `{ }` is evaluated. After `:` comes a **format** spec.

---

## 6. Slicing and small list tricks

```python
text[:160]               # first 160 characters
state["plan"][1:]        # everything except the first item
state["plan"][0]         # the first item
list(dict.fromkeys(x))   # remove duplicates, keep order: ["a","b","a"] -> ["a","b"]
" ".join(text.split())   # collapse all newlines/extra spaces into single spaces
```

**List comprehension** = a short `for` loop that builds a list:

```python
tools = [t for t in tools if t.name in allowed]
# same as:
result = []
for t in tools:
    if t.name in allowed:
        result.append(t)
```

`next(...)` = "first item that matches, or a default":

```python
send_tool = next((t for t in mcp_tools if t.name == "send_gmail_message"), None)
```

`all(...)` = True if every item is True (`agent_builder.py` approval: _all_ risky calls approved?).

---

## 7. Dictionaries

```python
os.getenv("GEMINI_MODEL", "gemini-3.8-flash")   # value, or the default if missing
doc.metadata.get("page", 0)                     # same idea for dicts
{"messages": [response]}                        # a node's "state update"
name, _, argument = command.partition(" ")      # "/upload a.pdf" -> "/upload", " ", "a.pdf"
```

`_` is a name for "I don't need this value".

---

## 8. Decorators: `@tool`

```python
@tool
def search_pdf(query: str) -> str:
    """Search the user's PDF documents..."""
```

A decorator **wraps** the function below it. `@tool` turns a normal function into a LangChain `Tool` object with:

- `.name` → `"search_pdf"` (from the function name)
- `.description` → the **docstring** (so the docstring is a prompt for the LLM!)
- `.args` → `{"query": {"type": "string"}}` (from the type hints)

---

## 9. Functions inside functions: closures and factories

```python
def make_agent_node(key, agent):          # the FACTORY
    async def node(state):                # the function it builds
        ... uses key and agent ...        # "remembers" them = a CLOSURE
    return node                           # return the function itself (no brackets!)
```

Used in `supervisor.py` (one node per agent), `scheduler.py` (`make_schedule_email_tool`) and `agent_builder.py` (all node functions remember `llm_with_tools`, `agent_key`…). It's a way to make **many similar functions** without copy-paste.

---

## 10. `global`

```python
_retriever = None             # module-level variable

def search_pdf(query):
    global _retriever         # "when I assign _retriever, change the MODULE one"
    if _retriever is None:
        _retriever = ...      # created only once ("lazy initialisation")
```

Without `global`, the assignment would create a **new local** variable inside the function.

---

## 11. `with` and `async with`: context managers

```python
with ui.console.status("thinking..."):   # start the spinner
    response = ...                        # do work
                                          # spinner stops automatically, even on errors
with open("x.log", "a") as f: ...         # file closes automatically
```

A context manager has a **setup** and a guaranteed **cleanup**. `async with` is the same for async resources (network connections, MCP sessions).

**`AsyncExitStack`** (`main.py`, `mcp_servers.py`) = a "basket" of async-with's. Each `await stack.enter_async_context(x)` opens `x` now and **closes it when the stack closes**. We need it because the number of MCP servers is decided at runtime, and the connections must stay open after the function that opened them returns.

---

## 12. `async def`, `await`, `asyncio.run`

Network calls are slow. `async` code can **wait without freezing** everything else.

```python
async def agent_node(state):                       # an async function = a "coroutine"
    response = await llm_with_tools.ainvoke(...)   # await = "pause here until the LLM answers"
    return {"messages": [response]}

asyncio.run(main())                                # start the event loop, run main() to the end
```

Rules of thumb:

- You can only use `await` **inside** an `async def`.
- LangChain: `invoke` ↔ `ainvoke`, `stream` ↔ `astream` (the "a" = async version).
- **MCP tools are async-only**, which is why our whole graph is async (`graph.ainvoke`).
- `await asyncio.to_thread(func, arg)` runs a normal **blocking** function (like `input()` or `ingest_pdf`) in a helper thread, so the event loop stays free. That's how scheduled emails can fire while the app waits for your typing.
- `await asyncio.wait_for(x, timeout=120)` gives up after 120 seconds.

---

## 13. `try / except`

```python
try:
    count = ingest_pdf(path)
except Exception as e:            # any error lands here; e is the error object
    ui.error(f"Upload failed: {e}")
```

We catch errors at the **edges** (one user message, one MCP server) so one failure never crashes the whole app.

---

## 14. `if __name__ == "__main__":`

```python
if __name__ == "__main__":
    asyncio.run(main())
```

`__name__` is `"__main__"` only when you run the file directly (`python main.py`). When another file imports it, this block is skipped.

---

## 15. `rich` markup

```python
ui.console.print("[green]✅ ready[/green]")       # colour
ui.console.print("[bold]Hi[/bold] [dim]note[/dim]")
```

`[style] ... [/style]` works like HTML tags. See [doc 03](03_utils_and_ui.md).
