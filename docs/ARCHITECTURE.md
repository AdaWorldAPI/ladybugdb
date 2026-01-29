# Architecture

Deep dive into how LadybugDB works under the hood.

---

## Overview

LadybugDB is a **unified cognitive substrate** that combines four query paradigms:

```
┌─────────────────────────────────────────────────────────────┐
│                    Query Interface Layer                     │
│                                                             │
│   db.sql()    db.cypher()    db.resonate()    db.vector()  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    Query Router                              │
│                                                             │
│  • Detects query type (SQL/Cypher/Resonance/Vector)        │
│  • Transpiles Cypher → SQL (recursive CTEs)                │
│  • Routes to appropriate engine                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
┌─────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   DuckDB    │  │  Hamming SIMD   │  │   LanceDB       │
│   Engine    │  │  Engine         │  │   Engine        │
│             │  │                 │  │                 │
│  • SQL      │  │  • Fingerprint  │  │  • Dense vector │
│  • Analytics│  │  • 65M cmp/sec  │  │  • ANN search   │
│  • Joins    │  │  • Zero alloc   │  │  • HNSW/IVF     │
└──────┬──────┘  └────────┬────────┘  └────────┬────────┘
       │                  │                    │
       └──────────────────┼────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    Storage Layer                             │
│                                                             │
│  Lance Columnar Format + BtrBlocks-style Compression        │
│                                                             │
│  • Zero-copy between engines                                │
│  • Automatic encoding selection                             │
│  • Chunk-level statistics for pruning                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Query Router

The query router inspects incoming queries and routes them appropriately:

```python
def route_query(query: str) -> Engine:
    if query.strip().upper().startswith("MATCH"):
        # Cypher → transpile → DuckDB
        sql = CypherTranspiler.transpile(query)
        return DuckDBEngine(sql)
    
    elif query.strip().upper().startswith("RESONATE"):
        # Hamming similarity search
        return HammingEngine(query)
    
    elif query.strip().upper().startswith("VECTOR"):
        # Dense vector ANN
        return LanceEngine(query)
    
    else:
        # Standard SQL
        return DuckDBEngine(query)
```

### 2. Cypher Transpiler

Converts Cypher graph queries to SQL using recursive CTEs.

**Simple Pattern:**
```cypher
MATCH (a:Person)-[:KNOWS]->(b:Person)
WHERE a.age > 25
RETURN b.name
```

Becomes:
```sql
SELECT b.name
FROM nodes a, edges e, nodes b
WHERE a.label = 'Person'
  AND b.label = 'Person'
  AND e.from_id = a.id
  AND e.to_id = b.id
  AND e.type = 'KNOWS'
  AND a.age > 25
```

**Variable-Length Pattern:**
```cypher
MATCH (a:Config)-[:CAUSES*1..5]->(b:Failure)
RETURN b, length(path) as depth
```

Becomes:
```sql
WITH RECURSIVE traverse AS (
    -- Base case
    SELECT 
        n.id,
        ARRAY[n.id] AS path,
        1.0 AS amplification,
        0 AS depth
    FROM nodes n
    WHERE n.label = 'Config'
    
    UNION ALL
    
    -- Recursive case
    SELECT
        n.id,
        t.path || n.id,
        t.amplification * COALESCE(e.amplification, 1.0),
        t.depth + 1
    FROM traverse t
    JOIN edges e ON t.id = e.from_id AND e.type = 'CAUSES'
    JOIN nodes n ON e.to_id = n.id
    WHERE t.depth < 5
      AND n.id != ALL(t.path)  -- Cycle prevention
)
SELECT * FROM traverse t
JOIN nodes n ON t.id = n.id
WHERE t.depth >= 1 AND n.label = 'Failure'
```

### 3. Hamming SIMD Engine

The heart of resonance search — AVX-512 accelerated Hamming distance.

**Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                    BufferPool                                │
│                                                             │
│  Pre-allocated at startup:                                  │
│  • distances[max_batch]     - Hamming distances             │
│  • indices[max_batch]       - Result indices                │
│  • temp[VECTOR_UINT64]      - Scratch space                 │
│                                                             │
│  Hot path uses views → Zero malloc during search            │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 Numba JIT Kernels                            │
│                                                             │
│  @njit(cache=True, fastmath=True, parallel=True)           │
│                                                             │
│  • _popcount64()      - Hardware POPCNT                     │
│  • _hamming_kernel()  - Single distance                     │
│  • _hamming_batch()   - Parallel batch (prange)            │
│  • _topk_kernel()     - Partial sort for k-NN              │
└─────────────────────────────────────────────────────────────┘
```

**Key Optimizations:**

1. **Pre-allocated BufferPool**: All buffers created once at startup
2. **Numba @njit**: Compiles to native machine code
3. **cache=True**: Compilation cached to disk
4. **fastmath=True**: Enables SIMD-friendly float ops
5. **parallel=True**: Uses all CPU cores via prange
6. **inline='always'**: Eliminates function call overhead

**Fingerprint Format:**

```
┌─────────────────────────────────────────────────────────────┐
│                    10,000-bit Fingerprint                    │
│                                                             │
│  Stored as: np.ndarray[157] of uint64                       │
│  157 × 64 = 10,048 bits (48 bits padding)                   │
│                                                             │
│  Generation: SHA-256(content) → LFSR expansion → 10K bits   │
└─────────────────────────────────────────────────────────────┘
```

### 4. VSA Operations

Vector Symbolic Architecture operations for cognitive computing:

```python
# BIND (XOR) - Creates compound representation
red_apple = bind(color_red, object_apple)

# UNBIND - Recovers components
recovered_apple = unbind(red_apple, color_red)  # ≈ object_apple

# BUNDLE (Majority Vote) - Creates prototype
generic_cat = bundle([cat1, cat2, cat3])

# PERMUTE - Encodes position/sequence
sequence = permute(word, position=3)
```

**Implementation:**

```python
@njit(cache=True, parallel=True)
def _bundle_kernel(vectors: np.ndarray, out: np.ndarray) -> None:
    """Majority vote bundling."""
    n_vectors = vectors.shape[0]
    threshold = n_vectors // 2
    
    for i in prange(VECTOR_UINT64):
        result = np.uint64(0)
        for bit in range(64):
            count = 0
            mask = np.uint64(1) << np.uint64(bit)
            for v in range(n_vectors):
                if vectors[v, i] & mask:
                    count += 1
            if count > threshold:
                result |= mask
        out[i] = result
```

### 5. Compression Layer

BtrBlocks-inspired automatic encoding selection:

```
┌─────────────────────────────────────────────────────────────┐
│                    Encoding Selector                         │
│                                                             │
│  Input data → Analyze → Select best encoding:               │
│                                                             │
│  • Dictionary: Low cardinality (< 256 unique)              │
│  • RLE: Many repeated values (runs > 50%)                  │
│  • FOR: Small integers (< 16 bits range)                   │
│  • Delta: Sequential/sorted data                           │
│  • Bitpack: Dense booleans/flags                           │
│  • Plain: Fallback for incompressible data                 │
└─────────────────────────────────────────────────────────────┘
```

**Typical Compression Ratios:**

| Data Type | Best Encoding | Ratio |
|-----------|---------------|-------|
| String labels | Dictionary | 10-100x |
| Timestamps | Delta + FOR | 5-20x |
| Sparse flags | RLE | 20-100x |
| Small integers | FOR | 2-8x |
| Fingerprints | Plain | 1x (already dense) |

---

## Data Flow

### Write Path

```
User creates Node
        │
        ▼
┌─────────────────┐
│ Fingerprint Gen │ ← SHA-256 + LFSR expansion
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Arrow Conversion│ ← Zero-copy to columnar
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Compression     │ ← Auto-select encoding
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Lance Storage   │ ← Write to disk
└─────────────────┘
```

### Read Path (Resonance Query)

```
User calls resonate(fingerprint)
        │
        ▼
┌─────────────────────────────────────────┐
│ BufferPool provides pre-allocated views │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ Numba kernel: parallel Hamming distance │
│ (65M comparisons/sec)                   │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ Top-K selection (partial sort)          │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ Threshold filtering                     │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ Return SearchResult                     │
└─────────────────────────────────────────┘
```

### Read Path (Cypher Query)

```
User calls cypher("MATCH (a)-[:CAUSES*1..5]->(b)")
        │
        ▼
┌─────────────────────────────────────────┐
│ CypherParser: Extract pattern           │
│ • Nodes: [(a, label), (b, label)]      │
│ • Edges: [(CAUSES, 1..5)]              │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ CypherTranspiler: Generate SQL          │
│ • Variable-length → Recursive CTE       │
│ • Simple → JOINs                        │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ DuckDB: Execute SQL                     │
│ • CTE unrolled by optimizer             │
│ • Parallel execution                    │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ Return results                          │
└─────────────────────────────────────────┘
```

---

## Memory Layout

### Node Table

```
┌─────────────────────────────────────────────────────────────┐
│ Column         │ Type        │ Encoding    │ Notes         │
├────────────────┼─────────────┼─────────────┼───────────────┤
│ id             │ string      │ dictionary  │ Primary key   │
│ label          │ string      │ dictionary  │ Low card      │
│ content        │ string      │ plain/zstd  │ Variable len  │
│ fingerprint    │ fixed[1256] │ plain       │ 157 × uint64  │
│ embedding      │ float32[D]  │ plain       │ Optional      │
│ qidx           │ uint8       │ plain       │ 0-255         │
│ properties     │ string      │ plain       │ JSON blob     │
│ created_at     │ timestamp   │ delta       │ Sequential    │
│ version        │ uint32      │ FOR         │ Small ints    │
└─────────────────────────────────────────────────────────────┘
```

### Edge Table

```
┌─────────────────────────────────────────────────────────────┐
│ Column         │ Type        │ Encoding    │ Notes         │
├────────────────┼─────────────┼─────────────┼───────────────┤
│ id             │ string      │ dictionary  │ Derived       │
│ from_id        │ string      │ dictionary  │ FK to nodes   │
│ to_id          │ string      │ dictionary  │ FK to nodes   │
│ type           │ string      │ dictionary  │ Low card      │
│ weight         │ float32     │ plain       │ Default 1.0   │
│ amplification  │ float32     │ plain       │ For butterfly │
│ confidence     │ float32     │ plain       │ 0-1           │
│ properties     │ string      │ plain       │ JSON blob     │
│ created_at     │ timestamp   │ delta       │ Sequential    │
└─────────────────────────────────────────────────────────────┘
```

---

## Concurrency Model

```
┌─────────────────────────────────────────────────────────────┐
│                    Connection Pool                           │
│                                                             │
│  • One DuckDB connection per thread                         │
│  • Shared BufferPool (thread-local views)                   │
│  • Lance handles concurrent writes with MVCC                │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Write Path                                │
│                                                             │
│  • Single writer (Lance handles serialization)              │
│  • Optimistic concurrency for updates                       │
│  • Version column for conflict detection                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Read Path                                 │
│                                                             │
│  • Unlimited concurrent readers                             │
│  • Snapshot isolation (MVCC)                                │
│  • No locks during Hamming search                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Extension Points

### Custom Encoders

```python
from ladybugdb.compression import Encoder, register_encoder

class MyEncoder(Encoder):
    encoding_type = EncodingType.CUSTOM
    
    def encode(self, data: np.ndarray) -> bytes:
        ...
    
    def decode(self, data: bytes) -> np.ndarray:
        ...

register_encoder(MyEncoder)
```

### Custom Query Types

```python
from ladybugdb.query import QueryHandler, register_handler

class MyQueryHandler(QueryHandler):
    pattern = r"^MYQUERY\s+"
    
    def execute(self, query: str, db: LadybugEngine):
        ...

register_handler(MyQueryHandler)
```

### Custom Node Types

```python
from ladybugdb.compat import Node, NODE_TYPES

@dataclass
class MyNode(Node):
    label: str = "MyNode"
    my_field: str = ""

NODE_TYPES["MyNode"] = MyNode
```

---

## Performance Characteristics

| Operation | Complexity | Typical Latency |
|-----------|------------|-----------------|
| Single Hamming | O(D) | 50 ns |
| Batch Hamming (N) | O(N×D) | 15 ns/vector |
| k-NN search | O(N×D + N log k) | 150 μs (10K corpus) |
| SQL simple | O(N) | 1 ms |
| Cypher 1-hop | O(E) | 2 ms |
| Cypher 5-hop | O(E^5) bounded | 20 ms |
| Compression | O(N) | 10 μs/KB |
| Decompression | O(N) | 5 μs/KB |

Where:
- D = 10,000 bits (fingerprint dimension)
- N = corpus size
- E = edge count

---

<p align="center"><i>See <a href="PERFORMANCE.md">Performance Guide</a> for optimization tips.</i></p>
