"""
scheduler.py - "send this email tomorrow at 9am".

The Gmail API has NO "schedule send" feature (the button in the Gmail website is
not available to apps). So we build it ourselves with APScheduler, a library that
runs a function at a given date/time - like an alarm clock for Python code.

How it works:
    1. The Gmail agent calls our schedule_email tool with a time.
    2. We add a "job" to the scheduler: "at 09:00 run send_now(...)".
    3. At 09:00 the scheduler runs send_now(), which calls the Gmail MCP
       server's send_gmail_message tool - the same tool used for "send now".

LIMITATION (important!): jobs live in this program's memory. If you close the app
before the time comes, the email is NOT sent. Use /jobs to see what is waiting.
"""

import os
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from langchain_core.tools import BaseTool, tool

import ui

# AsyncIOScheduler runs jobs inside our asyncio event loop - the same loop that
# keeps the MCP connections open, so a job can use the Gmail MCP tool directly.
scheduler = AsyncIOScheduler()


def start() -> None:
    """Must be called from inside a running event loop (main.py does this)."""
    if not scheduler.running:
        scheduler.start()


def list_jobs() -> list[tuple[str, str]]:
    """Returns [(time, description), ...] for the /jobs command."""
    return [(f"{job.next_run_time:%a %d %b %H:%M}", job.name) for job in scheduler.get_jobs()]


def make_schedule_email_tool(send_tool: BaseTool) -> BaseTool:
    """
    Creates the schedule_email tool.

    WHY a function that RETURNS a tool ("factory")?
    The tool needs the Gmail MCP send tool, which only exists after we connect to
    the server. The inner function "remembers" send_tool from the outer function -
    this is called a CLOSURE.
    """

    async def send_now(to: str, subject: str, body: str) -> None:
        """The job that runs at the scheduled time."""
        try:
            await send_tool.ainvoke({
                "user_google_email": os.getenv("USER_GOOGLE_EMAIL", ""),
                "to": to,
                "subject": subject,
                "body": body,
            })
            ui.success(f"📧 Scheduled email sent to {to}: {subject}")
        except Exception as e:
            ui.error(f"Scheduled email to {to} failed: {e}")

    @tool
    def schedule_email(to: str, subject: str, body: str, send_at: str) -> str:
        """Schedule an email to be sent automatically at a future time.
        send_at must be an ISO 8601 datetime with UTC offset, e.g. 2026-10-03T09:00:00+05:00.
        Only works while this app keeps running."""
        try:
            when = datetime.fromisoformat(send_at)
        except ValueError:
            return "Error: send_at must look like 2026-10-03T09:00:00+05:00"

        # A time without an offset ("naive") is treated as the computer's local time.
        if when.tzinfo is None:
            when = when.astimezone()
        if when <= datetime.now().astimezone():
            return "Error: that time is in the past. Ask the user for a future time."

        scheduler.add_job(
            send_now,
            trigger="date",              # run ONCE at a specific date/time
            run_date=when,
            args=[to, subject, body],
            name=f"to {to}: {subject}",
        )
        return f"Scheduled: the email to {to} will be sent at {when:%A %d %B %Y %H:%M}."

    return schedule_email
