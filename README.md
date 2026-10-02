# 🤖 Smart Assistant — a beginner-friendly LangGraph multi-agent

One terminal chatbot, five helpers. A **🧭 Supervisor** reads your message and hands it to the right sub-agent:

| Agent | What it does | Powered by |
|---|---|---|
| 📚 **RAG Agent** | Answers questions from **any PDF** you upload, with page citations | Pinecone (hosted vector DB) + Gemini embeddings |
| 🐙 **GitHub Agent** | Answers anything about repos, issues, PRs, commits, files (read-only) | GitHub's official **MCP** server |
| 📅 **Calendar Agent** | Reads your meetings, checks free time, creates / moves / cancels meetings (with Meet links) | `workspace-mcp` **MCP** server (Calendar tools) |
| 📧 **Gmail Agent** | Reads & searches mail, writes drafts, sends emails, **schedules** emails for later | `workspace-mcp` **MCP** server (Gmail tools) + APScheduler |
| 💬 **Assistant** | Greetings and general questions | Gemini |

Anything that **sends or changes** something (send email, schedule email, create/update/delete meeting) asks you **✅ Approve? [y/n]** first.

```
👤 You › Book a 30 min Google Meet with ali@example.com tomorrow at 3pm and email him the agenda
🧭 Supervisor → 📅 Calendar Agent (meeting then agenda email)
🧭 Supervisor → 📧 Gmail Agent (meeting then agenda email)
   🔧 get_events {"time_min": "2026-10-03T15:00:00+05:00", ...}
   📥 No events found ...
   🔧 manage_event {"action": "create", "summary": "Meeting with Ali", ...}
┌─ ⚠️  📅 Calendar Agent wants to run manage_event ──────────────┐
│  action:     create                                            │
│  start_time: 2026-10-03T15:00:00+05:00                         │
│  attendees:  ['ali@example.com']                               │
└────────────────────────────────────────────────────────────────┘
   ✅ Approve? [y/n] (n): y
┌─ 📅 Calendar Agent ────────────────────────────────────────────┐
│ ✅ Meeting created for Sat 3 Oct, 15:00–15:30 with a Meet link  │
└────────────────────────────────────────────────────────────────┘
...
```

---

## 🚀 Quick start (Windows PowerShell)

```powershell
cd D:\office\langraph-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
copy .env.example .env                # then paste your keys into .env  (see docs/01_setup.md)
python ingest.py data\sample_handbook.pdf   # upload the sample PDF to Pinecone
python main.py                        # start chatting
```

Only `GOOGLE_API_KEY` is required to start. Every other agent switches on when its keys are present. The startup banner shows ✅ / ❌ for each one.

---

## 📖 Learn the code (read in this order)

| # | Document | You will learn |
|---|---|---|
| 0 | [docs/00_overview.md](docs/00_overview.md) | The big picture, the life of one message, a glossary |
| 1 | [docs/01_setup.md](docs/01_setup.md) | Getting every key: Gemini, Pinecone, GitHub, Google Cloud OAuth |
| 2 | [docs/02_python_syntax.md](docs/02_python_syntax.md) | Every Python feature used in this project, explained simply |
| 3 | [docs/03_utils_and_ui.md](docs/03_utils_and_ui.md) | `utils.py` and `ui.py`, line by line |
| 4 | [docs/04_rag_agent.md](docs/04_rag_agent.md) | `rag_core.py`, `ingest.py`, `rag_agent.py`: RAG with a hosted vector DB |
| 5 | [docs/05_agent_builder.md](docs/05_agent_builder.md) | `agent_builder.py`: the ReAct loop + human approval |
| 6 | [docs/06_mcp_agents.md](docs/06_mcp_agents.md) | `mcp_servers.py` + GitHub / Calendar / Gmail agents + `scheduler.py` |
| 7 | [docs/07_supervisor_and_main.md](docs/07_supervisor_and_main.md) | `supervisor.py` + `main.py`: routing, subgraphs, memory, the chat loop |
| 8 | [docs/08_try_it.md](docs/08_try_it.md) | Example prompts for every agent |
| 9 | [docs/09_troubleshooting.md](docs/09_troubleshooting.md) | Common errors and their fixes |
| 10 | [docs/10_exercises.md](docs/10_exercises.md) | Small tasks to practise and extend the project |

---

## 🗂️ Project structure

```
langraph-agent/
├── main.py             ▶ START HERE - the chat loop and /commands
├── supervisor.py       🧭 main graph: plans which agent(s) run, holds memory
├── agent_builder.py    🔁 builds every sub-agent: agent → approval → tools loop
│
├── rag_agent.py        📚 RAG sub-agent (search_pdf tool)
├── rag_core.py            PDF → chunks → Gemini embeddings → Pinecone
├── ingest.py              CLI: upload PDFs step by step
│
├── mcp_servers.py      🔌 connects to the 3 MCP servers, returns their tools
├── github_agent.py     🐙 GitHub sub-agent
├── calendar_agent.py   📅 Calendar sub-agent
├── gmail_agent.py      📧 Gmail sub-agent
├── scheduler.py        ⏰ schedule_email tool (APScheduler)
│
├── utils.py            🧠 picks the LLM + embeddings, small helpers
├── ui.py               🎨 all terminal output (rich): panels, icons, colours
│
├── data/sample_handbook.pdf   a small PDF to test the RAG agent
├── docs/               📖 the learning guide
├── .env.example        template for your keys
└── requirements.txt
```

## 🔗 How it relates to the course

| Course lecture (06_LangChain Langgraph) | Used here in |
|---|---|
| 02/03 nodes, edges, conditional edges | `supervisor.py`, `agent_builder.py` |
| 04 ReAct agent, `ToolNode`, `tools_condition` | `agent_builder.py` |
| 05 memory, `MemorySaver`, `thread_id` | `supervisor.py`, `main.py` |
| 06 human-in-the-loop | approval node in `agent_builder.py` |
| 07 RAG agent | `rag_core.py`, `rag_agent.py` (now with **Pinecone** instead of in-memory) |
| 08 MCP | `mcp_servers.py` (now **real** servers instead of a simulated one) |
| `utils.get_chat_model()` | `utils.py` (same Gemini → Groq priority) |
