"""Q4: Face & Text Similarity Search System.

Uses multi-provider approach:
- Text embeddings: Gemini Embedding (gemini-embedding-001, 3072-dim) primary,
                   sentence-transformers (local) fallback
- Image embeddings: CLIP via sentence-transformers (local, free)
- Face embeddings: InsightFace (open-source)
- Vector store: ChromaDB (open-source, runs embedded)

LangChain integration for embeddings via GoogleGenerativeAIEmbeddings.
"""

import io
import time
import structlog
import numpy as np
from typing import Optional
from pathlib import Path

from config import get_settings
from utils.monitoring import Timer

logger = structlog.get_logger()
settings = get_settings()

# Lazy-loaded models (loaded on first use to save memory)
_gemini_embeddings = None
_text_model = None
_clip_model = None
_face_analyzer = None
_chroma_client = None


# =============================================================================
# Model Loading (Lazy)
# =============================================================================

def _get_gemini_embeddings():
    """Load LangChain Gemini embeddings (primary for text)."""
    global _gemini_embeddings
    if _gemini_embeddings is None and settings.gemini_api_key:
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            _gemini_embeddings = GoogleGenerativeAIEmbeddings(
                model=f"models/{settings.gemini_embedding_model}",
                google_api_key=settings.gemini_api_key,
            )
            logger.info(f"Loaded Gemini embedding model: {settings.gemini_embedding_model}")
        except Exception as e:
            logger.warning(f"Failed to load Gemini embeddings: {e}")
    return _gemini_embeddings


# =============================================================================
# Model Loading (Lazy)
# =============================================================================

def _get_text_model():
    """Load sentence-transformers model for text embeddings."""
    global _text_model
    if _text_model is None:
        from sentence_transformers import SentenceTransformer
        _text_model = SentenceTransformer("all-MiniLM-L6-v2")  # Small, fast, free
        logger.info("Loaded text embedding model: all-MiniLM-L6-v2")
    return _text_model


def _get_clip_model():
    """Load CLIP model for image embeddings."""
    global _clip_model
    if _clip_model is None:
        from sentence_transformers import SentenceTransformer
        _clip_model = SentenceTransformer("clip-ViT-B-32")  # CLIP for images
        logger.info("Loaded CLIP model: clip-ViT-B-32")
    return _clip_model


def _get_face_analyzer():
    """Load InsightFace for face detection and embedding."""
    global _face_analyzer
    if _face_analyzer is None:
        try:
            from insightface.app import FaceAnalysis
            _face_analyzer = FaceAnalysis(
                name="buffalo_l",
                providers=["CPUExecutionProvider"],
            )
            _face_analyzer.prepare(ctx_id=0, det_size=(640, 640))
            logger.info("Loaded InsightFace face analyzer")
        except Exception as e:
            logger.warning(f"InsightFace not available: {e}. Face search disabled.")
            _face_analyzer = "unavailable"
    return _face_analyzer if _face_analyzer != "unavailable" else None


def _get_chroma_client():
    """Get ChromaDB client (persistent, embedded)."""
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        persist_dir = settings.chroma_persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=persist_dir)
        logger.info(f"ChromaDB initialized at {persist_dir}")
    return _chroma_client


# =============================================================================
# Embedding Functions
# =============================================================================

def embed_text(text: str) -> list[float]:
    """Generate text embedding using Gemini (primary) or sentence-transformers (fallback)."""
    # Primary: Gemini embeddings via LangChain
    gemini = _get_gemini_embeddings()
    if gemini is not None:
        try:
            with Timer("gemini_text_embedding"):
                embedding = gemini.embed_query(text)
            logger.info("text_embedding", provider="gemini", dim=len(embedding))
            return embedding
        except Exception as e:
            logger.warning(f"Gemini embedding failed, falling back to local: {e}")

    # Fallback: local sentence-transformers
    model = _get_text_model()
    with Timer("text_embedding"):
        embedding = model.encode(text, normalize_embeddings=True)
    logger.info("text_embedding", provider="sentence-transformers", dim=len(embedding))
    return embedding.tolist()


def embed_image_clip(image_data: bytes) -> list[float]:
    """Generate image embedding using Gemini Vision (describe) + Gemini Embedding.

    Pipeline: Image → Gemini Vision (describe) → Gemini Embedding (3072-dim)
    Fallback: CLIP via sentence-transformers (local, 512-dim)
    """
    # Primary: Gemini Vision → describe image → embed description
    if settings.gemini_api_key:
        try:
            from google import genai
            from google.genai import types as gtypes

            client = genai.Client(api_key=settings.gemini_api_key)

            # Step 1: Describe the image using Gemini Vision
            with Timer("gemini_vision_describe"):
                response = client.models.generate_content(
                    model="gemini-2.5-flash-lite",
                    contents=gtypes.Content(parts=[
                        gtypes.Part(text="Describe this image in one detailed paragraph for similarity search indexing. Include colors, objects, style, composition. Only return the description."),
                        gtypes.Part(inline_data=gtypes.Blob(mime_type="image/png", data=image_data)),
                    ]),
                )
                description = response.text.strip()

            # Step 2: Embed the description
            with Timer("gemini_image_embedding"):
                result = client.models.embed_content(
                    model=settings.gemini_embedding_model,
                    contents=description,
                )
                embedding = result.embeddings[0].values

            logger.info("image_embedding", provider="gemini-vision", dim=len(embedding), desc_len=len(description))
            return list(embedding)
        except Exception as e:
            logger.warning(f"Gemini image embedding failed, falling back to CLIP: {e}")

    # Fallback: CLIP (local)
    from PIL import Image
    model = _get_clip_model()
    image = Image.open(io.BytesIO(image_data)).convert("RGB")

    with Timer("clip_embedding"):
        embedding = model.encode(image, normalize_embeddings=True)
    logger.info("image_embedding", provider="clip", dim=len(embedding))
    return embedding.tolist()


def embed_text_clip(text: str) -> list[float]:
    """Generate text embedding for image search (uses Gemini primary, CLIP fallback)."""
    # Primary: Gemini text embedding (same space as image descriptions)
    gemini = _get_gemini_embeddings()
    if gemini is not None:
        try:
            with Timer("gemini_clip_text_embedding"):
                embedding = gemini.embed_query(text)
            logger.info("clip_text_embedding", provider="gemini", dim=len(embedding))
            return embedding
        except Exception as e:
            logger.warning(f"Gemini text-clip embedding failed: {e}")

    # Fallback: CLIP text embedding
    model = _get_clip_model()
    with Timer("clip_text_embedding"):
        embedding = model.encode(text, normalize_embeddings=True)
    logger.info("clip_text_embedding", provider="clip", dim=len(embedding))
    return embedding.tolist()


def embed_face(image_data: bytes) -> Optional[list[float]]:
    """Extract face embedding using InsightFace."""
    analyzer = _get_face_analyzer()
    if analyzer is None:
        logger.warning("Face analysis not available")
        return None

    from PIL import Image

    image = Image.open(io.BytesIO(image_data)).convert("RGB")
    img_array = np.array(image)

    with Timer("face_embedding"):
        faces = analyzer.get(img_array)

    if not faces:
        logger.info("No faces detected in image")
        return None

    # Return embedding of the largest face
    largest_face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    return largest_face.embedding.tolist()


# =============================================================================
# ChromaDB Collection Management
# =============================================================================

def _get_collection(workspace_id: str, embed_type: str):
    """Get or create a ChromaDB collection for a workspace + embed type."""
    client = _get_chroma_client()
    # Sanitize: ChromaDB names must be 3-63 chars, start/end with alphanumeric,
    # contain only alphanumeric, underscores, hyphens
    import re
    safe_workspace = re.sub(r"[^a-zA-Z0-9_]", "_", workspace_id)[:40]
    safe_embed = re.sub(r"[^a-zA-Z0-9_]", "_", embed_type)[:20]
    collection_name = f"{safe_workspace}_{safe_embed}"
    # Ensure it starts and ends with alphanumeric
    collection_name = collection_name.strip("_") or "default_collection"
    if len(collection_name) < 3:
        collection_name = collection_name + "_col"
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


# =============================================================================
# Index & Search
# =============================================================================

async def index_asset(
    asset_id: str,
    workspace_id: str,
    embed_type: str,
    data: str | bytes,
    metadata: dict = None,
):
    """Index an asset's embedding into ChromaDB."""
    if embed_type == "text":
        embedding = embed_text(data)
    elif embed_type == "clip":
        embedding = embed_image_clip(data)
    elif embed_type == "face":
        embedding = embed_face(data)
        if embedding is None:
            logger.info(f"No face found in asset {asset_id}, skipping face index")
            return
    else:
        raise ValueError(f"Unknown embed type: {embed_type}")

    collection = _get_collection(workspace_id, embed_type)
    try:
        collection.upsert(
            ids=[asset_id],
            embeddings=[embedding],
            metadatas=[metadata or {"asset_id": asset_id}],
        )
    except Exception as e:
        if "dimension" in str(e).lower():
            # Embedding dimension changed (e.g. provider switch). Reset collection.
            logger.warning("dimension_mismatch_resetting_collection", error=str(e))
            client = _get_chroma_client()
            client.delete_collection(collection.name)
            collection = _get_collection(workspace_id, embed_type)
            collection.upsert(
                ids=[asset_id],
                embeddings=[embedding],
                metadatas=[metadata or {"asset_id": asset_id}],
            )
        else:
            raise
    logger.info(f"Indexed asset {asset_id} in {embed_type} collection")


async def search_similar(
    query: str | bytes,
    workspace_id: str,
    embed_type: str = "text",
    top_k: int = 10,
) -> dict:
    """Search for similar assets."""
    start_time = time.perf_counter()

    # Generate query embedding
    if embed_type == "text":
        query_embedding = embed_text(query)
    elif embed_type == "clip":
        if isinstance(query, str):
            query_embedding = embed_text_clip(query)  # Text-to-image search
        else:
            query_embedding = embed_image_clip(query)
    elif embed_type == "face":
        query_embedding = embed_face(query)
        if query_embedding is None:
            return {"results": [], "query_time_ms": 0, "total_results": 0}
    else:
        raise ValueError(f"Unknown embed type: {embed_type}")

    # Query ChromaDB
    collection = _get_collection(workspace_id, embed_type)
    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count() or 1),
            include=["distances", "metadatas"],
        )
    except Exception as e:
        if "dimension" in str(e).lower():
            # Collection has stale embeddings with different dimensions — reset it
            logger.warning("search_dimension_mismatch_resetting", error=str(e))
            client = _get_chroma_client()
            client.delete_collection(collection.name)
            return {"results": [], "query_time_ms": 0, "total_results": 0}
        raise

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    # Format results (ChromaDB returns distances, convert to similarity)
    formatted = []
    if results["ids"] and results["ids"][0]:
        for i, asset_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i] if results["distances"] else 0
            similarity = 1.0 - distance  # Cosine distance to similarity
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}
            formatted.append({
                "asset_id": asset_id,
                "similarity": round(max(similarity, 0), 4),
                "metadata": metadata,
            })

    return {
        "results": formatted,
        "query_time_ms": round(elapsed_ms, 2),
        "total_results": len(formatted),
    }
