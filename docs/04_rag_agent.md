# 04 · 📚 The RAG agent: PDFs in a hosted vector database

Files: `rag_core.py` (the pipeline), `ingest.py` (upload step by step), `rag_agent.py` (the agent).

## The idea in one picture

```
INDEXING (once per PDF)                         QUERYING (every question)
─────────────────────────                       ─────────────────────────
PDF ─▶ pages ─▶ chunks ─▶ 768 numbers each      question ─▶ 768 numbers
             PyPDFLoader   splitter   Gemini                    │ Gemini
                                     │                          ▼
                                     └──▶  ☁️ Pinecone  ◀── "find the 4 closest vectors"
                                                                │
                                                                ▼
                                          4 chunks + question ─▶ LLM ─▶ answer + (source, page)
```

**Why RAG?** The LLM has never seen *your* PDF. Pasting the whole PDF into every prompt is slow and expensive (and often too long). RAG finds just the **few relevant pieces** and gives only those to the LLM.

**Why a *hosted* vector DB?** Your study-buddy project used Chroma, which saves to a folder **on your laptop**. Pinecone lives **in the cloud**: index once, then search from any computer, a teammate's laptop or a deployed server.

---

# Part A · `rag_core.py`

## A1. Settings

```python
INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "smart-assistant-pdfs")
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
```

* 🎯 The Pinecone index name and the chunk sizes.
* 💡 An **index** in Pinecone is like a table in a normal database. 1000 characters ≈ 200 words ≈ one or two paragraphs: big enough to hold a complete idea, small enough to be precise. The **overlap** repeats 150 characters between neighbours, so a sentence cut at a boundary still appears complete in one chunk.

## A2. `get_pinecone_index`: connect, create once

```python
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

if not pc.has_index(INDEX_NAME):
    pc.create_index(
        name=INDEX_NAME,
        dimension=EMBEDDING_DIM,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
    while not pc.describe_index(INDEX_NAME).status["ready"]:
        time.sleep(1)

return pc.Index(INDEX_NAME)
```

* 🎯 Connects to your Pinecone account. On the very first run it **creates** the index, waits until it's ready, then returns a handle to it.
* 💡 Settings:
  * `dimension` must equal the embedding size (768), or Pinecone rejects the vectors.
  * `metric="cosine"` compares the **angle** between vectors, the standard measure for text meaning.
  * `ServerlessSpec(cloud="aws", region="us-east-1")`: the free Starter plan only allows this location.
* 💡 The `while` loop is needed because a brand-new index takes a few seconds before it accepts data.
* 🔤 `while not X: time.sleep(1)` = "check every second until X is true".

## A3. `get_vector_store`: the LangChain wrapper

```python
return PineconeVectorStore(index=get_pinecone_index(), embedding=get_embeddings())
```

* 🎯 Wraps the raw index in LangChain's standard vector-store interface.
* 💡 Now we can use the **same** methods as with Chroma or InMemoryVectorStore (`add_documents`, `similarity_search`, `as_retriever`). We pass the embedding model, so the store embeds texts **for us**: when adding chunks *and* when searching with a question.

## A4. `load_pdf`: Step 1, LOAD

```python
pages = PyPDFLoader(str(path)).load()
for doc in pages:
    doc.metadata = {"source": path.name, "page": doc.metadata.get("page", 0) + 1}
return [doc for doc in pages if doc.page_content.strip()]
```

* 🎯 Reads the PDF into a list of `Document`s, **one per page**.
* 💡 Steps:
  * `PyPDFLoader` uses the `pypdf` library to pull out the text.
  * We **replace** the metadata with just `source` + `page`, because those two are what we need for citations ("handbook.pdf, page 3"). `+ 1` because the loader counts pages from 0, but humans count from 1.
  * Pages with no text are dropped. Scanned PDFs are just images and have no text layer, so they would give empty chunks.
* 🔤 `str(path)` because the loader wants a string, not a `Path`. `.strip()` removes spaces/newlines; an empty string counts as False.

## A5. `split_documents`: Step 2, CHUNK

```python
splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)
return splitter.split_documents(documents)
```

* 🎯 Cuts each page into chunks of at most 1000 characters.
* 💡 "Recursive" means it tries the separators **in order**: paragraph break, then line break, then sentence end, then space, then anywhere. So it always cuts at the most natural place possible. Each chunk **inherits** its page's metadata, so we still know the page number after splitting.

## A6. `ingest_pdf`: Steps 3 + 4, EMBED + UPLOAD

```python
chunks = split_documents(load_pdf(path))
...
for id_batch in index.list(prefix=f"{path.name}#"):
    index.delete(ids=id_batch)

ids = []
chunk_number_on_page: dict[int, int] = {}
for chunk in chunks:
    page = chunk.metadata["page"]
    n = chunk_number_on_page.get(page, 0)
    chunk_number_on_page[page] = n + 1
    ids.append(f"{path.name}#p{page}#c{n}")

store.add_documents(chunks, ids=ids)
```

* 🎯 Uploads all chunks of one PDF. Each gets a readable **id** like `sample_handbook.pdf#p2#c0` (file, page 2, first chunk on that page).
* 💡 **Why delete first?** If you upload the same PDF twice (maybe after editing it), the old chunks are removed first, so there are no duplicates and no stale text. Because every id starts with the file name, `index.list(prefix="sample_handbook.pdf#")` finds exactly that file's chunks.
* 💡 `add_documents` does **two** things: it calls Gemini to embed every chunk (in batches), then sends the vectors + text + metadata to Pinecone.
* 🔤 `chunk_number_on_page` is a dict used as a **counter** per page. `.get(page, 0)` gives 0 the first time a page is seen.

## A7. `format_docs`: chunks → text for the LLM

```python
return "\n\n".join(
    f"[source: {d.metadata.get('source', '?')}, page {int(d.metadata.get('page', 0))}]\n{d.page_content}"
    for d in docs
)
```

* 🎯 Joins the found chunks into one string, each one labelled with its source and page.
* 💡 The LLM only reads text. The `[source: ..., page ...]` label is **what makes citations possible**: the LLM copies it into its answer.
* 🔤 `int(...)` because Pinecone stores numbers as floats (`2.0`), and "page 2" reads better. `"\n\n".join(...)` puts a blank line between chunks.

---

# Part B · `ingest.py`: watch the pipeline

```powershell
python ingest.py data\sample_handbook.pdf
```

```
──────────────────── 📄 sample_handbook.pdf ────────────────────
ℹ️  Step 1 LOAD   : 2 pages with text
ℹ️  Step 2 CHUNK  : 2 chunks (about 1.0 per page)
ℹ️  Step 3 EMBED  : each chunk -> 768 numbers (EMBEDDING_DIM=768)
   first 5 numbers: [0.0123, -0.0456, ...]
✅ Step 4 UPLOAD : 2 chunks stored in Pinecone index 'smart-assistant-pdfs'
──────────────────────── 🔎 Test search ────────────────────────
```

* 🎯 Runs each step separately and **prints what's inside**, so you can see a real vector.
* 💡 Same idea as the numbered lesson files in your study-buddy repo. In the chat, `/upload <file.pdf>` calls the same `ingest_pdf` (without the explanations).
* 🔤 `sys.argv` is the list of words typed in the command: `["ingest.py", "data\\sample_handbook.pdf"]`. `sys.argv[1:]` = everything after the script name, so you can pass several PDFs.

---

# Part C · `rag_agent.py`: retrieval as a tool

## C1. The system prompt

```python
SYSTEM_PROMPT = (
    "You are the RAG Agent. You answer questions using ONLY the user's PDF documents. "
    "ALWAYS call the search_pdf tool first. ..."
    "If the documents do not contain the answer, say: \"I couldn't find that in your documents.\" "
    "End your answer with the sources, e.g. (source: handbook.pdf, page 3). "
)
```

* 💡 The three rules that make RAG **trustworthy**:
  1. Always search first.
  2. Only answer from what was found, and say "not found" otherwise, so it doesn't **hallucinate**.
  3. Cite the source.
* 🔤 Strings next to each other inside `( )` are joined automatically. That's an easy way to write a long text over several lines.

## C2. The `search_pdf` tool

```python
_retriever = None

@tool
def search_pdf(query: str) -> str:
    """Search the user's PDF documents stored in the Pinecone vector database. ..."""
    global _retriever
    if _retriever is None:
        _retriever = get_vector_store().as_retriever(search_kwargs={"k": 4})
    docs = _retriever.invoke(query)
    if not docs:
        return "No matching text found. (Is any PDF uploaded? Use /upload <file.pdf>)"
    return format_docs(docs)
```

* 🎯 The only tool of this agent: search Pinecone, return the 4 best chunks as labelled text.
* 💡 This is **Agentic RAG**: the LLM **decides** the search words, and may search again with different words. A plain RAG *chain* always searches exactly once with the raw question.
* 💡 The retriever is created **lazily** (on first use), so starting the app doesn't hit Pinecone twice.
* 💡 The empty-result message tells the LLM (and you) what to do next.
* 🔤 `as_retriever(search_kwargs={"k": 4})` gives an object with `.invoke(question) → list of Documents`. See [doc 02 §8](02_python_syntax.md) for `@tool` and §10 for `global`.

## C3. Building the agent

```python
def build_rag_agent():
    return build_tool_agent("rag", [search_pdf], SYSTEM_PROMPT)
```

* 🎯 One line! All graph logic (agent → tools loop) lives in `agent_builder.py` ([doc 05](05_agent_builder.md)).
* 💡 No `sensitive_tools`: searching only **reads**, so it never needs approval.

---

### ✏️ Try it

```
👤 You › What happens if I submit an assignment 2 days late?
🧭 Supervisor → 📚 RAG Agent (question about uploaded handbook)
   🔧 search_pdf {"query": "late assignment submission penalty"}
   📥 [source: sample_handbook.pdf, page 1] Nova Learning Academy - Student Handbook 2026 ...
┌─ 📚 RAG Agent ───────────────────────────────────────────────┐
│ You lose 10% of the marks per day, so 2 days late = 20% off. │
│ (source: sample_handbook.pdf, page 1)                        │
└──────────────────────────────────────────────────────────────┘
```
