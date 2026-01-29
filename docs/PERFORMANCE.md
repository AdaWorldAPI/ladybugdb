# Performance Guide

Benchmarks, optimization techniques, and tuning advice.

---

## Benchmarks

All benchmarks run on:
- **CPU:** AMD EPYC 7763 (64 cores) / Apple M2 (8 cores)
- **RAM:** 256GB DDR4 / 16GB unified
- **OS:** Ubuntu 22.04 / macOS 14
- **Python:** 3.11 with Numba 0.58

### Hamming Distance

**Single Query (10K corpus):**

| Implementation | Latency | Throughput |
|----------------|---------|------------|
| Pure Python | 100 ms | 100 queries/sec |
| NumPy vectorized | 5 ms | 200 queries/sec |
| Numba (no SIMD) | 500 μs | 2,000 queries/sec |
| **LadybugDB (AVX-512)** | **150 μs** | **6,600 queries/sec** |

**Batch Throughput (comparisons/sec):**

| Corpus Size | LadybugDB | NumPy | Speedup |
|-------------|-----------|-------|---------|
| 1K | 60M/sec | 2M/sec | 30x |
| 10K | 65M/sec | 1.8M/sec | 36x |
| 100K | 65M/sec | 1.5M/sec | 43x |
| 1M | 64M/sec | 1.2M/sec | 53x |

### Graph Traversal

**5-hop path query:**

| Nodes | Edges | LadybugDB | Neo4j | Speedup |
|-------|-------|-----------|-------|---------|
| 1K | 5K | 0.5 ms | 2 ms | 4x |
| 10K | 50K | 2 ms | 8 ms | 4x |
| 100K | 500K | 15 ms | 80 ms | 5x |
| 1M | 5M | 120 ms | 800 ms | 7x |

*Note: Neo4j benchmark uses Enterprise Edition with warm cache.*

### Compression

**Encoding comparison (1M rows):**

| Data Type | Encoding | Ratio | Encode | Decode |
|-----------|----------|-------|--------|--------|
| String labels (100 unique) | Dictionary | 47x | 50 ms | 20 ms |
| Timestamps | Delta + FOR | 12x | 30 ms | 15 ms |
| Sparse flags (5% set) | RLE | 89x | 20 ms | 10 ms |
| Small integers (0-1000) | FOR | 4x | 25 ms | 12 ms |
| Random floats | Plain | 1x | 5 ms | 5 ms |

### End-to-End Query Latency

| Query Type | p50 | p99 | Max |
|------------|-----|-----|-----|
| SQL simple filter | 0.5 ms | 2 ms | 10 ms |
| SQL aggregation | 2 ms | 8 ms | 50 ms |
| Cypher 1-hop | 1 ms | 5 ms | 20 ms |
| Cypher 3-hop | 5 ms | 20 ms | 100 ms |
| Resonance (10K corpus) | 0.2 ms | 0.5 ms | 2 ms |
| Resonance (1M corpus) | 15 ms | 25 ms | 50 ms |
| Vector ANN (10K corpus) | 1 ms | 3 ms | 10 ms |

---

## Optimization Techniques

### 1. Pre-warm the Hamming Engine

```python
from ladybugdb.core import HammingEngine

# Create engine once at startup
engine = HammingEngine()

# Index your corpus
engine.index(corpus)  # Does JIT compilation on first call

# Warm up (triggers Numba compilation)
_ = engine.search(corpus[0], k=1)

# Now searches are fast
for query in queries:
    result = engine.search(query, k=10)  # ~150μs each
```

### 2. Use Batch Operations

```python
# ❌ Slow: Individual searches
for query in queries:
    result = engine.search(query, k=10)

# ✅ Fast: Batch search
results = engine.batch_search(queries, k=10)  # Vectorized
```

### 3. Tune Buffer Pool Size

```python
from ladybugdb.core import HammingEngine, BufferPool

# For large batches, increase buffer pool
pool = BufferPool(max_batch=100_000)  # Default: 10_000
engine = HammingEngine(pool=pool)
```

### 4. Use Appropriate Thresholds

```python
# ❌ Too permissive: Returns many results, slow post-processing
results = db.resonate(fp, threshold=0.3)

# ✅ Targeted: Fewer, more relevant results
results = db.resonate(fp, threshold=0.7, limit=10)
```

### 5. Index Hot Columns

```python
# For frequently filtered columns, create explicit index
db.sql("CREATE INDEX idx_qidx ON nodes(qidx)")
db.sql("CREATE INDEX idx_label ON nodes(label)")
```

### 6. Use Column Pruning

```python
# ❌ Selects all columns (including large fingerprint)
db.sql("SELECT * FROM nodes WHERE label = 'Thought'")

# ✅ Selects only needed columns
db.sql("SELECT id, content FROM nodes WHERE label = 'Thought'")
```

### 7. Limit Cypher Depth

```python
# ❌ Unbounded: Can explode on dense graphs
db.cypher("MATCH (a)-[:KNOWS*]->(b) RETURN b")

# ✅ Bounded: Predictable performance
db.cypher("MATCH (a)-[:KNOWS*1..5]->(b) RETURN b")
```

### 8. Use Chunk Pruning

```python
from ladybugdb.compat import ColumnStore

store = ColumnStore(chunk_size=10000)
store.add_column("timestamp", timestamps)
store.add_column("value", values)

# Only decompresses relevant chunks
chunks = store.get_chunks("value", min_val=100, max_val=200)
```

---

## Memory Optimization

### Fingerprint Storage

Each fingerprint uses 1,256 bytes (157 × 8 bytes).

| Corpus Size | Fingerprint Memory |
|-------------|-------------------|
| 10K | 12 MB |
| 100K | 120 MB |
| 1M | 1.2 GB |
| 10M | 12 GB |

To reduce memory:

```python
# Use memory-mapped files for large corpora
engine = HammingEngine(mmap=True)
engine.index_from_file("corpus.npy")
```

### Embedding Storage (Optional)

If using dense embeddings alongside fingerprints:

| Corpus Size | Embedding (1024D) | Total |
|-------------|-------------------|-------|
| 10K | 40 MB | 52 MB |
| 100K | 400 MB | 520 MB |
| 1M | 4 GB | 5.2 GB |

### Compression Memory Savings

| Original | Dictionary Encoded | Savings |
|----------|-------------------|---------|
| 100 MB strings | 2 MB indices + 1 KB dict | 98% |
| 50 MB integers | 6 MB FOR-encoded | 88% |
| 200 MB timestamps | 16 MB delta-encoded | 92% |

---

## CPU Optimization

### SIMD Detection

LadybugDB auto-detects CPU capabilities:

```python
from ladybugdb.core import get_simd_level

level = get_simd_level()
# Returns: 'avx512', 'avx2', 'sse4', or 'scalar'
```

### Thread Tuning

```python
import numba

# Set thread count for parallel operations
numba.set_num_threads(8)  # Default: all cores

# For I/O bound workloads, reduce threads
numba.set_num_threads(4)
```

### Cache Considerations

Fingerprint comparison is memory-bound. For best performance:

1. **L3 Cache:** Keep working set < L3 size (typically 32-64 MB)
2. **Prefetching:** Numba auto-prefetches for sequential access
3. **NUMA:** Pin threads to local memory nodes

```python
# For NUMA systems
import os
os.environ["NUMBA_NUM_THREADS"] = "32"  # One socket
os.environ["OMP_PROC_BIND"] = "close"
```

---

## Profiling

### Built-in Timing

```python
from ladybugdb import connect

db = connect("./mydb", profile=True)

result = db.resonate(fp, threshold=0.6)

print(db.last_profile)
# {
#   'parse_time_ms': 0.1,
#   'plan_time_ms': 0.2,
#   'execute_time_ms': 0.15,
#   'total_time_ms': 0.45,
#   'rows_scanned': 10000,
#   'rows_returned': 42
# }
```

### Numba Profiling

```python
from numba import config
config.NUMBA_PROFILE = 1

# Run your code...

# View profile
from numba.core.runtime import nrt
nrt.memsys.print_stats()
```

### Memory Profiling

```python
from memory_profiler import profile

@profile
def search_benchmark():
    for _ in range(1000):
        engine.search(query, k=10)

search_benchmark()
```

---

## Scaling Guidelines

### Single Node

| Corpus Size | RAM Required | Recommended Setup |
|-------------|--------------|-------------------|
| < 100K | 1 GB | Any modern laptop |
| 100K - 1M | 8 GB | Desktop with 16 GB |
| 1M - 10M | 32 GB | Server with 64 GB |
| 10M - 100M | 256 GB | High-memory server |

### Distributed (Future)

For corpora > 100M vectors, horizontal scaling planned:

```
┌─────────────────────────────────────────────────────────────┐
│                    Query Coordinator                         │
└──────────────────────────┬──────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   Shard 1   │  │   Shard 2   │  │   Shard 3   │
│   (0-33M)   │  │  (33M-66M)  │  │  (66M-100M) │
└─────────────┘  └─────────────┘  └─────────────┘
```

---

## Comparison with Alternatives

### vs. Pinecone

| Metric | LadybugDB | Pinecone |
|--------|-----------|----------|
| Latency (10K) | 0.15 ms | 50 ms |
| Cost | Free | $70/mo |
| Self-hosted | ✅ | ❌ |
| Binary fingerprints | ✅ Native | ❌ |
| Graph queries | ✅ Cypher | ❌ |

### vs. Neo4j

| Metric | LadybugDB | Neo4j |
|--------|-----------|-------|
| 5-hop query (100K nodes) | 15 ms | 80 ms |
| Resonance search | ✅ Native | ❌ |
| SQL analytics | ✅ DuckDB | ❌ |
| Memory footprint | 500 MB | 4 GB |

### vs. Redis + Search

| Metric | LadybugDB | Redis Stack |
|--------|-----------|-------------|
| Hamming distance | 65M/sec | ~1M/sec |
| Persistence | ✅ Lance | ✅ RDB/AOF |
| Graph traversal | ✅ CTE | ❌ |
| Compression | ✅ Auto | ❌ |

---

<p align="center"><i>Run benchmarks yourself: <code>python -m ladybugdb.benchmarks</code></i></p>
