# 01 · Setup: install + every key, step by step

> You only **need** step 1 + step 2 to start. Steps 3–5 each switch on one more agent.
> After every step you can run `python main.py` and see one more ✅ in the banner.

---

## Step 1 · Install

```powershell
cd D:\office\langraph-agent
python -m venv .venv                  # make a private Python just for this project
.\.venv\Scripts\Activate.ps1          # use it (your prompt now starts with (.venv))
pip install -r requirements.txt       # install every library listed in requirements.txt
copy .env.example .env                # your own settings file (git-ignored = never uploaded)
```

| Line                     | Why                                                                                                                                                          |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `python -m venv .venv`   | A **virtual environment** keeps this project's libraries separate from other projects, so versions never clash.                                              |
| `Activate.ps1`           | Makes `python` and `pip` point to `.venv`. Do this every time you open a new terminal. If PowerShell blocks it: `Set-ExecutionPolicy -Scope Process Bypass`. |
| `pip install -r ...`     | `-r` = "read the list from this file".                                                                                                                       |
| `copy .env.example .env` | `.env` holds your **secrets**. `.gitignore` lists `.env`, so git never uploads it.                                                                           |

> Python 3.11–3.13 is needed (3.14 is not yet supported by `langchain-pinecone`).

---

## Step 2 · 🧠 Gemini key (required, free)

1. Open <https://aistudio.google.com/apikey> and sign in with Google.
2. Click **Create API key** and copy it.
3. In `.env`: `GOOGLE_API_KEY=AIza...`

This one key gives us **both** the chat model (`gemini-3.8-flash`) **and** the embedding model used by RAG.

> **Free-tier limits:** the free tier allows a limited number of requests per minute. One message can use 3–6 requests (supervisor + agent + tool loop). If you see `429 RESOURCE_EXHAUSTED`, wait a minute and check your API quota.

---

## Step 3 · 📚 Pinecone key (RAG agent)

1. Sign up at <https://app.pinecone.io> (Starter plan = free).
2. Left menu → **API Keys** → **Create API key** → copy it.
3. In `.env`: `PINECONE_API_KEY=pcsk_...`
4. Upload the sample PDF:

```powershell
python ingest.py data\sample_handbook.pdf
```

You will see the 5 RAG steps printed (load → chunk → embed → upload → test search).
You **don't** create the index yourself. `rag_core.get_pinecone_index()` creates `smart-assistant-pdfs` (768 dimensions, cosine, AWS us-east-1) on the first run. Open the Pinecone website → **Indexes** to see your vectors.

---

## Step 4 · 🐙 GitHub token (GitHub agent)

1. Go to <https://github.com/settings/personal-access-tokens> → **Generate new token** (fine-grained).
2. Name: `smart-assistant`, Expiration: 30–90 days.
3. **Repository access:** _All repositories_ (or pick some).
4. **Permissions → Repository:** set **Contents**, **Issues**, **Pull requests**, **Metadata** to **Read-only**.
5. Generate → copy → in `.env`: `GITHUB_TOKEN=github_pat_...`

We connect to GitHub's **hosted** MCP server (`https://api.githubcopilot.com/mcp/`) in **read-only** mode, so no Docker or install is needed.

---

## Step 5 · 📅📧 Google Calendar + Gmail (one setup for both)

Google needs to know **which app** is asking for your calendar/mail. That "app identity" is an **OAuth client**. You create it once in Google Cloud. It takes about 10 minutes and is free.

### 5.1 Create a project and enable the APIs

1. Open <https://console.cloud.google.com/> → project picker (top left) → **New project** → name `smart-assistant` → **Create**.
2. Menu → **APIs & Services → Library** → search **Google Calendar API** → **Enable**.
3. Search **Gmail API** → **Enable**.

### 5.2 Consent screen (what you see when logging in)

1. **APIs & Services → OAuth consent screen** (or **Google Auth Platform → Branding**) → **Get started**.
2. App name: `Smart Assistant`, support email: your email → User type **External** → finish.
3. **Audience → Test users → Add users** → add **your own Gmail address**. (In "Testing" mode only listed users can log in.)

### 5.3 Create the OAuth client

1. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Application type: **Desktop app**, name: `smart-assistant-desktop` → **Create**.
3. Copy **Client ID** and **Client secret** into `.env`:

```env
GOOGLE_OAUTH_CLIENT_ID=1234567890-abc.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-...
USER_GOOGLE_EMAIL=you@gmail.com
USER_NAME=Hamad
```

### 5.4 First login (happens automatically)

1. `python main.py`. The **first** start downloads `workspace-mcp` with `uvx` (≈1 minute). After that it starts in seconds.
2. Ask: `What meetings do I have today?`
3. Your **browser opens** a Google login page. Choose your account.
4. Google warns _"Google hasn't verified this app"_. That's expected, because it is **your own** app in testing mode. Click **Continue**, tick the permissions, click **Continue**.
5. The page says _authentication successful_. Go back to the terminal and **ask again**.
6. Do the same once for Gmail (`Show my last 3 emails`).

The login tokens are saved in `.google_tokens/calendar/` and `.google_tokens/gmail/` (git-ignored). Calendar and Gmail have **separate** tokens because they are **separate MCP servers**.

> ⚠️ In "Testing" mode Google expires tokens after **7 days**. If an agent suddenly asks you to log in again, that's why: just log in again.

---

## Final check

```powershell
python main.py
```

```
╭──────────────────────────────────────────────╮
│ 🤖 Smart Assistant  -  LangGraph multi-agent │
│ 🧠 Brain: Gemini (gemini-3.8-flash)          │
╰──────────────────────────────────────────────╯
                      Agents
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Agent             ┃  Status  ┃ Details                                      ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 📚 RAG Agent      │ ✅ ready │ Pinecone index 'smart-assistant-pdfs': 2 chunks │
│ 🐙 GitHub Agent   │ ✅ ready │ 25 MCP tools                                 │
│ 📅 Calendar Agent │ ✅ ready │ 4 MCP tools                                  │
│ 📧 Gmail Agent    │ ✅ ready │ 7 MCP tools                                  │
└───────────────────┴──────────┴──────────────────────────────────────────────┘
```

(Your tool and chunk counts may be different.) Something ❌? See [09_troubleshooting.md](09_troubleshooting.md).
