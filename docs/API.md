# API Reference

Complete API documentation for LadybugDB.

---

## Table of Contents

- [Core](#core)
  - [connect()](#connect)
  - [LadybugEngine](#ladybugengine)
  - [HammingEngine](#hammingengine)
- [DTOs](#dtos)
  - [Node](#node)
  - [Edge](#edge)
  - [Specialized Nodes](#specialized-nodes)
  - [Results](#results)
- [Compatibility APIs](#compatibility-apis)
  - [Jina API](#jina-api)
  - [Neo4j API](#neo4j-api)
- [Compression](#compression)
- [Utilities](#utilities)

---

## Core

### connect()

```python
def connect(
    path: str,
    *,
    create: bool = True,
    read_only: bool = False,
) -> LadybugEngine
```

Connect to or create a LadybugDB database.

**Parameters:**
- `path`: Path to database directory
- `create`: Create if doesn't exist (default: True)
- `read_only`: Open in read-only mode (default: False)

**Returns:** `LadybugEngine` instance

**Example:**
```python
from ladybugdb import connect

db = connect("./my_database")
db = connect("./readonly_db", read_only=True)
```

---

### LadybugEngine

Main database interface.

#### Methods

##### sql()

```python
def sql(self, query: str, params: dict = None) -> List[Dict]
```

Execute SQL query.

**Example:**
```python
results = db.sql("SELECT * FROM nodes WHERE qidx > ?", {"1": 100})
```

##### cypher()

```python
def cypher(self, query: str, params: dict = None) -> List[Dict]
```

Execute Cypher query (transpiled to SQL).

**Example:**
```python
results = db.cypher("""
    MATCH (a:Thought)-[:CAUSES*1..5]->(b)
    WHERE a.qidx > $min_qidx
    RETURN b
""", {"min_qidx": 100})
```

##### resonate()

```python
def resonate(
    self,
    fingerprint: np.ndarray,
    threshold: float = 0.6,
    limit: int = 10,
) -> SearchResult
```

Search by Hamming similarity.

**Parameters:**
- `fingerprint`: Query fingerprint (157 uint64 values = 10,048 bits)
- `threshold`: Minimum similarity (0.0 to 1.0)
- `limit`: Maximum results

**Returns:** `SearchResult` with nodes, distances, similarities

##### resonate_content()

```python
def resonate_content(
    self,
    content: str,
    threshold: float = 0.6,
    limit: int = 10,
) -> SearchResult
```

Search by content (auto-generates fingerprint).

##### vector_search()

```python
def vector_search(
    self,
    embedding: np.ndarray,
    k: int = 10,
    filter: str = None,
) -> List[Dict]
```

Approximate nearest neighbor search.

##### add_node()

```python
def add_node(self, node: Node) -> str
```

Add a node to the database. Returns node ID.

##### add_edge()

```python
def add_edge(self, edge: Edge) -> str
```

Add an edge to the database. Returns edge ID.

##### detect_butterflies()

```python
def detect_butterflies(
    self,
    source: str,
    threshold: float = 2.0,
    max_depth: int = 10,
) -> List[Tuple[List[Node], float]]
```

Find causal chains with amplification above threshold.

**Returns:** List of (path, total_amplification) tuples

---

### HammingEngine

Low-level SIMD-accelerated Hamming operations.

```python
from ladybugdb.core import HammingEngine

engine = HammingEngine()
```

#### Methods

##### index()

```python
def index(self, vectors: np.ndarray) -> None
```

Index corpus for searching.

**Parameters:**
- `vectors`: Shape (N, 157) uint64 array of fingerprints

##### search()

```python
def search(self, query: np.ndarray, k: int = 10) -> SearchResult
```

Find k nearest neighbors by Hamming distance.

**Parameters:**
- `query`: Single fingerprint (157 uint64)
- `k`: Number of results

**Returns:** `SearchResult` with indices, distances, similarities

##### hamming()

```python
def hamming(self, a: np.ndarray, b: np.ndarray) -> int
```

Compute Hamming distance between two fingerprints.

---

## DTOs

### Node

Base node class.

```python
from ladybugdb.compat import Node

node = Node(
    id="unique_id",           # Required
    content="Text content",   # Optional
    label="NodeType",         # Default: "Node"
    qidx=128,                 # Qualia index 0-255
    properties={},            # Custom properties
)
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `id` | str | Unique identifier |
| `content` | str | Text content |
| `label` | str | Node type/label |
| `qidx` | int | Qualia index (0-255) |
| `properties` | dict | Custom key-value pairs |
| `fingerprint` | np.ndarray | Auto-computed 10K bit fingerprint |
| `embedding` | np.ndarray | Optional dense embedding |
| `thinking_style` | np.ndarray | 7-dim thinking style vector |
| `created_at` | datetime | Creation timestamp |
| `version` | int | Version number |

#### Methods

```python
node.to_dict()      # Convert to JSON-serializable dict
node.to_json()      # Convert to JSON string
node.to_arrow()     # Convert to Arrow struct (zero-copy)
Node.from_dict(d)   # Create from dict
Node.from_json(s)   # Create from JSON string
```

---

### Edge

Relationship between nodes.

```python
from ladybugdb.compat import Edge

edge = Edge(
    from_id="node_1",         # Source node ID
    to_id="node_2",           # Target node ID
    type="CAUSES",            # Relationship type
    weight=1.0,               # Edge weight
    amplification=1.5,        # For butterfly detection
    confidence=0.9,           # Confidence score
    properties={},            # Custom properties
)
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `from_id` | str | Source node ID |
| `to_id` | str | Target node ID |
| `type` | str | Relationship type |
| `weight` | float | Edge weight (default: 1.0) |
| `amplification` | float | Amplification factor (default: 1.0) |
| `confidence` | float | Confidence score (default: 1.0) |
| `id` | str | Auto-generated: `{from}--{type}-->{to}` |

---

### Specialized Nodes

#### Thought

```python
from ladybugdb.compat import Thought

thought = Thought(
    id="t1",
    content="An idea",
    intensity=0.8,      # 0.0 to 1.0
    valence=0.5,        # -1.0 to 1.0 (negative to positive)
)

thought.is_positive    # True if valence > 0
thought.is_intense     # True if intensity > 0.7
```

#### Concept

```python
from ladybugdb.compat import Concept

concept = Concept(
    id="c1",
    content="Abstract idea",
    abstraction_level=3,  # 1=concrete, 5=abstract
    domain="philosophy",
)

# Create from bundled thoughts
concept = Concept.from_thoughts([t1, t2, t3], name="Combined")
```

#### LearningMoment

```python
from ladybugdb.compat import LearningMoment

moment = LearningMoment(
    id="lm1",
    content="Realized X leads to Y",
    breakthrough_level=4,     # 1-5
    concepts_involved=["X", "Y"],
    context="During debugging",
)

moment.is_breakthrough  # True if level >= 4
```

#### Decision

```python
from ladybugdb.compat import Decision

decision = Decision(
    id="d1",
    decision_type="GATE",     # CHOICE, GATE, HANDOVER
    outcome="FLOW",
    rationale="All tests pass",
    agent_id="reviewer",
    gate_result="FLOW",       # FLOW, HOLD, BLOCK
)
```

#### Blocker

```python
from ladybugdb.compat import Blocker

blocker = Blocker(
    id="b1",
    content="Missing API credentials",
    blocker_type="RESOURCE",  # TECHNICAL, DOMAIN, RESOURCE
    severity="HIGH",          # LOW, MEDIUM, HIGH, CRITICAL
    blocking_task="deployment",
)

blocker.is_resolved  # True if resolved_at is set
```

#### Handover

```python
from ladybugdb.compat import Handover

handover = Handover(
    from_agent="Archaeologist",
    to_agent="Developer",
    task="Implement feature",
    context="Found the root cause...",
    decisions_made=[decision1, decision2],
    blockers=[blocker1],
    files_modified=["src/main.py"],
    next_steps=["Step 1", "Step 2"],
    priority="HIGH",
)

# Render for LLM context
markdown = handover.to_markdown()
```

---

### Results

#### SearchResult

```python
from ladybugdb.compat import SearchResult

result = SearchResult(
    nodes=[node1, node2],
    distances=np.array([100, 200]),
    similarities=np.array([0.99, 0.98]),
)

len(result)                    # Number of results
result.top(3)                  # Top 3 nodes
result.above_threshold(0.9)    # Nodes with similarity >= 0.9

for node, dist, sim in result:
    print(f"{node.id}: {sim:.2%}")
```

#### PathResult

```python
from ladybugdb.compat import PathResult

result = PathResult(
    paths=[[node1, node2, node3]],
    edges=[[edge1, edge2]],
    amplifications=[6.0],
)

butterflies = result.butterflies(threshold=2.0)
```

#### QueryResult

```python
from ladybugdb.compat import QueryResult

result = QueryResult(
    data=[{"id": "1", "name": "Alice"}],
    columns=["id", "name"],
    row_count=1,
    execution_time_ms=5.2,
)

df = result.to_dataframe()      # pandas DataFrame
table = result.to_arrow_table() # PyArrow Table
```

---

## Compatibility APIs

### Jina API

#### Document

```python
from ladybugdb.compat import Document

doc = Document(
    id="doc_1",
    content="Hello world",
    tags={"category": "greeting"},
)

doc.embedding          # Auto-computed fingerprint
doc.text               # Alias for content
doc.scores             # Populated after search
doc.matches            # Populated after matching
```

#### DocumentArray

```python
from ladybugdb.compat import DocumentArray

da = DocumentArray([doc1, doc2, doc3])

da.embeddings          # (N, 157) uint64 matrix
da.find(query, limit=10)
da.filter(lambda d: d.tags.get("category") == "tech")
da.map(lambda d: transform(d))
da.shuffle(seed=42)
train, test = da.split(0.8)
```

#### JinaClient

```python
from ladybugdb.compat import JinaClient

client = JinaClient()

# Encode
embedding = client.encode("Hello world")
embeddings = client.encode(["Hello", "World"])

# Index
client.index(documents)

# Search
results = client.search(query, top_k=10, threshold=0.6)

# Manage
client.delete(["id1", "id2"])
client.update([updated_doc])
client.num_docs  # Count
```

#### ResonanceQuery (Fluent API)

```python
from ladybugdb.compat import ResonanceQuery

results = (
    ResonanceQuery(client)
    .with_content("quantum physics")
    .threshold(0.6)
    .limit(10)
    .filter(lambda d: d.tags.get("year") > 2020)
    .sort_by("hamming_similarity")
    .execute()
)
```

#### Convenience Functions

```python
from ladybugdb.compat import resonate, batch_resonate

# One-shot search
matches = resonate("query", corpus, threshold=0.7)

# Batch search
results = batch_resonate(
    ["query1", "query2", "query3"],
    corpus,
    top_k=10
)
```

---

### Neo4j API

#### GraphDatabase

```python
from ladybugdb.compat import GraphDatabase

driver = GraphDatabase.driver("ladybug://./mydb")
```

#### Session

```python
with driver.session() as session:
    result = session.run(
        "MATCH (n:Person {name: $name}) RETURN n",
        name="Alice"
    )
    
    with session.begin_transaction() as tx:
        tx.run("CREATE (n:Person {name: 'Bob'})")
        tx.commit()
```

#### Result

```python
result = session.run("MATCH (n) RETURN n LIMIT 10")

result.single()        # Single record or None
result.peek()          # Peek without consuming
result.data()          # All records as dicts
result.keys()          # Column names
result.values()        # All values

for record in result:
    print(record["n"])
    print(record.get("name", "Unknown"))
```

#### Cypher Utilities

```python
from ladybugdb.compat import cypher_to_sql, parse_cypher

# Transpile to SQL
sql = cypher_to_sql("MATCH (a)-[:KNOWS]->(b) RETURN b")

# Parse to AST
ast = parse_cypher("MATCH (n) WHERE n.age > 25 RETURN n")
```

---

## Compression

### Compressor

```python
from ladybugdb.compat import Compressor, EncodingType

compressor = Compressor(
    rle_threshold=0.5,      # Min compression ratio for RLE
    dict_threshold=256,     # Max unique values for dictionary
    for_bit_threshold=16,   # Max bits for FOR
)

# Auto-select best encoding
block = compressor.compress(data)

# Force specific encoding
block = compressor.compress(data, force_encoding=EncodingType.RLE)

# Compress strings
block = compressor.compress_strings(["a", "b", "a", "c"])
```

### CompressedBlock

```python
block.encoding           # EncodingType
block.dtype              # numpy dtype
block.n_values           # Number of values
block.compressed_size    # Bytes
block.uncompressed_size  # Bytes
block.compression_ratio  # Ratio (higher = better)

# Decode
data = block.decode()    # Full decode (cached)
slice = block.slice(10, 20)  # Partial decode
```

### EncodingType

```python
from ladybugdb.compat import EncodingType

EncodingType.PLAIN       # No compression
EncodingType.DICTIONARY  # Dictionary encoding
EncodingType.RLE         # Run-length encoding
EncodingType.FOR         # Frame of reference
EncodingType.BITPACK     # Bitpacking
EncodingType.DELTA       # Delta encoding
EncodingType.ZSTD        # Zstd compression
```

### ColumnStore

```python
from ladybugdb.compat import ColumnStore

store = ColumnStore(chunk_size=10000)

# Add columns
store.add_column("id", ids)
store.add_column("value", values)
store.add_column("label", labels)

# Get full column
col = store.get_column("value")

# Get chunks with pruning
chunks = store.get_chunks("value", min_val=100, max_val=200)

# Statistics
stats = store.stats()
```

### DictionaryBuilder

```python
from ladybugdb.compat import DictionaryBuilder

builder = DictionaryBuilder(max_size=65536)

idx = builder.add("hello")      # Returns index
indices = builder.add_many(["hello", "world", "hello"])

dictionary = builder.build()    # ["hello", "world"]
len(builder)                    # 2
"hello" in builder              # True
```

---

## Utilities

### Fingerprint Generation

```python
from ladybugdb.compat import content_to_fingerprint, random_fingerprint

# Deterministic from content
fp = content_to_fingerprint("Hello world")

# Random
fp = random_fingerprint()
```

### Chunking

```python
from ladybugdb.compat import chunk_text, chunk_tokens, semantic_chunk

# Fixed-size chunks with overlap
chunks = chunk_text(text, chunk_size=512, overlap=64)

# Token-based chunks
chunks = chunk_tokens(tokens, chunk_size=256, overlap=32)

# Semantic chunks (paragraph/sentence boundaries)
chunks = semantic_chunk(text, min_chunk=100, max_chunk=1000)
```

### Node Factory

```python
from ladybugdb.compat import create_node, NODE_TYPES

# Create by label
node = create_node("Thought", id="t1", content="An idea")

# Available types
print(NODE_TYPES.keys())  # Node, Thought, Concept, etc.
```

---

## Constants

```python
from ladybugdb.core import (
    VECTOR_BITS,      # 10000
    VECTOR_UINT64,    # 157
    VECTOR_BYTES,     # 1256
    EMBEDDING_DIM,    # 1024
    THINKING_STYLE_DIM,  # 7
)
```

---

<p align="center"><i>Full source code: <a href="https://github.com/AdaWorldAPI/ladybugdb">GitHub</a></i></p>
