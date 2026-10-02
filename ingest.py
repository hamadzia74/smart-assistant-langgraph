"""
ingest.py - upload PDFs into Pinecone, STEP BY STEP, printing what happens inside.

Run:
    python ingest.py data/sample_handbook.pdf
    python ingest.py "C:\\Users\\me\\Documents\\any file.pdf"  other.pdf

Run this once per PDF. After that the RAG agent can answer questions about it,
from any computer, because the vectors live in the cloud (Pinecone).
(Inside the chat you can do the same with: /upload <file.pdf>)
"""

import sys
from pathlib import Path

import ui
from rag_core import INDEX_NAME, count_chunks, format_docs, get_vector_store, ingest_pdf, load_pdf, split_documents
from utils import EMBEDDING_DIM, get_embeddings


def explain(path: Path) -> None:
    """Shows each RAG indexing step on one PDF, then uploads it."""
    ui.section(f"📄 {path.name}")

    # Step 1: LOAD
    pages = load_pdf(path)
    ui.info(f"Step 1 LOAD   : {len(pages)} pages with text")
    ui.console.print(f"   [dim]page 1 starts with: {pages[0].page_content[:120]!r}[/dim]")

    # Step 2: CHUNK
    chunks = split_documents(pages)
    ui.info(f"Step 2 CHUNK  : {len(chunks)} chunks (about {len(chunks) / len(pages):.1f} per page)")
    ui.console.print(f"   [dim]first chunk metadata: {chunks[0].metadata}[/dim]")

    # Step 3: EMBED (demo on one chunk, so you can SEE a vector)
    vector = get_embeddings().embed_query(chunks[0].page_content)
    ui.info(f"Step 3 EMBED  : each chunk -> {len(vector)} numbers (EMBEDDING_DIM={EMBEDDING_DIM})")
    ui.console.print(f"   [dim]first 5 numbers: {[round(x, 4) for x in vector[:5]]}[/dim]")

    # Step 4: UPLOAD (ingest_pdf repeats steps 1-3 for every chunk and uploads)
    with ui.console.status("[dim]📤 embedding + uploading all chunks...[/dim]"):
        count = ingest_pdf(path)
    ui.success(f"Step 4 UPLOAD : {count} chunks stored in Pinecone index '{INDEX_NAME}'")


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]]   # sys.argv = the words typed after "python"
    if not paths:
        ui.warn("Usage: python ingest.py <file.pdf> [more.pdf ...]")
        return

    for path in paths:
        try:
            explain(path)
        except Exception as e:
            ui.error(f"{path}: {e}")

    # Step 5: TEST - search the index once, like the RAG agent will.
    ui.section("🔎 Test search")
    query = "What is this document about?"
    docs = get_vector_store().similarity_search(query, k=2)
    ui.info(f"Query: {query!r} -> {len(docs)} chunks found")
    ui.console.print(f"[dim]{format_docs(docs)[:600]}[/dim]")
    # Pinecone is "eventually consistent": brand-new vectors can take a few seconds
    # to be counted, so this number may lag behind for a moment.
    ui.info(f"Index '{INDEX_NAME}' now reports {count_chunks()} chunks in total.")


if __name__ == "__main__":
    main()
