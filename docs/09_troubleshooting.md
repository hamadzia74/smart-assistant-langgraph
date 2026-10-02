# 09 · 🛠️ Troubleshooting

**First rule:** read the ❌ message. Then, for MCP agents, open `logs/github.log`, `logs/calendar.log` or `logs/gmail.log` (stdio servers write their own logs there).

| Symptom | Cause | Fix |
|---|---|---|
| `❌ No LLM key` at start | `.env` missing or key still `your_...` | `copy .env.example .env`, paste `GOOGLE_API_KEY`. |
| `429 RESOURCE_EXHAUSTED` / `quota` | Gemini free tier: too many requests per minute | Wait 1 minute. Or `GEMINI_MODEL=gemini-2.5-flash-lite` in `.env`. |
| `Activate.ps1 cannot be loaded` | PowerShell script policy | `Set-ExecutionPolicy -Scope Process Bypass`, then activate again. |
| `ModuleNotFoundError` | venv not active, or packages not installed | `.\.venv\Scripts\Activate.ps1` then `pip install -r requirements.txt`. |
| 📚 `Pinecone error: ... Unauthorized` | Wrong `PINECONE_API_KEY` | Copy the key again from app.pinecone.io → API Keys. |
| 📚 `Vector dimension 3072 does not match the dimension of the index 768` | You changed `EMBEDDING_DIM` or the model | Delete the index on the Pinecone website (or set a new `PINECONE_INDEX_NAME`) and re-ingest. |
| 📚 "I couldn't find that" but it **is** in the PDF | Scanned PDF (image only), or the question uses very different words | Check the `📥` preview. Scanned PDFs need OCR first. Try rephrasing; raise `k` in `rag_agent.py`. |
| 📚 Banner shows `0 chunks` right after ingest | Pinecone counts update a few seconds later | Restart the app after ~10 s. Search works immediately anyway. |
| 🐙 `could not connect: ...` | Token wrong/expired, or no internet | Make a new token ([setup step 4](01_setup.md)). Check that `GITHUB_TOKEN` has no spaces or quotes. |
| 🐙 "Resource not accessible" / 404 on a private repo | Fine-grained token has no access to that repo | Edit the token → Repository access → add the repo. |
| 📅📧 `could not connect` on the very first start | `uvx` still downloading, or `uvx` not found | Wait and restart. Check that `.venv\Scripts\uvx.exe` exists (`pip install uv`). Look at `logs/calendar.log`. |
| 📅📧 "ACTION REQUIRED: Google Authentication Needed" | First login, or the 7-day test token expired | Open the link (or the browser tab that opened), approve, then ask again. |
| 📅📧 Google page: `Error 403: access_denied` | Your email isn't a **test user** | Cloud Console → OAuth consent screen → Audience → **Test users** → add your Gmail. |
| 📅📧 Google page: `redirect_uri_mismatch` | OAuth client type is "Web application" | Create a **Desktop app** OAuth client and use its id/secret. |
| 📅📧 `Gmail API has not been used in project ...` | API not enabled | Cloud Console → Library → enable **Gmail API** / **Google Calendar API**. |
| 📅 Meeting created at the wrong hour | Time-zone confusion | Check the `🔧 manage_event` arguments: the time must end with your offset, e.g. `+05:00`. Your Windows time zone must be correct. |
| 📧 Scheduled email never arrived | The app was closed before the time | Scheduled jobs live in memory. Keep the app running (`/jobs` shows pending ones). |
| `port 8001/8002 already in use` in a log | Another copy of the app is running | Close the other terminal running `main.py`. |
| Agent keeps calling tools and stops with `recursion limit` | It is confused by a vague request | Be more specific ("in repo owner/name", "on Friday 3 Oct at 15:00"). |

## Reset everything

```powershell
Remove-Item -Recurse -Force .google_tokens   # forget Google logins
Remove-Item -Recurse -Force logs             # clear logs
```
Delete the index on the Pinecone website to clear all PDFs.
