# 08 · ▶ Try it: example prompts for every agent

Start with `python main.py`. Watch the `🧭` line (which agent?) and the `🔧` lines (which tools, with which arguments?). That's where you learn the most.

## 💬 Chat
```
hi
what can you do?
```

## 📚 RAG (after `python ingest.py data\sample_handbook.pdf`)
```
What is the attendance policy in my handbook?
What happens if I submit an assignment 2 days late?
How is the final grade calculated?
And what grade do I need for an A?            ← follow-up: uses memory
Who is the principal of the academy?          ← not in the PDF → "I couldn't find that"
/upload C:\Users\me\Documents\any.pdf         ← add your own PDF
```

## 🐙 GitHub
```
Who am I on GitHub?
List my repositories
Summarize the README of danishmustafa86/Agentic_AI_B02_SMIT
What files are in hamadzia74/study-buddy-rag-agent?
Show the open issues in langchain-ai/langgraph
What were the last 5 commits in hamadzia74/study-buddy-rag-agent?
```

## 📅 Calendar
```
What meetings do I have today?
Am I free tomorrow between 2pm and 5pm?
Create a meeting "Project sync" tomorrow at 3pm for 45 minutes with ali@example.com and a Google Meet link
Move my Project sync meeting to 4pm
Cancel the Project sync meeting                ← approval asked (manage_event)
```

## 📧 Gmail
```
Show my last 5 unread emails
Find emails from github in the last 2 days
Draft an email to sara@example.com asking for the assignment deadline   ← draft, no approval
Send it                                         ← follow-up: approval asked
Send an email to sara@example.com saying thanks for the help, send it tomorrow at 9am
/jobs                                           ← see the scheduled email
Send a test email to myself in 2 minutes        ← watch it fire while the app is open
```

## 🧭 Multi-agent (two agents in one request)
```
Book a 30 minute Google Meet with ali@example.com tomorrow at 11am and email him the agenda: 1) progress 2) blockers
Read my handbook's grading policy and email a short summary to sara@example.com
```
Watch the supervisor plan two steps, e.g. `📅 Calendar Agent` then `📧 Gmail Agent`. The second agent can read the first agent's answer (the Meet link, the summary).

## 🔍 See the graph
```
/graph
```
Paste the output at <https://mermaid.live>.
