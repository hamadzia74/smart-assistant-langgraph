"""
utils.py - small helpers that EVERY other file uses.

Same idea as utils.py in the course repo (lecture 06_LangChain Langgraph):
    Chat model priority:   1. Google Gemini   2. Groq
    Embedding model:       Google Gemini (Pinecone needs real embeddings)

WHY keep this in one file?
    The rest of the project never talks to "Gemini" or "Groq" directly. It only
    talks to LangChain's common interfaces (BaseChatModel / Embeddings).
    So if you want to switch provider, you change THIS file only.
"""

import os
import sys

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

# load_dotenv() reads the .env file and copies every KEY=value line into
# environment variables, so os.getenv("KEY") can read them anywhere.
load_dotenv()

# Windows terminals sometimes crash on emojis / special characters.
# reconfigure(encoding="utf-8") tells Python to print using UTF-8.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def has_key(name: str) -> bool:
    """
    True if the env var is set to a REAL value.

    .env.example uses placeholders like "your_google_api_key_here".
    A placeholder is not a real key, so we treat it as "missing".
    """
    value = os.getenv(name, "")
    return bool(value) and not value.startswith("your_")


# ============================================================
# 1. CHAT MODEL  (the "brain" that reads, decides and writes)
# ============================================================
def get_chat_model(temperature: float = 0.0) -> BaseChatModel:
    """
    Returns the best available chat model.

    temperature=0 -> predictable, factual answers. Agents that call tools
    should be precise (correct email address, correct date), not creative.
    """
    if has_key("GOOGLE_API_KEY"):
        # Import INSIDE the if: the package is only needed when this branch runs.
        from langchain_google_genai import ChatGoogleGenerativeAI

        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        return ChatGoogleGenerativeAI(model=model, temperature=temperature)

    if has_key("GROQ_API_KEY"):
        from langchain_groq import ChatGroq

        model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        return ChatGroq(model=model, temperature=temperature)

    # Unlike the course repo we do NOT fall back to a Mock LLM: GitHub, Calendar
    # and Gmail are real services, so a fake brain cannot do anything useful.
    raise RuntimeError(
        "No LLM key found. Put GOOGLE_API_KEY (or GROQ_API_KEY) in your .env file."
    )


def chat_model_name() -> str:
    """A friendly label for the startup banner, e.g. 'Gemini (gemini-2.5-flash)'."""
    if has_key("GOOGLE_API_KEY"):
        return f"Gemini ({os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')})"
    if has_key("GROQ_API_KEY"):
        return f"Groq ({os.getenv('GROQ_MODEL', 'openai/gpt-oss-120b')})"
    return "none"


# ============================================================
# 2. EMBEDDINGS  (text -> list of numbers, used by the RAG agent)
# ============================================================
# Gemini's embedding model can return vectors of different sizes.
# 768 numbers is plenty for PDFs and uses 4x less Pinecone storage than 3072.
# IMPORTANT: the Pinecone index must be created with the SAME dimension.
EMBEDDING_DIM = 768


def get_embeddings() -> Embeddings:
    """Returns the Gemini embedding model (needs GOOGLE_API_KEY)."""
    if not has_key("GOOGLE_API_KEY"):
        raise RuntimeError("The RAG agent needs GOOGLE_API_KEY for Gemini embeddings.")

    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        output_dimensionality=EMBEDDING_DIM,
    )


# ============================================================
# 3. MESSAGE HELPER
# ============================================================
def message_text(message) -> str:
    """
    Returns the plain text of a message.

    Most models return content as a string: "Hello".
    Gemini sometimes returns a LIST of parts: [{"type": "text", "text": "Hello"}].
    This helper turns both shapes into a normal string.
    """
    content = message.content
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        if isinstance(part, dict):
            parts.append(part.get("text", ""))
        else:
            parts.append(str(part))
    return "".join(parts)
