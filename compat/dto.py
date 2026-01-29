"""
LadybugDB Data Transfer Objects

Familiar Pydantic-like syntax, but backed by:
- NumPy structured arrays (zero-copy)
- Numba JIT for hot paths
- Pre-allocated buffers

Usage feels like dataclasses:
    node = Node(id="abc", content="hello", qidx=128)
    node.fingerprint  # Lazy computed
    node.to_arrow()   # Zero-copy to Arrow
    node.to_dict()    # For JSON serialization

But underneath: pure machine code.
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union, TypeVar, Generic, Type
from datetime import datetime
import json
import hashlib

try:
    from numba import njit, types
    from numba.typed import Dict as NumbaDict, List as NumbaList
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    def njit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if not args else decorator(args[0])

try:
    import pyarrow as pa
    ARROW_AVAILABLE = True
except ImportError:
    ARROW_AVAILABLE = False


# =============================================================================
# CONSTANTS
# =============================================================================

FINGERPRINT_BITS = 10_000
FINGERPRINT_UINT64 = 157
FINGERPRINT_BYTES = 1250
EMBEDDING_DIM = 1024
THINKING_STYLE_DIM = 7
SCENT_DIM = 48


# =============================================================================
# FINGERPRINT GENERATION (Numba-accelerated)
# =============================================================================

@njit(cache=True)
def _hash_to_fingerprint(hash_bytes: np.ndarray, out: np.ndarray) -> None:
    """
    Expand hash bytes into 10K bit fingerprint using LFSR.
    Deterministic: same hash → same fingerprint.
    """
    # Use hash as seed for LFSR
    state = np.uint64(0)
    for i in range(min(8, len(hash_bytes))):
        state = (state << 8) | np.uint64(hash_bytes[i])
    
    if state == 0:
        state = np.uint64(0xDEADBEEF)
    
    # Generate 157 uint64 values
    for i in range(157):
        # Xorshift64
        state ^= state << np.uint64(13)
        state ^= state >> np.uint64(7)
        state ^= state << np.uint64(17)
        out[i] = state


def content_to_fingerprint(content: str) -> np.ndarray:
    """Generate deterministic fingerprint from content."""
    hash_bytes = np.frombuffer(
        hashlib.sha256(content.encode()).digest(), 
        dtype=np.uint8
    )
    out = np.zeros(FINGERPRINT_UINT64, dtype=np.uint64)
    _hash_to_fingerprint(hash_bytes, out)
    return out


def random_fingerprint() -> np.ndarray:
    """Generate random fingerprint."""
    return np.random.randint(0, 2**63, FINGERPRINT_UINT64, dtype=np.uint64)


# =============================================================================
# BASE DTO
# =============================================================================

@dataclass
class BaseDTO:
    """Base class for all DTOs with common serialization."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, np.ndarray):
                result[key] = value.tolist()
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, BaseDTO):
                result[key] = value.to_dict()
            elif isinstance(value, list) and value and isinstance(value[0], BaseDTO):
                result[key] = [v.to_dict() for v in value]
            else:
                result[key] = value
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseDTO':
        """Create from dict."""
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'BaseDTO':
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))


# =============================================================================
# NODE DTO
# =============================================================================

@dataclass
class Node(BaseDTO):
    """
    Graph node with VSA fingerprint.
    
    Usage:
        node = Node(id="thought_1", content="The sky is blue", label="Thought")
        node.fingerprint  # Auto-generated from content
        node.qidx = 180   # Qualia index (0-255)
        
        # Search by resonance
        similar = db.resonate(node.fingerprint, threshold=0.6)
    """
    id: str
    content: str = ""
    label: str = "Node"
    
    # VSA fields (lazy-computed)
    _fingerprint: Optional[np.ndarray] = field(default=None, repr=False)
    _embedding: Optional[np.ndarray] = field(default=None, repr=False)
    _thinking_style: Optional[np.ndarray] = field(default=None, repr=False)
    
    # Metadata
    qidx: int = 128  # Qualia index 0-255
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    version: int = 1
    
    @property
    def fingerprint(self) -> np.ndarray:
        """Get or compute fingerprint."""
        if self._fingerprint is None:
            self._fingerprint = content_to_fingerprint(self.content or self.id)
        return self._fingerprint
    
    @fingerprint.setter
    def fingerprint(self, value: np.ndarray):
        self._fingerprint = value
    
    @property
    def embedding(self) -> Optional[np.ndarray]:
        """Get embedding (must be set externally via encoder)."""
        return self._embedding
    
    @embedding.setter
    def embedding(self, value: np.ndarray):
        self._embedding = np.asarray(value, dtype=np.float32)
    
    @property
    def thinking_style(self) -> np.ndarray:
        """Get or compute thinking style vector."""
        if self._thinking_style is None:
            # Default: derive from qidx
            self._thinking_style = np.zeros(THINKING_STYLE_DIM, dtype=np.float32)
            self._thinking_style[self.qidx % THINKING_STYLE_DIM] = 1.0
        return self._thinking_style
    
    @thinking_style.setter
    def thinking_style(self, value: np.ndarray):
        self._thinking_style = np.asarray(value, dtype=np.float32)
    
    def to_arrow(self) -> 'pa.StructScalar':
        """Convert to Arrow struct (zero-copy where possible)."""
        if not ARROW_AVAILABLE:
            raise ImportError("PyArrow required for to_arrow()")
        
        return {
            'id': self.id,
            'label': self.label,
            'content': self.content,
            'fingerprint': self.fingerprint.view(np.uint8),
            'embedding': self._embedding,
            'thinking_style': self.thinking_style,
            'qidx': self.qidx,
            'properties': json.dumps(self.properties),
            'created_at': self.created_at,
            'version': self.version,
        }
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        if isinstance(other, Node):
            return self.id == other.id
        return False


# =============================================================================
# EDGE DTO
# =============================================================================

@dataclass
class Edge(BaseDTO):
    """
    Graph edge with amplification tracking.
    
    Usage:
        edge = Edge(
            from_id="config_1",
            to_id="thought_1", 
            type="CAUSES",
            amplification=2.5  # Butterfly detection uses this
        )
    """
    from_id: str
    to_id: str
    type: str = "RELATES_TO"
    
    # Butterfly causality
    weight: float = 1.0
    amplification: float = 1.0  # > 1.0 = amplifying, < 1.0 = dampening
    confidence: float = 1.0
    
    # Metadata
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def id(self) -> str:
        """Edge ID derived from endpoints and type."""
        return f"{self.from_id}--{self.type}-->{self.to_id}"
    
    def to_arrow(self) -> Dict[str, Any]:
        """Convert to Arrow-compatible dict."""
        return {
            'id': self.id,
            'from_id': self.from_id,
            'to_id': self.to_id,
            'type': self.type,
            'weight': self.weight,
            'amplification': self.amplification,
            'confidence': self.confidence,
            'properties': json.dumps(self.properties),
            'created_at': self.created_at,
        }


# =============================================================================
# SPECIALIZED NODE TYPES
# =============================================================================

@dataclass
class Thought(Node):
    """A cognitive thought node."""
    label: str = "Thought"
    
    # Thought-specific
    intensity: float = 0.5  # 0-1
    valence: float = 0.0    # -1 to 1 (negative to positive)
    
    @property
    def is_positive(self) -> bool:
        return self.valence > 0
    
    @property
    def is_intense(self) -> bool:
        return self.intensity > 0.7


@dataclass  
class Concept(Node):
    """An abstract concept node."""
    label: str = "Concept"
    
    # Concept-specific
    abstraction_level: int = 1  # 1=concrete, 5=abstract
    domain: str = ""
    
    @classmethod
    def from_thoughts(cls, thoughts: List[Thought], name: str) -> 'Concept':
        """Create concept by bundling thoughts."""
        # Bundle fingerprints
        if thoughts:
            fps = np.stack([t.fingerprint for t in thoughts])
            # Majority vote for bundling
            bundled = np.zeros(FINGERPRINT_UINT64, dtype=np.uint64)
            for i in range(FINGERPRINT_UINT64):
                for bit in range(64):
                    count = sum(1 for t in thoughts if fps[thoughts.index(t), i] & (1 << bit))
                    if count > len(thoughts) // 2:
                        bundled[i] |= np.uint64(1 << bit)
            
            concept = cls(id=f"concept_{name}", content=name)
            concept._fingerprint = bundled
            return concept
        return cls(id=f"concept_{name}", content=name)


@dataclass
class LearningMoment(Node):
    """A captured learning moment."""
    label: str = "LearningMoment"
    
    # Learning-specific
    breakthrough_level: int = 1  # 1-5
    concepts_involved: List[str] = field(default_factory=list)
    context: str = ""
    
    @property
    def is_breakthrough(self) -> bool:
        return self.breakthrough_level >= 4


@dataclass
class Decision(Node):
    """A decision node for agent blackboard."""
    label: str = "Decision"
    
    # Decision-specific
    decision_type: str = "CHOICE"  # CHOICE, GATE, HANDOVER
    outcome: str = ""
    rationale: str = ""
    agent_id: str = ""
    
    # Gate decisions
    gate_result: Optional[str] = None  # FLOW, HOLD, BLOCK


@dataclass
class Blocker(Node):
    """A blocker node for agent coordination."""
    label: str = "Blocker"
    
    # Blocker-specific
    blocker_type: str = "TECHNICAL"  # TECHNICAL, DOMAIN, RESOURCE
    severity: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    blocking_task: str = ""
    resolution: Optional[str] = None
    resolved_at: Optional[datetime] = None
    
    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None


# =============================================================================
# QUERY RESULTS
# =============================================================================

@dataclass
class SearchResult(BaseDTO):
    """Result from a resonance/vector search."""
    nodes: List[Node]
    distances: np.ndarray
    similarities: np.ndarray
    
    def __len__(self) -> int:
        return len(self.nodes)
    
    def __iter__(self):
        for node, dist, sim in zip(self.nodes, self.distances, self.similarities):
            yield node, float(dist), float(sim)
    
    def top(self, k: int = 1) -> List[Node]:
        """Get top k results."""
        return self.nodes[:k]
    
    def above_threshold(self, threshold: float = 0.6) -> List[Node]:
        """Get results above similarity threshold."""
        return [n for n, s in zip(self.nodes, self.similarities) if s >= threshold]


@dataclass
class PathResult(BaseDTO):
    """Result from a graph traversal."""
    paths: List[List[Node]]
    edges: List[List[Edge]]
    amplifications: List[float]
    
    def __len__(self) -> int:
        return len(self.paths)
    
    def butterflies(self, threshold: float = 2.0) -> List[Tuple[List[Node], float]]:
        """Get paths with amplification above threshold."""
        return [
            (path, amp) 
            for path, amp in zip(self.paths, self.amplifications)
            if amp >= threshold
        ]


@dataclass
class QueryResult(BaseDTO):
    """Generic query result with metadata."""
    data: List[Dict[str, Any]]
    columns: List[str]
    row_count: int
    execution_time_ms: float
    
    def __len__(self) -> int:
        return self.row_count
    
    def to_dataframe(self):
        """Convert to pandas DataFrame."""
        import pandas as pd
        return pd.DataFrame(self.data, columns=self.columns)
    
    def to_arrow_table(self):
        """Convert to Arrow Table."""
        if not ARROW_AVAILABLE:
            raise ImportError("PyArrow required")
        import pyarrow as pa
        return pa.Table.from_pylist(self.data)


# =============================================================================
# HANDOVER DTO (Agent2Agent)
# =============================================================================

@dataclass
class Handover(BaseDTO):
    """
    Agent handover packet.
    
    Contains everything needed to continue work in a new context.
    """
    from_agent: str
    to_agent: str
    task: str
    
    # Context
    context: str = ""
    decisions_made: List[Decision] = field(default_factory=list)
    blockers: List[Blocker] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    
    # Resonance state
    resonance_hits: List[str] = field(default_factory=list)
    thinking_style: Optional[np.ndarray] = None
    
    # Next steps
    next_steps: List[str] = field(default_factory=list)
    priority: str = "MEDIUM"
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    session_id: str = ""
    
    def to_markdown(self) -> str:
        """Render as markdown for context window."""
        lines = [
            f"# Handover: {self.from_agent} → {self.to_agent}",
            f"**Task:** {self.task}",
            f"**Priority:** {self.priority}",
            "",
            "## Context",
            self.context,
            "",
        ]
        
        if self.decisions_made:
            lines.append("## Decisions Made")
            for d in self.decisions_made:
                lines.append(f"- **{d.decision_type}**: {d.outcome}")
                if d.rationale:
                    lines.append(f"  - Rationale: {d.rationale}")
            lines.append("")
        
        if self.blockers:
            lines.append("## Blockers")
            for b in self.blockers:
                status = "✅ Resolved" if b.is_resolved else "🔴 Active"
                lines.append(f"- [{status}] {b.content} ({b.severity})")
            lines.append("")
        
        if self.files_modified:
            lines.append("## Files Modified")
            for f in self.files_modified:
                lines.append(f"- `{f}`")
            lines.append("")
        
        if self.next_steps:
            lines.append("## Next Steps")
            for i, step in enumerate(self.next_steps, 1):
                lines.append(f"{i}. {step}")
        
        return "\n".join(lines)


# =============================================================================
# BATCH OPERATIONS (Numba-optimized)
# =============================================================================

class NodeBatch:
    """
    Batch of nodes stored in columnar format for Numba.
    
    Usage:
        batch = NodeBatch(capacity=10000)
        batch.add(node1)
        batch.add(node2)
        
        # Vectorized operations
        distances = batch.hamming_to(query_fingerprint)
        similar = batch.filter_by_similarity(query, threshold=0.6)
    """
    
    def __init__(self, capacity: int = 10000):
        self.capacity = capacity
        self.size = 0
        
        # Columnar storage
        self.ids: List[str] = []
        self.labels: List[str] = []
        self.contents: List[str] = []
        self.fingerprints = np.zeros((capacity, FINGERPRINT_UINT64), dtype=np.uint64)
        self.qidxs = np.zeros(capacity, dtype=np.int32)
        self.embeddings = np.zeros((capacity, EMBEDDING_DIM), dtype=np.float32)
        self._has_embeddings = np.zeros(capacity, dtype=np.bool_)
    
    def add(self, node: Node) -> int:
        """Add node to batch, return index."""
        if self.size >= self.capacity:
            self._grow()
        
        idx = self.size
        self.ids.append(node.id)
        self.labels.append(node.label)
        self.contents.append(node.content)
        self.fingerprints[idx] = node.fingerprint
        self.qidxs[idx] = node.qidx
        
        if node._embedding is not None:
            self.embeddings[idx] = node._embedding
            self._has_embeddings[idx] = True
        
        self.size += 1
        return idx
    
    def add_many(self, nodes: List[Node]) -> List[int]:
        """Add multiple nodes."""
        return [self.add(n) for n in nodes]
    
    def _grow(self):
        """Double capacity."""
        new_capacity = self.capacity * 2
        
        new_fps = np.zeros((new_capacity, FINGERPRINT_UINT64), dtype=np.uint64)
        new_fps[:self.capacity] = self.fingerprints
        self.fingerprints = new_fps
        
        new_qidx = np.zeros(new_capacity, dtype=np.int32)
        new_qidx[:self.capacity] = self.qidxs
        self.qidxs = new_qidx
        
        new_emb = np.zeros((new_capacity, EMBEDDING_DIM), dtype=np.float32)
        new_emb[:self.capacity] = self.embeddings
        self.embeddings = new_emb
        
        new_has = np.zeros(new_capacity, dtype=np.bool_)
        new_has[:self.capacity] = self._has_embeddings
        self._has_embeddings = new_has
        
        self.capacity = new_capacity
    
    def get(self, idx: int) -> Node:
        """Get node by index."""
        node = Node(
            id=self.ids[idx],
            label=self.labels[idx],
            content=self.contents[idx],
            qidx=int(self.qidxs[idx]),
        )
        node._fingerprint = self.fingerprints[idx].copy()
        if self._has_embeddings[idx]:
            node._embedding = self.embeddings[idx].copy()
        return node
    
    def __len__(self) -> int:
        return self.size
    
    def __iter__(self):
        for i in range(self.size):
            yield self.get(i)


# =============================================================================
# TYPE REGISTRY
# =============================================================================

NODE_TYPES: Dict[str, Type[Node]] = {
    'Node': Node,
    'Thought': Thought,
    'Concept': Concept,
    'LearningMoment': LearningMoment,
    'Decision': Decision,
    'Blocker': Blocker,
}

def create_node(label: str, **kwargs) -> Node:
    """Factory for creating typed nodes."""
    cls = NODE_TYPES.get(label, Node)
    return cls(label=label, **kwargs)
