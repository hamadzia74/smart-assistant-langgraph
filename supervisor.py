"""
supervisor.py - the MAIN graph: a supervisor that sends each request to the right sub-agent.

                              +------------+
         START ─────────────▶ | supervisor |  (one LLM call: "which agents, in what order?")
                              +------------+
                                    │ next_step()
            ┌──────────┬────────────┼────────────┬──────────┐
            ▼          ▼            ▼            ▼          ▼
         📚 rag    🐙 github   📅 calendar   📧 gmail    💬 chat
            │          │            │            │          │
            └──────────┴─── next_step() ─────────┴──────────┘
                     (run the next planned agent, or END)

The supervisor writes a PLAN, e.g.:
    "What does my PDF say about leave?"                 -> ["rag"]
    "Book a meeting with ali@x.com at 3pm and email him the agenda" -> ["calendar", "gmail"]

Each sub-agent is a full graph (agent -> approval -> tools loop, see agent_builder.py)
used here as ONE node. A graph inside a graph is called a SUBGRAPH.

MEMORY: this graph is compiled with a MemorySaver checkpointer (lecture 05), so
follow-up questions like "send it now" work. The sub-agents get the conversation
from here, so they don't need their own memory.
"""

from typing import Literal

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from pydantic import BaseModel, Field

import ui
from utils import get_chat_model, message_text

# Literal["a", "b"] means: the value must be EXACTLY one of these strings.
# The LLM's structured output is checked against it, so it can't invent an agent.
AgentName = Literal["rag", "github", "calendar", "gmail", "chat"]

SUPERVISOR_PROMPT = """You are the supervisor of a team of assistant agents.
Read the conversation and plan which agent(s) must handle the user's LATEST message.

Agents:
- rag: questions about the user's uploaded PDF documents / knowledge base / "my document".
- github: anything about GitHub - repositories, issues, pull requests, commits, code, users.
- calendar: Google Calendar - read meetings/events/schedule, check free time, create,
  move or cancel meetings at specific times.
- gmail: email - read/search inbox, write or draft emails, send emails, send emails
  later at a specific time.
- chat: greetings, small talk, questions about what you can do, general knowledge.

Rules:
- Usually choose exactly ONE agent.
- Choose two (in order) only if the request clearly needs two, e.g.
  "create a meeting and then email the agenda" -> ["calendar", "gmail"].
- Use earlier messages for context: "send it" after a draft email -> gmail."""


# ------------------------------------------------------------
# 1. State: what flows between the nodes
# ------------------------------------------------------------
class AssistantState(MessagesState):
    """
    MessagesState already has:  messages: list  (with the add_messages reducer)
    We add one more field:
        plan -> the agents still waiting to run in THIS turn, e.g. ["calendar", "gmail"]
    """
    plan: list[str]


# ------------------------------------------------------------
# 2. Structured output: force the LLM to answer in a fixed shape
# ------------------------------------------------------------
class RoutePlan(BaseModel):
    """The supervisor's decision. Field descriptions are sent to the LLM as instructions."""

    steps: list[AgentName] = Field(description="Agents to run, in order. Usually just one.")
    reason: str = Field(description="Very short reason, max 8 words.")


def build_supervisor_graph(agents: dict[str, object]):
    """
    agents = {"rag": <compiled graph> or "why it is off", "github": ..., ...}
    Returns the compiled supervisor graph with memory.
    """
    # with_structured_output makes the LLM return a RoutePlan object instead of text.
    router = get_chat_model().with_structured_output(RoutePlan)
    chat_llm = get_chat_model(temperature=0.5)  # a bit more natural for small talk

    # ------------------------------------------------------------
    # Node: supervisor - make the plan
    # ------------------------------------------------------------
    async def supervisor_node(state: AssistantState) -> dict:
        with ui.console.status("[dim]🧭 Supervisor is choosing an agent...[/dim]"):
            decision: RoutePlan = await router.ainvoke(
                [SystemMessage(content=SUPERVISOR_PROMPT)] + state["messages"]
            )

        # dict.fromkeys(...) removes duplicates but keeps the order; [:3] = at most 3 steps.
        steps = list(dict.fromkeys(decision.steps))[:3] or ["chat"]
        for step in steps:
            ui.show_route(step, decision.reason)
        return {"plan": steps}

    # ------------------------------------------------------------
    # Routing function: which node runs next?
    # ------------------------------------------------------------
    def next_step(state: AssistantState) -> str:
        # The first agent in the plan, or END when the plan is empty.
        return state["plan"][0] if state["plan"] else END

    # ------------------------------------------------------------
    # Node factory: wrap a sub-agent graph as ONE node
    # ------------------------------------------------------------
    def make_agent_node(key: str, agent):
        """
        Returns an async node function for sub-agent `key`.
        A function that builds and returns another function = a "factory".
        Each returned node "remembers" its own key and agent (a closure).
        """

        async def node(state: AssistantState) -> dict:
            remaining = state["plan"][1:]  # everything after this agent

            # The agent is OFF (missing keys): explain instead of crashing.
            if isinstance(agent, str):
                text = (f"⚠️ The {ui.AGENTS[key][1]} is not available: {agent}.\n\n"
                        "See `docs/01_setup.md` to set it up.")
                ui.show_answer(key, text)
                return {"messages": [AIMessage(content=text, name=key)], "plan": remaining}

            try:
                # Run the whole sub-agent loop. It gets the full conversation so far.
                result = await agent.ainvoke(
                    {"messages": state["messages"]},
                    {"recursion_limit": 30},   # stop a confused agent from looping forever
                )
                text = message_text(result["messages"][-1])
            except Exception as e:
                # e.g. 429 = free-tier rate limit. Show it, stop this turn, keep the app alive.
                text = f"❌ Error: {type(e).__name__}: {e}"
                remaining = []

            ui.show_answer(key, text)
            # Only the FINAL answer goes into the shared memory, not every tool call.
            # That keeps the history short and readable for the next agents.
            # name=key labels which agent wrote it.
            return {"messages": [AIMessage(content=text, name=key)], "plan": remaining}

        return node

    # ------------------------------------------------------------
    # Node: chat - general conversation, no tools
    # ------------------------------------------------------------
    async def chat_node(state: AssistantState) -> dict:
        system = SystemMessage(content=(
            "You are Smart Assistant, a friendly helper. You have agents for: "
            "PDF documents (RAG), GitHub, Google Calendar and Gmail. "
            "Answer briefly. If asked what you can do, list those abilities with examples."
        ))
        with ui.console.status("[dim]⏳ thinking...[/dim]"):
            response = await chat_llm.ainvoke([system] + state["messages"])
        text = message_text(response)
        ui.show_answer("chat", text)
        return {"messages": [AIMessage(content=text, name="chat")], "plan": state["plan"][1:]}

    # ------------------------------------------------------------
    # Build the graph
    # ------------------------------------------------------------
    builder = StateGraph(AssistantState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("chat", chat_node)
    for key in ("rag", "github", "calendar", "gmail"):
        builder.add_node(key, make_agent_node(key, agents[key]))

    # The possible destinations of next_step: every agent node, or END.
    destinations = ["rag", "github", "calendar", "gmail", "chat", END]

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges("supervisor", next_step, destinations)
    # After ANY agent finishes, check the plan again: next agent or END.
    for key in ("rag", "github", "calendar", "gmail", "chat"):
        builder.add_conditional_edges(key, next_step, destinations)

    # MemorySaver = remember every conversation (per thread_id) while the app runs.
    return builder.compile(checkpointer=MemorySaver())
