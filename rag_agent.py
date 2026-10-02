"""
rag_agent.py - 📚 the RAG sub-agent: answers questions from your PDFs in Pinecone.

"Agentic RAG" (same idea as your study-buddy project):
    Retrieval is a TOOL. The LLM DECIDES when to search and with which words.
    It may search twice with different words if the first result is not enough.

The PDFs are indexed beforehand by ingest.py (or the /upload command in main.py).
"""

from langchain_core.tools import tool

from agent_builder import build_tool_agent
from rag_core import format_docs, get_vector_store

SYSTEM_PROMPT = (
    "You are the RAG Agent. You answer questions using ONLY the user's PDF documents. "
    "ALWAYS call the search_pdf tool first. You may call it again with different words "
    "if the first result does not answer the question. "
    "If the documents do not contain the answer, say: "
    "\"I couldn't find that in your documents.\" Never invent facts. "
    "End your answer with the sources, e.g. (source: handbook.pdf, page 3). "
    "Use short paragraphs or bullet points."
)

# Created the first time the tool runs ("lazy"), so importing this file is fast
# and does not need the internet.
_retriever = None


# @tool turns a normal function into a LangChain tool.
# The function NAME, the TYPE HINTS and the DOCSTRING are sent to the LLM - that is
# how it knows what the tool does and what to pass in. The docstring is a prompt!
@tool
def search_pdf(query: str) -> str:
    """Search the user's PDF documents stored in the Pinecone vector database.
    Input: a short search query with the key terms, e.g. 'leave policy for new employees'.
    Returns the most relevant text chunks with their file name and page number."""
    global _retriever  # `global` lets us assign to the module-level variable above
    if _retriever is None:
        # k=4 -> return the 4 most similar chunks.
        _retriever = get_vector_store().as_retriever(search_kwargs={"k": 4})

    docs = _retriever.invoke(query)
    if not docs:
        return "No matching text found. (Is any PDF uploaded? Use /upload <file.pdf>)"
    return format_docs(docs)


def build_rag_agent():
    """Returns the compiled RAG sub-agent graph."""
    # search_pdf only READS, so nothing needs human approval.
    return build_tool_agent("rag", [search_pdf], SYSTEM_PROMPT)
