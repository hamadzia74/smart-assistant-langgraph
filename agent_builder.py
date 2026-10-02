"""
agent_builder.py - ONE function that builds a tool-using sub-agent.

All 4 sub-agents (RAG, GitHub, Calendar, Gmail) work the same way. Only their
TOOLS and their SYSTEM PROMPT differ. So instead of copying the same graph code
4 times, we write it once here and call it 4 times.

This is the ReAct loop from lecture 04, plus a human-approval step from lecture 06:

        START
          |
          v
      +-------+  tool calls?  +----------+  approved  +-------+
      | agent | ------------> | approval | ---------> | tools |
      +-------+               +----------+            +-------+
        ^  |                       | rejected             |
        |  | no tool calls         v                      |
        |  v                  (back to agent)             |
        | END                                             |
        +-------------------------------------------------+
                         tool results go back to the agent

    agent    -> the LLM reads the conversation and either answers or asks for tools
    approval -> if a "sensitive" tool (send email, create meeting) was requested,
                ask the human in the terminal. Safe tools pass straight through.
    tools    -> runs the tool calls and adds the results to the conversation
"""

from datetime import datetime

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

import ui
from utils import get_chat_model, message_text


def build_tool_agent(
    agent_key: str,
    tools: list[BaseTool],
    system_prompt: str,
    sensitive_tools: set[str] = frozenset(),
):
    """
    Builds and compiles a sub-agent graph.

    agent_key       -> "rag", "github", "calendar" or "gmail" (used for icons/colours)
    tools           -> the tools this agent may call
    system_prompt   -> the agent's job description and rules
    sensitive_tools -> tool names that need a human "yes" before running

    Returns a compiled graph. Call it with: await graph.ainvoke({"messages": [...]})
    """
    # bind_tools sends the tools' names + descriptions + argument schemas to the LLM
    # with every request, so the LLM can reply with a "tool call" instead of text.
    llm_with_tools = get_chat_model().bind_tools(tools)

    # ToolNode is a prebuilt node: it reads the tool calls in the last AI message,
    # runs the matching tools, and returns one ToolMessage per call.
    # handle_tool_errors=True -> if a tool crashes, the error text goes back to the
    # LLM as a ToolMessage (so it can explain or retry) instead of crashing our app.
    tool_node = ToolNode(tools, handle_tool_errors=True)

    # ------------------------------------------------------------
    # Node 1: agent - the LLM thinks and decides
    # ------------------------------------------------------------
    # `async def` because MCP tools only work asynchronously, so the whole graph
    # runs with `await graph.ainvoke(...)`. Inside, we `await` the LLM call.
    async def agent_node(state: MessagesState) -> dict:
        # The LLM has no clock. Give it today's date so "tomorrow 3pm" works.
        now = datetime.now().astimezone()
        system = SystemMessage(
            content=f"{system_prompt}\n\nCurrent date and time: {now:%A, %d %B %Y, %H:%M} "
                    f"(UTC offset {now:%z})."
        )
        # The system prompt is added on every call, NOT stored in the state,
        # so it is not saved into memory again and again.
        with ui.console.status(f"[dim]⏳ {ui.AGENTS[agent_key][1]} is thinking...[/dim]"):
            response = await llm_with_tools.ainvoke([system] + state["messages"])

        for call in response.tool_calls:
            ui.show_tool_call(agent_key, call["name"], call["args"])

        # Returning {"messages": [response]} APPENDS to the list - MessagesState uses
        # the add_messages "reducer", which adds instead of replacing.
        return {"messages": [response]}

    # ------------------------------------------------------------
    # Node 2: approval - human-in-the-loop for sensitive tools
    # ------------------------------------------------------------
    def approval_node(state: MessagesState) -> dict:
        last_message = state["messages"][-1]
        risky_calls = [c for c in last_message.tool_calls if c["name"] in sensitive_tools]

        # Nothing risky -> return an empty update and let the graph continue to "tools".
        if not risky_calls:
            return {}

        approved = all(ui.ask_approval(agent_key, c["name"], c["args"]) for c in risky_calls)
        if approved:
            return {}

        # Rejected: every tool call MUST get an answer (a ToolMessage with the same id),
        # otherwise the LLM API complains. We answer each one with "cancelled".
        ui.warn("Cancelled - nothing was sent or changed.")
        cancelled = [
            ToolMessage(
                content="The user REJECTED this action. Nothing was done. "
                        "Tell the user it was cancelled and do not try again.",
                tool_call_id=call["id"],
            )
            for call in last_message.tool_calls
        ]
        return {"messages": cancelled}

    # ------------------------------------------------------------
    # Node 3: tools - run the tools, show a preview of each result
    # ------------------------------------------------------------
    async def tools_node(state: MessagesState) -> dict:
        with ui.console.status("[dim]⏳ running tool...[/dim]"):
            result = await tool_node.ainvoke(state)
        for msg in result["messages"]:
            ui.show_tool_result(message_text(msg))
        return result

    # ------------------------------------------------------------
    # Routing function used after the approval node
    # ------------------------------------------------------------
    def after_approval(state: MessagesState) -> str:
        # If approval added "cancelled" ToolMessages, go back to the agent to explain.
        # Otherwise the last message is still the AI's tool request -> run the tools.
        if isinstance(state["messages"][-1], ToolMessage):
            return "agent"
        return "tools"

    # ------------------------------------------------------------
    # Build the graph
    # ------------------------------------------------------------
    builder = StateGraph(MessagesState)          # state = {"messages": [...]}
    builder.add_node("agent", agent_node)
    builder.add_node("approval", approval_node)
    builder.add_node("tools", tools_node)

    builder.add_edge(START, "agent")
    # tools_condition looks at the last message:
    #   has tool calls -> returns "tools"     no tool calls -> returns END
    # The dict maps those return values to OUR node names ("tools" -> "approval").
    builder.add_conditional_edges("agent", tools_condition, {"tools": "approval", END: END})
    builder.add_conditional_edges("approval", after_approval, {"tools": "tools", "agent": "agent"})
    builder.add_edge("tools", "agent")           # the agent reads the tool results

    # No checkpointer here: MEMORY lives in the supervisor graph (supervisor.py).
    return builder.compile(name=f"{agent_key}_agent")
