# 03 · `utils.py` and `ui.py`: the helpers

> Format of the walkthrough docs: a **piece of code** followed by **🎯 What** it does, **💡 Why** it's there, and **🔤 Syntax** notes.

---

# Part A · `utils.py`

## A1. Loading `.env`

```python
from dotenv import load_dotenv
load_dotenv()
```

- 🎯 **What:** reads `.env` and copies every `KEY=value` line into the process's environment variables.
- 💡 **Why:** secrets stay **out of the code**. `os.getenv("GOOGLE_API_KEY")` can now read them from any file. LangChain's Gemini class also reads `GOOGLE_API_KEY` from the environment automatically, which is why we never pass the key by hand.
- 🔤 **Syntax:** it runs at **import time** (top level of the module), so the first `import utils` loads the keys for the whole program.

## A2. UTF-8 on Windows

```python
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
```

- 🎯 Tells Python to print in UTF-8.
- 💡 Old Windows consoles use a code page that can't show emojis (📚 🐙 📅) and would crash with `UnicodeEncodeError`.
- 🔤 `try/except/pass` = "try it; if it fails, ignore it". Safe because this is only cosmetic.

## A3. `has_key`

```python
def has_key(name: str) -> bool:
    value = os.getenv(name, "")
    return bool(value) and not value.startswith("your_")
```

- 🎯 True only for a **real** key.
- 💡 `.env.example` contains placeholders like `your_google_api_key_here`. If you copy it and forget one key, we treat that key as missing instead of sending a fake key to Google and getting a confusing error.
- 🔤 `bool("")` is `False`, `bool("abc")` is `True`. `and` needs both sides True.

## A4. `get_chat_model`: choosing the brain

```python
def get_chat_model(temperature: float = 0.0) -> BaseChatModel:
    if has_key("GOOGLE_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        return ChatGoogleGenerativeAI(model=model, temperature=temperature)
    if has_key("GROQ_API_KEY"):
        ...
    raise RuntimeError("No LLM key found ...")
```

- 🎯 Returns a ready-to-use chat model: Gemini first, Groq second.
- 💡 Same priority as the course's `utils.py`. All other files only call `get_chat_model()`, so switching provider is a one-file change. That works because every LangChain chat model shares the same **interface** (`BaseChatModel`: `invoke`, `ainvoke`, `bind_tools`, `with_structured_output`).
- 💡 `temperature=0.0` gives the most predictable output. Tool-calling agents must be **precise** (a correct date and email), not creative.
- 💡 Unlike the course we `raise` instead of using a Mock LLM, because a fake model cannot really read your calendar.
- 🔤 `temperature: float = 0.0` is a parameter with a **default value**. `raise` stops the function with an error.

## A5. Embeddings

```python
EMBEDDING_DIM = 768

def get_embeddings() -> Embeddings:
    ...
    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        output_dimensionality=EMBEDDING_DIM,
    )
```

- 🎯 The model that turns text into **768 numbers**.
- 💡 `gemini-embedding-001` normally returns 3072 numbers. 768 is accurate enough for PDFs and uses 4× less space in Pinecone (the free plan has 2 GB).
- ⚠️ The Pinecone index is created with `dimension=EMBEDDING_DIM`. If you change this number later, you must **delete the index** in Pinecone (or use a new `PINECONE_INDEX_NAME`), because vectors of different sizes cannot live in one index.
- 🔤 `UPPER_CASE` names are a convention for **constants** (values that don't change).

## A6. `message_text`

```python
def message_text(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    ...join the "text" parts...
```

- 🎯 Always returns plain text from a message.
- 💡 Gemini sometimes returns `content` as a **list of parts** (`[{"type": "text", "text": "Hi"}]`), and MCP tool results also come as lists. Printing that list would look ugly.
- 🔤 `isinstance(x, str)` asks "is x a string?".

---

# Part B · `ui.py`: all terminal output

**Big idea:** the agent files say **what** to show (`ui.show_tool_call(...)`). `ui.py` decides **how** it looks. Want other colours or icons? Edit only this file.

## B1. The console and the agent table

```python
console = Console()

AGENTS = {
    "supervisor": ("🧭", "Supervisor", "white"),
    "rag": ("📚", "RAG Agent", "cyan"),
    ...
}
```

- 🎯 `Console` is rich's smart `print`: it understands colours, panels, tables and markdown.
- 💡 One dict holds every agent's **icon, name, colour**, so every panel/message for the Gmail agent is yellow with 📧, everywhere.
- 🔤 A dict of **tuples**. Unpack a tuple into 3 variables in one line: `icon, name, colour = AGENTS[key]`. Use `_` for parts you don't need: `_, _, colour = AGENTS[key]`.

## B2. `banner`

```python
table = Table(title="Agents", show_header=True, header_style="bold")
table.add_column("Agent")
...
for key, (ok, detail) in statuses.items():
    icon, name, colour = AGENTS[key]
    status = "[green]✅ ready[/green]" if ok else "[red]❌ off[/red]"
    table.add_row(f"[{colour}]{icon} {name}[/{colour}]", status, detail)
```

- 🎯 Draws the startup table with ✅ / ❌ per agent.
- 💡 A beginner immediately sees which keys are missing, **before** asking a question that would fail.
- 🔤 `for key, (ok, detail) in statuses.items()` unpacks each `(key, (bool, str))` pair. `A if condition else B` is a one-line if/else (the "ternary" expression). `[green]...[/green]` is rich markup.

## B3. Live progress lines

```python
def show_route(agent_key, reason): ...        # 🧭 Supervisor → 📅 Calendar Agent (reason)
def show_tool_call(agent_key, tool_name, args): ...   #    🔧 get_events {...}
def show_tool_result(text): ...               #    📥 first 140 characters of the result
```

- 🎯 Prints each step **while it happens**.
- 💡 You can **see the agent think**: which agent was picked, which tool it called with which arguments, what came back. That's the best way to learn (and debug) agents. Results are shortened so the screen stays readable.
- 🔤 `json.dumps(args, ensure_ascii=False, default=str)` turns a dict into a one-line string. `ensure_ascii=False` keeps emojis and Urdu readable. `default=str` converts anything unusual (like dates) with `str()` instead of crashing.

## B4. `show_answer`

```python
console.print(Panel(Markdown(text or "_(no answer)_"), title=f"{icon} {name}",
                    title_align="left", border_style=colour))
```

- 🎯 The final answer in a box coloured like the agent.
- 💡 LLMs write Markdown (`**bold**`, lists). `Markdown(...)` renders it nicely instead of showing the raw `**` stars.
- 🔤 `text or "..."` gives `text` if it is not empty, otherwise the fallback.

## B5. `ask_approval`: human-in-the-loop

```python
console.print(Panel(table, title=f"⚠️  {icon} {name} wants to run [bold]{tool_name}[/bold]", border_style="red"))
return Confirm.ask("   ✅ Approve?", default=False)
```

- 🎯 Shows every argument of the risky tool call in a red box and asks y/n.
- 💡 You see **exactly** what will be sent (recipient, subject, body, time) before it happens. `default=False` means just pressing Enter = **No**: safe by default.
- 🔤 `Confirm.ask` keeps asking until you type y/yes/n/no and returns `True`/`False`.

## B6. Small helpers

```python
def info(text): console.print(f"ℹ️  {text}")
def success(text): console.print(f"[green]✅ {text}[/green]")
def warn(text): ...      # ⚠️ yellow
def error(text): ...     # ❌ red
def section(title): console.print(Rule(f"[bold]{title}[/bold]"))   # ───── title ─────
```

Same icon + colour for the same kind of message everywhere = output that's easy to scan.

---

### ✏️ Try it

```powershell
python -c "import ui; ui.success('it works'); ui.show_answer('gmail', '**Hello** from the _Gmail_ agent')"
```
