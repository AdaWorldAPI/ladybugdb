"""
LadybugDB Jina-Compatible API

Familiar Jina Client syntax, backed by AVX-512 Hamming resonance.

Usage (feels like Jina):
    from ladybugdb.compat import JinaClient
    
    client = JinaClient()
    
    # Encode content to fingerprint (like Jina embeddings)
    fp = client.encode("The sky is blue")
    
    # Search by resonance (like Jina search)
    results = client.search(fp, top_k=10, threshold=0.6)
    
    # Index documents (like Jina index)
    client.index([
        Document(id="1", content="Hello world"),
        Document(id="2", content="Goodbye world"),
    ])

But underneath: 65M comparisons/sec via SIMD Hamming.
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union, Callable, Iterator
from datetime import datetime
import hashlib
import json

try:
    from numba import njit, prange
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    def njit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if not args else decorator(args[0])
    prange = range

from .dto import Node, SearchResult, content_to_fingerprint, random_fingerprint
from ..core.numba_zero_overhead import HammingEngine, BufferPool, VECTOR_UINT64, VECTOR_BITS


# =============================================================================
# DOCUMENT (Jina-compatible)
# =============================================================================

@dataclass
class Document:
    """
    Jina-compatible Document class.
    
    Usage:
        doc = Document(id="1", content="Hello world")
        doc.embedding  # Auto-computed fingerprint
        doc.tags["custom"] = "value"
    """
    id: str = ""
    content: str = ""
    
    # Embedding (fingerprint in our case)
    _embedding: Optional[np.ndarray] = field(default=None, repr=False)
    
    # Jina-compatible fields
    tags: Dict[str, Any] = field(default_factory=dict)
    scores: Dict[str, float] = field(default_factory=dict)
    matches: List['Document'] = field(default_factory=list)
    chunks: List['Document'] = field(default_factory=list)
    
    # Metadata
    mime_type: str = "text/plain"
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def embedding(self) -> np.ndarray:
        """Get or compute embedding (fingerprint)."""
        if self._embedding is None:
            self._embedding = content_to_fingerprint(self.content or self.id)
        return self._embedding
    
    @embedding.setter
    def embedding(self, value: np.ndarray):
        self._embedding = np.asarray(value, dtype=np.uint64)
    
    @property
    def text(self) -> str:
        """Alias for content (Jina compatibility)."""
        return self.content
    
    @text.setter
    def text(self, value: str):
        self.content = value
        self._embedding = None  # Reset on content change
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return {
            'id': self.id,
            'content': self.content,
            'embedding': self.embedding.tolist() if self._embedding is not None else None,
            'tags': self.tags,
            'scores': self.scores,
            'mime_type': self.mime_type,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Document':
        """Create from dict."""
        doc = cls(
            id=data.get('id', ''),
            content=data.get('content', ''),
            tags=data.get('tags', {}),
            mime_type=data.get('mime_type', 'text/plain'),
        )
        if data.get('embedding'):
            doc._embedding = np.array(data['embedding'], dtype=np.uint64)
        return doc
    
    def __hash__(self):
        return hash(self.id)


# =============================================================================
# DOCUMENT ARRAY (Jina-compatible)
# =============================================================================

class DocumentArray:
    """
    Jina-compatible DocumentArray with vectorized operations.
    
    Usage:
        da = DocumentArray([doc1, doc2, doc3])
        da.embeddings  # (N, 157) uint64 matrix
        
        # Find similar
        matches = da.find(query_doc, limit=10)
        
        # Filter
        filtered = da.filter(lambda d: d.tags.get('category') == 'tech')
    """
    
    def __init__(self, docs: Optional[List[Document]] = None):
        self._docs: List[Document] = list(docs) if docs else []
        self._embeddings_cache: Optional[np.ndarray] = None
        self._engine: Optional[HammingEngine] = None
    
    @property
    def embeddings(self) -> np.ndarray:
        """Get embeddings matrix (N, 157) uint64."""
        if self._embeddings_cache is None or len(self._embeddings_cache) != len(self._docs):
            self._embeddings_cache = np.stack([d.embedding for d in self._docs])
        return self._embeddings_cache
    
    @property
    def _hamming_engine(self) -> HammingEngine:
        """Get or create Hamming engine."""
        if self._engine is None:
            self._engine = HammingEngine()
        if self._engine.corpus is None or self._engine.n_vectors != len(self._docs):
            self._engine.index(self.embeddings)
        return self._engine
    
    def append(self, doc: Document) -> None:
        """Add document."""
        self._docs.append(doc)
        self._embeddings_cache = None  # Invalidate cache
    
    def extend(self, docs: List[Document]) -> None:
        """Add multiple documents."""
        self._docs.extend(docs)
        self._embeddings_cache = None
    
    def find(
        self, 
        query: Union[Document, np.ndarray, str],
        limit: int = 10,
        threshold: Optional[float] = None,
    ) -> 'DocumentArray':
        """
        Find similar documents.
        
        Args:
            query: Document, embedding, or text to search for
            limit: Maximum results
            threshold: Minimum similarity (0-1)
        
        Returns:
            DocumentArray of matches with scores
        """
        # Get query embedding
        if isinstance(query, str):
            query_emb = content_to_fingerprint(query)
        elif isinstance(query, Document):
            query_emb = query.embedding
        else:
            query_emb = np.asarray(query, dtype=np.uint64)
        
        # Search
        result = self._hamming_engine.search(query_emb, k=limit)
        
        # Build result DocumentArray
        matches = []
        for idx, dist, sim in zip(result.indices, result.distances, result.similarities):
            if threshold is not None and sim < threshold:
                continue
            
            doc = self._docs[idx]
            doc.scores['hamming_distance'] = float(dist)
            doc.scores['hamming_similarity'] = float(sim)
            matches.append(doc)
        
        return DocumentArray(matches)
    
    def match(
        self,
        query_da: 'DocumentArray',
        limit: int = 10,
        threshold: Optional[float] = None,
    ) -> None:
        """
        Match each document in query_da against this DocumentArray.
        Sets matches on each query document.
        """
        for query_doc in query_da:
            results = self.find(query_doc, limit=limit, threshold=threshold)
            query_doc.matches = list(results)
    
    def filter(self, fn: Callable[[Document], bool]) -> 'DocumentArray':
        """Filter documents by predicate."""
        return DocumentArray([d for d in self._docs if fn(d)])
    
    def map(self, fn: Callable[[Document], Document]) -> 'DocumentArray':
        """Map function over documents."""
        return DocumentArray([fn(d) for d in self._docs])
    
    def shuffle(self, seed: Optional[int] = None) -> 'DocumentArray':
        """Return shuffled copy."""
        import random
        docs = list(self._docs)
        if seed is not None:
            random.seed(seed)
        random.shuffle(docs)
        return DocumentArray(docs)
    
    def split(self, ratio: float) -> tuple['DocumentArray', 'DocumentArray']:
        """Split into two DocumentArrays."""
        split_idx = int(len(self._docs) * ratio)
        return (
            DocumentArray(self._docs[:split_idx]),
            DocumentArray(self._docs[split_idx:])
        )
    
    def __len__(self) -> int:
        return len(self._docs)
    
    def __iter__(self) -> Iterator[Document]:
        return iter(self._docs)
    
    def __getitem__(self, idx: Union[int, slice]) -> Union[Document, 'DocumentArray']:
        if isinstance(idx, slice):
            return DocumentArray(self._docs[idx])
        return self._docs[idx]
    
    def __setitem__(self, idx: int, doc: Document):
        self._docs[idx] = doc
        self._embeddings_cache = None


# =============================================================================
# JINA CLIENT (Compatible API)
# =============================================================================

class JinaClient:
    """
    Jina-compatible client for LadybugDB.
    
    Familiar Jina syntax, backed by Hamming resonance.
    
    Usage:
        client = JinaClient()
        
        # Index documents
        client.index(documents)
        
        # Search
        results = client.search(query, top_k=10)
        
        # Encode text to embedding
        embedding = client.encode("Hello world")
    """
    
    def __init__(self, **kwargs):
        self._documents = DocumentArray()
        self._engine = HammingEngine()
        self._indexed = False
    
    def encode(
        self, 
        content: Union[str, List[str]],
    ) -> Union[np.ndarray, List[np.ndarray]]:
        """
        Encode content to fingerprint embedding.
        
        Args:
            content: Text or list of texts
        
        Returns:
            Fingerprint embedding(s)
        """
        if isinstance(content, str):
            return content_to_fingerprint(content)
        return [content_to_fingerprint(c) for c in content]
    
    def index(
        self,
        docs: Union[List[Document], DocumentArray, List[Dict[str, Any]]],
        **kwargs,
    ) -> None:
        """
        Index documents for searching.
        
        Args:
            docs: Documents to index
        """
        # Convert to DocumentArray if needed
        if isinstance(docs, DocumentArray):
            self._documents = docs
        elif isinstance(docs, list):
            if docs and isinstance(docs[0], dict):
                docs = [Document.from_dict(d) for d in docs]
            self._documents = DocumentArray(docs)
        
        # Build index
        self._engine.index(self._documents.embeddings)
        self._indexed = True
    
    def search(
        self,
        query: Union[Document, np.ndarray, str, List],
        top_k: int = 10,
        threshold: Optional[float] = None,
        **kwargs,
    ) -> Union[DocumentArray, List[DocumentArray]]:
        """
        Search for similar documents.
        
        Args:
            query: Query document, embedding, or text
            top_k: Number of results
            threshold: Minimum similarity (0-1)
        
        Returns:
            DocumentArray of matches
        """
        if not self._indexed:
            raise RuntimeError("Must call index() before search()")
        
        # Handle batch queries
        if isinstance(query, list):
            return [self.search(q, top_k=top_k, threshold=threshold) for q in query]
        
        return self._documents.find(query, limit=top_k, threshold=threshold)
    
    def delete(self, ids: Union[str, List[str]]) -> None:
        """Delete documents by ID."""
        if isinstance(ids, str):
            ids = [ids]
        id_set = set(ids)
        self._documents = self._documents.filter(lambda d: d.id not in id_set)
        self._indexed = False
    
    def update(self, docs: List[Document]) -> None:
        """Update existing documents."""
        id_to_doc = {d.id: d for d in docs}
        for i, doc in enumerate(self._documents):
            if doc.id in id_to_doc:
                self._documents[i] = id_to_doc[doc.id]
        self._indexed = False
    
    @property
    def num_docs(self) -> int:
        """Number of indexed documents."""
        return len(self._documents)


# =============================================================================
# FLOW (Jina-compatible Pipeline)
# =============================================================================

class Flow:
    """
    Jina-compatible Flow for building pipelines.
    
    Usage:
        flow = (
            Flow()
            .add(name='encoder', uses=MyEncoder)
            .add(name='indexer', uses=MyIndexer)
        )
        
        with flow:
            flow.index(docs)
            results = flow.search(query)
    """
    
    def __init__(self):
        self._executors: List[Dict[str, Any]] = []
        self._client: Optional[JinaClient] = None
    
    def add(
        self,
        name: str = "",
        uses: Optional[Any] = None,
        **kwargs,
    ) -> 'Flow':
        """Add executor to flow."""
        self._executors.append({
            'name': name,
            'uses': uses,
            'kwargs': kwargs,
        })
        return self
    
    def __enter__(self) -> 'Flow':
        """Start flow."""
        self._client = JinaClient()
        return self
    
    def __exit__(self, *args):
        """Stop flow."""
        self._client = None
    
    def index(self, docs: List[Document], **kwargs) -> None:
        """Index documents through flow."""
        if self._client is None:
            raise RuntimeError("Must use flow as context manager")
        self._client.index(docs, **kwargs)
    
    def search(self, query: Any, **kwargs) -> DocumentArray:
        """Search through flow."""
        if self._client is None:
            raise RuntimeError("Must use flow as context manager")
        return self._client.search(query, **kwargs)


# =============================================================================
# EXECUTOR BASE (Jina-compatible)
# =============================================================================

class Executor:
    """
    Jina-compatible Executor base class.
    
    Usage:
        class MyEncoder(Executor):
            @requests
            def encode(self, docs: DocumentArray, **kwargs):
                for doc in docs:
                    doc.embedding = self.model.encode(doc.content)
    """
    
    def __init__(self, **kwargs):
        self.runtime_args = kwargs
    
    def __call__(self, docs: DocumentArray, **kwargs) -> DocumentArray:
        """Process documents."""
        return docs


def requests(fn: Optional[Callable] = None, on: str = '/default'):
    """Decorator for executor methods (Jina compatibility)."""
    def decorator(func):
        func._jina_requests = on
        return func
    
    if fn is not None:
        return decorator(fn)
    return decorator


# =============================================================================
# RESONANCE QUERY BUILDER (Fluent API)
# =============================================================================

class ResonanceQuery:
    """
    Fluent API for building resonance queries.
    
    Usage:
        results = (
            ResonanceQuery(client)
            .with_content("The meaning of life")
            .threshold(0.6)
            .limit(10)
            .filter(lambda d: d.tags.get('domain') == 'philosophy')
            .execute()
        )
    """
    
    def __init__(self, client: JinaClient):
        self._client = client
        self._query: Optional[np.ndarray] = None
        self._threshold: Optional[float] = None
        self._limit: int = 10
        self._filters: List[Callable[[Document], bool]] = []
        self._sort_by: Optional[str] = None
    
    def with_content(self, content: str) -> 'ResonanceQuery':
        """Set query by content."""
        self._query = content_to_fingerprint(content)
        return self
    
    def with_embedding(self, embedding: np.ndarray) -> 'ResonanceQuery':
        """Set query by embedding."""
        self._query = np.asarray(embedding, dtype=np.uint64)
        return self
    
    def with_document(self, doc: Document) -> 'ResonanceQuery':
        """Set query by document."""
        self._query = doc.embedding
        return self
    
    def threshold(self, value: float) -> 'ResonanceQuery':
        """Set minimum similarity threshold."""
        self._threshold = value
        return self
    
    def limit(self, k: int) -> 'ResonanceQuery':
        """Set maximum results."""
        self._limit = k
        return self
    
    def filter(self, fn: Callable[[Document], bool]) -> 'ResonanceQuery':
        """Add filter predicate."""
        self._filters.append(fn)
        return self
    
    def sort_by(self, field: str) -> 'ResonanceQuery':
        """Sort results by field."""
        self._sort_by = field
        return self
    
    def execute(self) -> DocumentArray:
        """Execute the query."""
        if self._query is None:
            raise ValueError("Must set query via with_content/with_embedding/with_document")
        
        # Search
        results = self._client.search(
            self._query,
            top_k=self._limit * 2 if self._filters else self._limit,  # Over-fetch if filtering
            threshold=self._threshold,
        )
        
        # Apply filters
        for f in self._filters:
            results = results.filter(f)
        
        # Sort if requested
        if self._sort_by:
            docs = sorted(
                results._docs,
                key=lambda d: d.scores.get(self._sort_by, 0),
                reverse=True
            )
            results = DocumentArray(docs)
        
        # Limit
        return DocumentArray(list(results)[:self._limit])


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def resonate(
    query: Union[str, np.ndarray, Document],
    corpus: Union[List[Document], DocumentArray],
    top_k: int = 10,
    threshold: Optional[float] = None,
) -> DocumentArray:
    """
    One-shot resonance search.
    
    Usage:
        matches = resonate("quantum entanglement", my_documents, threshold=0.7)
    """
    client = JinaClient()
    client.index(corpus)
    return client.search(query, top_k=top_k, threshold=threshold)


def batch_resonate(
    queries: List[Union[str, np.ndarray, Document]],
    corpus: Union[List[Document], DocumentArray],
    top_k: int = 10,
    threshold: Optional[float] = None,
) -> List[DocumentArray]:
    """
    Batch resonance search.
    
    Usage:
        results = batch_resonate(
            ["query 1", "query 2", "query 3"],
            my_documents,
            threshold=0.6
        )
    """
    client = JinaClient()
    client.index(corpus)
    return [client.search(q, top_k=top_k, threshold=threshold) for q in queries]
