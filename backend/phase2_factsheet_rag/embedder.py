import logging
import os
import chromadb
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Directory for ChromaDB persistence
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")

# Load local embedding model (runs on CPU/GPU)
# all-MiniLM-L6-v2 is fast, compact (~80MB), and produces 384-dimensional embeddings.
print("[Embedder] Loading local embedding model (all-MiniLM-L6-v2)...")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

def get_chroma_client():
    """Get or create a persistent ChromaDB client."""
    return chromadb.PersistentClient(path=CHROMA_DIR)


def build_chunks(factsheet_records: list, definition_records: list) -> list[dict]:
    """
    Convert scraped records into retrievable chunks with metadata.
    
    Factsheet records → one chunk per field per scheme (14 fields × N schemes)
    Definition records → one chunk per definition
    """
    chunks = []
    
    # Factsheet chunks: per-field chunking
    for record in factsheet_records:
        if record is None:
            continue
        scheme_name = record["scheme_name"]
        source_url = record["source_url"]
        scraped_at = record["scraped_at"]
        
        for field_name, field_value in record["fields"].items():
            chunk_text = f"{scheme_name} - {field_name}: {field_value}"
            chunks.append({
                "id": f"fs_{scheme_name}_{field_name}".replace(" ", "_").lower(),
                "text": chunk_text,
                "metadata": {
                    "scheme_name": scheme_name,
                    "field": field_name,
                    "value": field_value,
                    "source_url": source_url,
                    "scraped_at": scraped_at,
                    "kind": "factsheet_field",
                },
            })
    
    # Definition chunks: one per definition
    for record in definition_records:
        if record is None:
            continue
        term = record["term"]
        chunks.append({
            "id": f"def_{term}".replace(" ", "_").lower(),
            "text": f"{term}: {record['text']}",
            "metadata": {
                "term": term,
                "source_url": record["source_url"],
                "scraped_at": record["scraped_at"],
                "kind": "definition",
            },
        })
    
    return chunks


def embed_texts(texts: list[str], api_key: str = None) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts using local SentenceTransformer.
    
    This runs entirely on your local machine, avoiding all API rate limits.
    """
    if not texts:
        return []
    
    print(f"  [Embedder] Generating local embeddings for {len(texts)} chunks...")
    # encode returns a numpy array, we convert to list for ChromaDB compatibility
    embeddings = embedding_model.encode(texts)
    return embeddings.tolist()


def embed_and_index(factsheet_records: list, definition_records: list, api_key: str = None, url_type: str = "both"):
    """
    Build chunks from scraped records, generate embeddings, and index into ChromaDB.
    
    Performs atomic replace: builds new collection, then swaps.
    
    Args:
        factsheet_records: List of scrape results from factsheet scraper
        definition_records: List of scrape results from definition scraper
        api_key: Gemini API key for embeddings
        url_type: "factsheets", "definitions", or "both"
    """
    client = get_chroma_client()
    
    # Build chunks based on what's being refreshed
    if url_type == "factsheets":
        new_chunks = build_chunks(factsheet_records, [])
        # Keep existing definition chunks
        existing_def_chunks = _get_existing_chunks(client, kind="definition")
        _guard_partial_refresh(
            client,
            kind_to_keep="definition",
            kept_chunks=existing_def_chunks,
            url_type=url_type,
        )
        all_chunks = new_chunks + existing_def_chunks
    elif url_type == "definitions":
        new_chunks = build_chunks([], definition_records)
        # Keep existing factsheet chunks
        existing_fs_chunks = _get_existing_chunks(client, kind="factsheet_field")
        _guard_partial_refresh(
            client,
            kind_to_keep="factsheet_field",
            kept_chunks=existing_fs_chunks,
            url_type=url_type,
        )
        all_chunks = existing_fs_chunks + new_chunks
    else:
        all_chunks = build_chunks(factsheet_records, definition_records)
    
    if not all_chunks:
        print("  [Embedder] No chunks to index.")
        return
    
    # Generate embeddings
    texts = [c["text"] for c in all_chunks]
    print(f"  [Embedder] Generating embeddings for {len(texts)} chunks...")
    embeddings = embed_texts(texts, api_key)
    
    # Atomic replace: delete old collection and create new one
    collection_name = "factsheet_kb"
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass  # Collection might not exist yet
    
    collection = client.create_collection(
        name=collection_name,
        metadata={"description": "Factsheet RAG knowledge base"}
    )
    
    # Add all chunks with embeddings
    collection.add(
        ids=[c["id"] for c in all_chunks],
        embeddings=embeddings,
        documents=[c["text"] for c in all_chunks],
        metadatas=[c["metadata"] for c in all_chunks],
    )
    
    print(f"  [Embedder] Indexed {len(all_chunks)} chunks into ChromaDB.")


def _count_chunks_by_kind(collection, kind: str) -> int:
    """Count rows whose metadata kind matches (full scan; KB stays small)."""
    try:
        data = collection.get(include=["metadatas"])
    except Exception as e:
        logger.warning("[Embedder] Could not scan collection: %s", e)
        return 0
    metas = data.get("metadatas") or []
    return sum(1 for m in metas if m and m.get("kind") == kind)


def _guard_partial_refresh(
    client,
    kind_to_keep: str,
    kept_chunks: list,
    url_type: str,
) -> None:
    """Abort if we would drop existing chunks of this kind (silent merge failure)."""
    try:
        collection = client.get_collection("factsheet_kb")
    except Exception:
        return
    expected = _count_chunks_by_kind(collection, kind_to_keep)
    if expected > 0 and len(kept_chunks) == 0:
        raise RuntimeError(
            f"Indexing aborted: could not read {expected} existing '{kind_to_keep}' chunk(s) "
            f"before {url_type} refresh. Re-fetching definitions only would erase factsheet NAV data. "
            f"Fix Chroma read or run a full 'both' reindex."
        )


def _get_existing_chunks(client, kind: str) -> list[dict]:
    """Retrieve existing chunks of a given kind from ChromaDB.

    Does not load stored embeddings: embed_and_index recomputes embeddings from text.
    Including embeddings in .get() has caused failures on large collections and led to
    silent empty merges (data loss) when combined with a bare except.
    """
    collection_name = "factsheet_kb"
    try:
        collection = client.get_collection(collection_name)
    except Exception as e:
        logger.warning("[Embedder] No existing collection %s: %s", collection_name, e)
        return []

    chunks: list[dict] = []

    # Prefer metadata filter (fast when it works)
    try:
        results = collection.get(
            where={"kind": kind},
            include=["documents", "metadatas"],
        )
        if results and results.get("ids"):
            for i, id_ in enumerate(results["ids"]):
                chunks.append(
                    {
                        "id": id_,
                        "text": results["documents"][i],
                        "metadata": results["metadatas"][i],
                    }
                )
            return chunks
    except Exception as e:
        logger.warning("[Embedder] Filtered get failed for kind=%s: %s", kind, e)

    # Fallback: full scan + Python filter (robust across Chroma versions)
    try:
        results = collection.get(include=["documents", "metadatas"])
        if not results or not results.get("ids"):
            return []
        for i, id_ in enumerate(results["ids"]):
            meta = results["metadatas"][i]
            if meta and meta.get("kind") == kind:
                chunks.append(
                    {
                        "id": id_,
                        "text": results["documents"][i],
                        "metadata": meta,
                    }
                )
    except Exception as e:
        logger.error("[Embedder] Failed to read existing chunks: %s", e)
        return []

    return chunks
