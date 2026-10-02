"""
ui.py - everything that PRINTS to the terminal lives here.

We use the `rich` library instead of plain print() because it gives us:
    Panel   -> a box with a coloured border and a title
    Table   -> neat rows and columns
    Rule    -> a horizontal line with a title in the middle
    Markdown-> renders **bold**, lists and `code` from the LLM's answers
    status  -> a spinner ("⏳ thinking...") while we wait for the LLM

WHY a separate file?
    The agent files only say WHAT to show (e.g. ui.show_tool_call(...)).
    HOW it looks (colours, icons, boxes) is decided here, in one place.
    Want different colours? Change this file only.
"""

import json

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm
from rich.rule import Rule
from rich.table import Table

# One shared Console object. console.print() is rich's "smart print".
console = Console()

# ------------------------------------------------------------
# Every agent gets an icon, a display name and a colour.
# A dict of tuples: key -> (icon, name, colour)
# ------------------------------------------------------------
AGENTS = {
    "supervisor": ("🧭", "Supervisor", "white"),
    "rag": ("📚", "RAG Agent", "cyan"),
    "github": ("🐙", "GitHub Agent", "magenta"),
    "calendar": ("📅", "Calendar Agent", "green"),
    "gmail": ("📧", "Gmail Agent", "yellow"),
    "chat": ("💬", "Assistant", "blue"),
}


def banner(model_name: str, statuses: dict[str, tuple[bool, str]]) -> None:
    """
    The welcome screen: title + a table showing which agents are ready.

    statuses looks like: {"rag": (True, "index: my-pdfs"), "github": (False, "GITHUB_TOKEN missing")}
    """
    console.print()
    console.print(
        Panel.fit(
            "[bold]🤖 Smart Assistant[/bold]  -  LangGraph multi-agent\n"
            f"[dim]🧠 Brain: {model_name}[/dim]",
            border_style="bright_blue",
        )
    )

    table = Table(title="Agents", show_header=True, header_style="bold")
    table.add_column("Agent")
    table.add_column("Status", justify="center")
    table.add_column("Details", style="dim")

    for key, (ok, detail) in statuses.items():
        icon, name, colour = AGENTS[key]
        status = "[green]✅ ready[/green]" if ok else "[red]❌ off[/red]"
        table.add_row(f"[{colour}]{icon} {name}[/{colour}]", status, detail)

    console.print(table)
    console.print(
        "[dim]Commands: /help  /upload <file.pdf>  /jobs  /graph  /new  /exit[/dim]\n"
    )


def help_panel() -> None:
    """Shows example questions for every agent."""
    text = (
        "[cyan]📚 RAG[/cyan]       What does my PDF say about refund policy?\n"
        "[magenta]🐙 GitHub[/magenta]    List my repositories / Summarize open issues in owner/repo\n"
        "[green]📅 Calendar[/green]  What meetings do I have tomorrow?\n"
        "             Create a meeting with ali@example.com on Friday 3pm for 30 minutes\n"
        "[yellow]📧 Gmail[/yellow]     Draft an email to sara@example.com about the project update\n"
        "             Send it tomorrow at 9am\n\n"
        "[bold]Commands[/bold]\n"
        "  /upload <path.pdf>  add a PDF to the Pinecone knowledge base\n"
        "  /jobs               show scheduled emails\n"
        "  /graph              print the supervisor graph (Mermaid diagram)\n"
        "  /new                start a fresh conversation (empty memory)\n"
        "  /exit               quit"
    )
    console.print(Panel(text, title="❓ Help", border_style="bright_blue"))


def user_prompt() -> str:
    """Reads one line from the user. console.input() is like input() but supports colour."""
    return console.input("[bold bright_white]👤 You ›[/bold bright_white] ").strip()


def show_route(agent_key: str, reason: str) -> None:
    """Prints which agent the supervisor picked, and why."""
    icon, name, colour = AGENTS[agent_key]
    console.print(f"🧭 [dim]Supervisor →[/dim] [{colour}]{icon} {name}[/{colour}] [dim]({reason})[/dim]")


def show_tool_call(agent_key: str, tool_name: str, args: dict) -> None:
    """Prints a tool call in a dim colour so the final answer stands out more."""
    _, _, colour = AGENTS[agent_key]
    # json.dumps turns a dict into a one-line string; ensure_ascii=False keeps emojis/Urdu readable.
    args_text = json.dumps(args, ensure_ascii=False, default=str)
    if len(args_text) > 160:
        args_text = args_text[:160] + "…"
    console.print(f"   🔧 [{colour}]{tool_name}[/{colour}] [dim]{args_text}[/dim]")


def show_tool_result(text: str) -> None:
    """Prints the first part of a tool's result so you can see what came back."""
    preview = " ".join(str(text).split())  # collapse newlines/extra spaces into single spaces
    if len(preview) > 140:
        preview = preview[:140] + "…"
    console.print(f"   📥 [dim]{preview}[/dim]")


def show_answer(agent_key: str, text: str) -> None:
    """The final answer, inside a panel coloured like the agent that wrote it."""
    icon, name, colour = AGENTS[agent_key]
    console.print(
        Panel(
            Markdown(text or "_(no answer)_"),
            title=f"{icon} {name}",
            title_align="left",
            border_style=colour,
        )
    )


def ask_approval(agent_key: str, tool_name: str, args: dict) -> bool:
    """
    Human-in-the-loop: show what the agent WANTS to do and ask yes/no.
    Returns True if the user approved.
    """
    icon, name, colour = AGENTS[agent_key]
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="bold")
    table.add_column()
    for key, value in args.items():
        table.add_row(f"{key}:", str(value))

    console.print(
        Panel(
            table,
            title=f"⚠️  {icon} {name} wants to run [bold]{tool_name}[/bold]",
            title_align="left",
            border_style="red",
        )
    )
    # Confirm.ask returns True for y/yes and False for n/no.
    return Confirm.ask("   ✅ Approve?", default=False)


def info(text: str) -> None:
    console.print(f"ℹ️  {text}")


def success(text: str) -> None:
    console.print(f"[green]✅ {text}[/green]")


def warn(text: str) -> None:
    console.print(f"[yellow]⚠️  {text}[/yellow]")


def error(text: str) -> None:
    console.print(f"[red]❌ {text}[/red]")


def section(title: str) -> None:
    """A horizontal line with a title, used by the step-by-step scripts."""
    console.print(Rule(f"[bold]{title}[/bold]"))
