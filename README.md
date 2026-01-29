# 🐞 LadybugDB

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**Unified cognitive substrate: SQL + Cypher + Vector + Hamming over LanceDB.**

*One database. All operations. Zero copies.*

---

## Why LadybugDB?

Modern AI systems need four query types:

| Need | Traditional | LadybugDB |
|------|-------------|-----------|
| Analytics | PostgreSQL | ✅ DuckDB SQL |
| Graphs | Neo4j | ✅ Cypher → Recursive CTEs |
| Vectors | Pinecone | ✅ LanceDB ANN |
| Fingerprints | Custom code | ✅ AVX-512 SIMD |

That's 4 databases, 4 sync mechanisms, 4 points of failure.

**LadybugDB collapses them into one.** Zero-copy operations. 65M Hamming comparisons/sec. Familiar APIs.

---

## Installation

```bash
pip install ladybugdb
```

**With extras:**
```bash
pip install ladybugdb[all]       # Everything
pip install ladybugdb[numba]     # SIMD acceleration
pip install ladybugdb[jina]      # Jina embeddings
```

**From source:**
```bash
git clone https://github.com/AdaWorldAPI/ladybugdb.git
cd ladybugdb && pip install -e ".[dev]"
```

---

## Quick Start

### Connect and Query

```python
from ladybugdb import connect

db = connect("./mydb")

# SQL
db.sql("SELECT * FROM nodes WHERE label = 'Thought'")

# Cypher (auto-transpiled)
db.cypher("MATCH (a)-[:CAUSES*1..5]->(b) RETURN b")

# Resonance (Hamming similarity)
db.resonate(fingerprint, threshold=0.6)

# Vector search
db.vector_search(embedding, k=10)
```

### Jina-Compatible API

```python
from ladybugdb.compat import JinaClient, Document

client = JinaClient()
client.index([
    Document(id="1", content="Quantum entanglement"),
    Document(id="2", content="Classical mechanics"),
])
results = client.search("quantum", top_k=10)
```

### Neo4j-Compatible API

```python
from ladybugdb.compat import GraphDatabase

driver = GraphDatabase.driver("ladybug://./mydb")
with driver.session() as session:
    result = session.run("""
        MATCH (a:Config)-[:CAUSES*1..5]->(b:Failure)
        RETURN b, length(path) as depth
    """)
```

### DTOs (Pydantic-Style)

```python
from ladybugdb.compat import Node, Thought, Handover

node = Node(id="t1", content="Sky is blue", qidx=180)
node.fingerprint  # Auto-computed 10K bits

handover = Handover(
    from_agent="Archaeologist",
    to_agent="Developer", 
    task="Fix N+1 query"
)
print(handover.to_markdown())  # For LLM context
```

---

## Core Features

### 🔍 Unified Query Engine

One interface, all query types:

```python
# SQL analytics
db.query("SELECT label, COUNT(*) FROM nodes GROUP BY label")

# Graph traversal  
db.query("MATCH path = (a)-[*1..10]->(b) RETURN path")

# Semantic search
db.query("VECTOR_SEARCH(embedding, 10)")

# Resonance matching
db.query("RESONATE(fingerprint, 0.6)")
```

### ⚡ Zero-Overhead Hamming

```python
from ladybugdb.core import HammingEngine

engine = HammingEngine()
engine.index(corpus)  # Index once

# Search: 65M comparisons/sec, zero allocation
result = engine.search(query, k=10)
```

**Performance:**
| Corpus | Time | Throughput |
|--------|------|------------|
| 10K | 150μs | 65M/sec |
| 100K | 1.5ms | 65M/sec |
| 1M | 15ms | 65M/sec |

### 🦋 Butterfly Detection

Track causal amplification chains:

```python
butterflies = db.detect_butterflies(
    source="config_change",
    threshold=2.0,  # amplification > 2x
    max_depth=10
)

for path, amp in butterflies:
    print(f"{amp:.1f}x: {' → '.join(path)}")
```

### 🗜️ Automatic Compression

```python
from ladybugdb.compat import Compressor

compressor = Compressor()
block = compressor.compress(data)
# Auto-selects: Dictionary, RLE, FOR, Delta, or Bitpack
print(f"{block.compression_ratio:.0f}x smaller")
```

---

## Documentation

| Document | Description |
|----------|-------------|
| **[Quickstart](docs/QUICKSTART.md)** | 5-minute getting started guide |
| **[API Reference](docs/API.md)** | Complete API documentation |
| **[Architecture](docs/ARCHITECTURE.md)** | System internals |
| **[Compatibility](docs/COMPATIBILITY.md)** | Jina / Neo4j / Pydantic APIs |
| **[Performance](docs/PERFORMANCE.md)** | Benchmarks and tuning |
| **[Migration](docs/MIGRATION.md)** | From Neo4j, Pinecone, etc. |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                  Unified Query Interface                 │
│              SQL │ Cypher │ Vector │ Hamming            │
├──────────────────────────────────────────────────────────┤
│ Cypher Transpiler │ Resonance Engine │ Vector Index     │
│ (Recursive CTEs)  │ (AVX-512 SIMD)   │ (HNSW/IVF)      │
├──────────────────────────────────────────────────────────┤
│                    DuckDB SQL Engine                     │
├──────────────────────────────────────────────────────────┤
│                   LanceDB Storage Layer                  │
│            (Lance Format + BtrBlocks Compression)        │
└──────────────────────────────────────────────────────────┘
```

---

## Requirements

- Python 3.9+
- NumPy 1.20+
- DuckDB 0.9+
- LanceDB 0.3+ (optional)
- Numba 0.58+ (optional, for SIMD)

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
git clone https://github.com/AdaWorldAPI/ladybugdb.git
cd ladybugdb
pip install -e ".[dev]"
pytest tests/
```

---

## License

Apache License 2.0 — see [LICENSE](LICENSE)

---

## Acknowledgments

Built on: [LanceDB](https://lancedb.com/), [DuckDB](https://duckdb.org/), [Numba](https://numba.pydata.org/)

Inspired by: [BtrBlocks](https://www.cs.cit.tum.de/dis/research/btrblocks/), [Procella](https://research.google/pubs/pub48388/)

---

<p align="center"><i>One database. All operations. Zero copies.</i></p>
