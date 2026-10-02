"""
rag_core.py - the RAG pipeline for PDFs, stored in a HOSTED vector database (Pinecone).

    RAG has two phases:

    INDEXING (once per PDF, run by ingest.py or the /upload command):
        load_pdf()  ->  split_documents()  ->  embed + upload to Pinecone
        [PDF -> one Document per page]  [pages -> small chunks]  [chunks -> vectors in the cloud]

    QUERYING (for every question, used by rag_agent.py):
        question -> embed it -> Pinecone finds the most similar chunks -> LLM answers from them

WHY Pinecone instead of Chroma (your study-buddy project) or InMemoryVectorStore (lecture 07)?
    InMemoryVectorStore -> lives in RAM, gone when the program stops.
    Chroma              -> saved in a folder on YOUR laptop only.
    Pinecone            -> a database in the cloud ("hosted"). Index a PDF once from
                           any computer, and every computer / teammate / deployed app
                           can search it. That is what real products do.
"""

import os
import time
from pathlib import Path
from typing import List

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_pinecone import PineconeVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pinecone import Pinecone, ServerlessSpec

from utils import EMBEDDING_DIM, get_embeddings, has_key

# The index name is read from .env, with a sensible default.
# An "index" in Pinecone is like a table in a normal database.
INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "smart-assistant-pdfs")

# chunk_size is in CHARACTERS (about 200-250 words). A PDF page is usually
# 2000-4000 characters, so each page becomes 2-4 chunks.
CHUNK_SIZE = 1000
# The last 150 characters of a chunk are repeated at the start of the next one,
# so a sentence cut at the boundary still appears complete in one chunk.
CHUNK_OVERLAP = 150


# ------------------------------------------------------------
# Connect to Pinecone (and create the index the first time)
# ------------------------------------------------------------
def get_pinecone_index():
    """
    Returns a handle to our Pinecone index. Creates the index if it does not exist.

    dimension -> how many numbers each vector has. MUST equal EMBEDDING_DIM,
                 otherwise Pinecone rejects the vectors.
    metric    -> how "similar" is measured. cosine = compare the ANGLE of two
                 vectors, the standard choice for text embeddings.
    ServerlessSpec(cloud="aws", region="us-east-1") -> the free Starter plan
                 only allows this cloud + region.
    """
    if not has_key("PINECONE_API_KEY"):
        raise RuntimeError("PINECONE_API_KEY is missing in .env")

    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

    if not pc.has_index(INDEX_NAME):
        pc.create_index(
            name=INDEX_NAME,
            dimension=EMBEDDING_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        # A new index needs a few seconds before it accepts data.
        while not pc.describe_index(INDEX_NAME).status["ready"]:
            time.sleep(1)

    return pc.Index(INDEX_NAME)


def get_vector_store() -> PineconeVectorStore:
    """
    Wraps the raw Pinecone index in LangChain's PineconeVectorStore.

    The wrapper gives us the SAME methods as every other LangChain vector store:
    add_documents(), similarity_search(), as_retriever() ...
    The embedding model is passed in, so the store embeds texts for us automatically.
    """
    return PineconeVectorStore(index=get_pinecone_index(), embedding=get_embeddings())


def count_chunks() -> int:
    """How many chunks (vectors) are stored in the index. Shown in the startup banner."""
    stats = get_pinecone_index().describe_index_stats()
    return stats.total_vector_count


# ------------------------------------------------------------
# Step 1: LOAD - PDF file -> one Document per page
# ------------------------------------------------------------
def load_pdf(path: Path) -> List[Document]:
    """
    PyPDFLoader reads the PDF with the `pypdf` library and returns a list:
    one Document per page.
        page_content -> the text on that page
        metadata     -> {"source": "...", "page": 0, ...}   (page starts at 0!)

    We overwrite the metadata with clean values so citations look nice:
        {"source": "handbook.pdf", "page": 1}               (page starts at 1)
    """
    pages = PyPDFLoader(str(path)).load()
    for doc in pages:
        doc.metadata = {"source": path.name, "page": doc.metadata.get("page", 0) + 1}
    # Scanned PDFs (photos of paper) have no text layer -> empty pages. Drop them.
    return [doc for doc in pages if doc.page_content.strip()]


# ------------------------------------------------------------
# Step 2: CHUNK - split pages into smaller pieces
# ------------------------------------------------------------
def split_documents(documents: List[Document]) -> List[Document]:
    """
    WHY split? One vector for a whole page is a blurry average of many topics.
    Smaller chunks give sharper matches, and we only send the best few to the LLM.

    RecursiveCharacterTextSplitter tries separators IN ORDER: paragraphs ("\\n\\n"),
    then lines ("\\n"), then sentences (". "), then words (" "). So it cuts at the
    most natural place that still keeps each chunk under CHUNK_SIZE.
    Every chunk keeps its page's metadata (source + page number).
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_documents(documents)


# ------------------------------------------------------------
# Steps 3 + 4: EMBED + UPLOAD to Pinecone
# ------------------------------------------------------------
def ingest_pdf(path: str | Path) -> int:
    """
    Indexes one PDF into Pinecone and returns how many chunks were uploaded.

    Re-uploading the same PDF is safe: every chunk id starts with the file name
    ("handbook.pdf#..."), so we first delete the old chunks of that file, then
    upload the new ones. No duplicates.
    """
    path = Path(path)
    if not path.exists() or path.suffix.lower() != ".pdf":
        raise FileNotFoundError(f"Not a PDF file: {path}")

    chunks = split_documents(load_pdf(path))
    if not chunks:
        raise ValueError("No text found in this PDF (is it a scanned image?)")

    store = get_vector_store()
    index = get_pinecone_index()

    # 1) Remove old chunks of this file. index.list(prefix=...) yields pages of ids.
    for id_batch in index.list(prefix=f"{path.name}#"):
        index.delete(ids=id_batch)

    # 2) Give each chunk a stable, readable id: "handbook.pdf#p3#c0"
    ids = []
    chunk_number_on_page: dict[int, int] = {}
    for chunk in chunks:
        page = chunk.metadata["page"]
        n = chunk_number_on_page.get(page, 0)
        chunk_number_on_page[page] = n + 1
        ids.append(f"{path.name}#p{page}#c{n}")

    # 3) add_documents embeds every chunk (Gemini) and uploads the vectors (Pinecone).
    store.add_documents(chunks, ids=ids)
    return len(chunks)


# ------------------------------------------------------------
# Helper: turn retrieved chunks into text the LLM can read
# ------------------------------------------------------------
def format_docs(docs: List[Document]) -> str:
    """
    The LLM only reads text, so we join the chunks into one string.
    Each chunk gets a label like [source: handbook.pdf, page 3] - that label is
    what lets the LLM CITE where the answer came from.
    """
    return "\n\n".join(
        f"[source: {d.metadata.get('source', '?')}, page {int(d.metadata.get('page', 0))}]\n{d.page_content}"
        for d in docs
    )
