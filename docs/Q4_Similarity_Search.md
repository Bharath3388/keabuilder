# Q4: Face & Text Similarity Search System

## Design Overview

KeaBuilder provides multi-modal similarity search — users can find assets by **text description**, **visual similarity**, or **face matching**. The system uses a layered embedding strategy with free/open-source models and ChromaDB as the vector store.

```
┌──────────────────────────────────────────────────────────────┐
│                    Similarity Search Stack                    │
│                                                              │
│  Embedding Providers (multi-provider with fallbacks)         │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Text         │  │ Image        │  │ Face              │  │
│  │              │  │              │  │                   │  │
│  │ Primary:     │  │ Primary:     │  │ InsightFace       │  │
│  │ Gemini       │  │ Gemini Vision│  │ (buffalo_l model) │  │
│  │ Embedding    │  │ → Gemini Emb │  │ 512-dim vector    │  │
│  │ (3072-dim)   │  │ (3072-dim)   │  │                   │  │
│  │              │  │              │  │ Open-source,      │  │
│  │ Fallback:    │  │ Fallback:    │  │ runs locally      │  │
│  │ sentence-    │  │ CLIP ViT-B-32│  │                   │  │
│  │ transformers │  │ (512-dim)    │  │                   │  │
│  │ MiniLM-L6    │  │              │  │                   │  │
│  │ (384-dim)    │  │ Open-source, │  │                   │  │
│  │              │  │ runs locally │  │                   │  │
│  └──────────────┘  └──────────────┘  └───────────────────┘  │
│                                                              │
│  Vector Store                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ ChromaDB (embedded, persistent)                      │    │
│  │ ● Cosine distance (hnsw:space = cosine)              │    │
│  │ ● Collections per workspace × embed_type             │    │
│  │ ● Local SQLite persistence at ./storage/chromadb/    │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

**Implementation:** `backend/services/similarity_search.py`

---

## How It Works

### 1. Indexing (Write Path)

When a new asset is generated, it is automatically indexed into ChromaDB:

```
Generated Asset
      │
      ├─── Text prompt ──▶ embed_text() ──▶ ChromaDB "text" collection
      │
      ├─── Image bytes ──▶ embed_image_clip() ──▶ ChromaDB "clip" collection
      │
      └─── Image bytes ──▶ embed_face() ──▶ ChromaDB "face" collection
                                               (only if face detected)
```

Each workspace has separate collections per embedding type, named `{workspace_id}_{embed_type}`. This provides workspace-level isolation.

### 2. Search (Read Path)

```
Search Query
      │
      ├─── Text query ──▶ embed_text() ──▶ query "text" collection
      │                                     ↓
      │                               Top-K results ranked by cosine similarity
      │
      ├─── Text query ──▶ embed_text_clip() ──▶ query "clip" collection
      │    (text-to-image search)                ↓
      │                                    Find images matching text description
      │
      ├─── Image bytes ──▶ embed_image_clip() ──▶ query "clip" collection
      │    (image-to-image search)                 ↓
      │                                      Find visually similar images
      │
      └─── Image bytes ──▶ embed_face() ──▶ query "face" collection
           (face matching)                   ↓
                                       Find images with same person
```

---

## Embedding Strategies

### Text Embeddings

**Primary: Gemini Embedding (gemini-embedding-001)**
- Dimensionality: 3072
- Provider: Google Generative AI (via LangChain)
- Cost: Free tier available
- Quality: State-of-the-art for semantic similarity

**Fallback: sentence-transformers (all-MiniLM-L6-v2)**
- Dimensionality: 384
- Provider: Local (HuggingFace model, ~22MB)
- Cost: Free, no API needed
- Quality: Good for general text similarity

The system tries Gemini first. If the API key is not configured or the call fails, it falls back to the local model transparently.

### Image Embeddings (Two-Stage Gemini Pipeline)

**Primary: Gemini Vision → Gemini Embedding**
1. **Stage 1**: Send image to `gemini-2.5-flash-lite` with the prompt "Describe this image in one detailed paragraph for similarity search indexing"
2. **Stage 2**: Embed the text description using `gemini-embedding-001` (3072-dim)

This approach maps images and text into the **same embedding space**, enabling accurate cross-modal text-to-image search.

**Fallback: CLIP (clip-ViT-B-32)**
- Dimensionality: 512
- Provider: Local (OpenAI's CLIP via sentence-transformers, ~340MB)
- Natively supports both image and text encoding in a shared space

### Face Embeddings

**InsightFace (buffalo_l model)**
- Dimensionality: 512
- Provider: Local, open-source
- Process:
  1. Detect all faces in the image
  2. Select the **largest face** (by bounding box area)
  3. Extract 512-dimensional face embedding
- If no face is detected, the asset is not indexed in the face collection

---

## Storage Architecture

### ChromaDB Collections

```
ChromaDB
├── demo_workspace_text     (text embeddings — prompt-based search)
├── demo_workspace_clip     (CLIP/Gemini embeddings — visual similarity)
├── demo_workspace_face     (InsightFace embeddings — face matching)
├── workspace_abc_text
├── workspace_abc_clip
└── ...
```

Each collection uses **HNSW (Hierarchical Navigable Small World)** indexing with **cosine distance** for fast approximate nearest neighbor search.

Collection names are sanitized to comply with ChromaDB's naming rules (3–63 chars, alphanumeric + underscores, start/end with alphanumeric).

### Data Persistence

- **Development**: SQLite-backed ChromaDB at `./storage/chromadb/`
- **Production**: Same ChromaDB can be pointed to a remote instance or kept local with persistent volumes

---

## Retrieval & Matching Logic

### Cosine Similarity Scoring

ChromaDB returns cosine **distances** (0 = identical, 2 = opposite). The system converts to **similarity**:

```python
similarity = 1.0 - distance   # 1.0 = perfect match, 0.0 = no match
```

Results are returned sorted by similarity (highest first), with negative values clamped to 0.

### Search Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `top_k` | 10 | Maximum number of results |
| `embed_type` | `"text"` | Which collection to search (`text`, `clip`, `face`) |
| `workspace_id` | required | Scopes search to one workspace |

### API Usage

**Text Search (find assets by description):**
```
POST /api/v1/search
X-API-Key: <key>

{
  "query": "modern minimalist logo with blue gradient",
  "workspace_id": "demo_workspace",
  "embed_type": "text",
  "top_k": 5
}
```

**Response:**
```json
{
  "results": [
    {
      "asset_id": "ast_20260424_image_a3f1",
      "similarity": 0.8742,
      "metadata": { "asset_id": "ast_20260424_image_a3f1" }
    },
    {
      "asset_id": "ast_20260424_image_b2c3",
      "similarity": 0.7891,
      "metadata": { "asset_id": "ast_20260424_image_b2c3" }
    }
  ],
  "query_time_ms": 12.4,
  "total_results": 2
}
```

**Image-to-Image Search (find visually similar images):**
```
POST /api/v1/search
Content-Type: multipart/form-data

query: <image bytes>
workspace_id: demo_workspace
embed_type: clip
```

**Face Search (find images of the same person):**
```
POST /api/v1/search
Content-Type: multipart/form-data

query: <image with face>
workspace_id: demo_workspace
embed_type: face
```

---

## Lazy Loading Strategy

All ML models are loaded on first use to minimize startup time and memory:

```python
_gemini_embeddings = None   # Loaded on first text embed
_text_model = None          # Loaded on first local text embed
_clip_model = None          # Loaded on first image embed
_face_analyzer = None       # Loaded on first face embed
_chroma_client = None       # Loaded on first collection access
```

This means the first search request for each embedding type incurs a one-time model loading delay (~1-5 seconds depending on model size), but subsequent requests are instant.
