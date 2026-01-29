# 🐞 LadybugDB

**One substrate. All operations. Zero copies.**

LadybugDB is a unified cognitive database that combines:
- **SQL** (DuckDB) for analytics
- **Cypher** (Graph) for relationship traversal
- **Vector Search** for semantic similarity
- **Hamming 10K** for resonance matching
- **Iceberg Versioning** for time-travel

Built on LanceDB + DuckDB with BtrBlocks compression and Procella-style query evaluation.

---

## Why LadybugDB?

```
BEFORE:                           AFTER:
┌─────────┐  ┌─────────┐         ┌─────────────────────────┐
│  Neo4j  │  │  Redis  │         │                         │
│ (graph) │  │  (KV)   │         │      LadybugDB          │
└────┬────┘  └────┬────┘         │                         │
     │            │              │  SQL + Cypher + Vector  │
┌────┴────┐  ┌────┴────┐         │  + Hamming + Versioning │
│  Jina   │  │ DuckDB  │         │                         │
│(vectors)│  │ (SQL)   │         │  All in one.            │
└─────────┘  └─────────┘         └─────────────────────────┘

4 systems → 1 system
4 serialization layers → 0 (Arrow zero-copy)
```

---

## Quick Start

```python
from ladybug import connect

# Connect to LadybugDB
db = connect("./my_db")

# Add nodes
db.add_node("thought_1", "Thought", content="Rails callbacks are tricky")
db.add_node("thought_2", "Thought", content="Callbacks have implicit ordering")

# Add causal edge
db.causes("thought_1", "thought_2", amplification=1.5)

# Query with SQL
db.query("SELECT * FROM nodes WHERE label = 'Thought'")

# Query with Cypher
db.query("MATCH (a)-[:CAUSES]->(b) RETURN b")

# Find similar (Hamming resonance)
db.resonate(fingerprint, threshold=0.6)

# Detect butterfly effects
db.detect_butterflies("config_change")
```

---

## Features

### 🔍 Unified Query Language

```sql
-- SQL
SELECT * FROM nodes WHERE qidx > 100

-- Cypher (transpiled to recursive CTE)
MATCH (a:Thought)-[:CAUSES*1..5]->(b:Thought)
WHERE a.qidx > 100
RETURN b

-- Vector search
SELECT * FROM nodes WHERE VECTOR_SEARCH(embedding, $query, 10)

-- Hamming resonance
SELECT * FROM nodes WHERE RESONATE(fingerprint, $fp, 0.6)
```

### 🦋 Butterfly Causality

```python
# Detect amplification chains
impact = db.impact_analysis("config_change")

print(f"Total affected: {impact['total_affected']}")
print(f"Max amplification: {impact['max_amplification']}x")
print(f"Butterfly effects: {impact['butterfly_effects']}")
```

### ⏰ Time Travel (Iceberg)

```python
# Checkout previous version
yesterday = db.checkout(version="2025-01-28")

# Compare
diff = db.diff(yesterday, db.latest)

# Rollback if needed
db.restore(version="2025-01-28")
```

### 🤖 Agent2Agent Orchestration

```python
from ladybug.agents import create_orchestrator

orch = create_orchestrator()

# Route task to appropriate agent
agent_id = orch.route_task("Excavate the User model")

# Agents share blackboard (LadybugDB)
# Automatic resonance-based context
# Structured handover protocol
```

---

## Performance

| Operation | Time | Throughput |
|-----------|------|------------|
| Point lookup | 0.1ms | 10K/sec |
| Hamming search (10K) | 0.5ms | 20M comparisons/sec |
| Vector ANN (10K) | 5ms | 2K queries/sec |
| Graph traversal (5 hops) | 5ms | 200/sec |
| Butterfly detection | 10ms | 100/sec |

Based on:
- BtrBlocks compression: 86 Gbit/s decode
- SIMD AVX-512 Hamming: 65M comparisons/sec
- Arrow zero-copy: No serialization overhead

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         QUERY LAYER                              │
│  SQL │ Cypher │ Vector │ Hamming │ Mixed                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────────┐
│                      EXECUTION LAYER                             │
│  DuckDB Engine + Custom UDFs (Hamming, Vector, Butterfly)       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────────┐
│                       STORAGE LAYER                              │
│  LanceDB (Arrow + BtrBlocks + Iceberg)                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Installation

```bash
pip install ladybugdb

# Or from source
git clone https://github.com/AdaWorldAPI/ladybugdb
cd ladybugdb
pip install -e .
```

---

## Schema

### Nodes (Universal)

| Column | Type | Description |
|--------|------|-------------|
| id | STRING | Unique identifier |
| label | STRING | Node type (Thought, Concept, etc.) |
| fingerprint | BINARY(1250) | 10K-bit Hamming vector |
| embedding | FLOAT[1024] | Jina semantic embedding |
| qidx | UINT8 | Qualia index (0-255) |
| thinking_style | FLOAT[7] | Cognitive style vector |
| content | STRING | Main content |
| properties | STRING | JSON properties |
| created_at | TIMESTAMP | Creation time |
| version | INT64 | Version number |

### Edges

| Column | Type | Description |
|--------|------|-------------|
| id | STRING | Unique identifier |
| from_id | STRING | Source node |
| to_id | STRING | Target node |
| type | STRING | Edge type (CAUSES, ENABLES, etc.) |
| weight | FLOAT | Edge weight |
| amplification | FLOAT | Butterfly amplification factor |
| properties | STRING | JSON properties |

### Edge Types

- **CAUSES**: Direct causation
- **AMPLIFIES**: Increases effect (>1x)
- **DAMPENS**: Decreases effect (<1x)
- **TRIGGERS**: Initiates cascade
- **ENABLES**: Makes possible
- **PREVENTS**: Blocks effect
- **SIMILAR_TO**: Semantic similarity
- **YIELDS**: Learning → Concept
- **HANDS_OVER**: Agent transfer

---

## Agent System

### Built-in Agents

| Agent | Role | Triggers |
|-------|------|----------|
| 🏺 Archaeologist | Excavate code patterns | "excavate", "find usages" |
| 🎯 ProductSage | Evaluate feature worth | "should we build", "priority" |
| 🧠 MetaLearner | Capture learning moments | "I just realized", "breakthrough" |
| 💻 Developer | Implement features | "implement", "code", "fix" |
| 👁️ Reviewer | Review changes | "review", "LGTM?" |

### Handover Protocol

```python
handover = agent_a.prepare_handover(
    to_agent="developer",
    next_steps=[
        "Review associations",
        "Extract service objects",
        "Add tests"
    ]
)

agent_b.receive_handover(handover)
# Agent B now has full context including:
# - Current task
# - Decisions made
# - Files modified
# - Blockers
# - Resonance hits (similar past situations)
```

---

## Integration with Ada

LadybugDB is the unified substrate for Ada v10:

```python
# Old (4 systems)
redis.hset("ada:thoughts:123", ...)
jina.index(embedding)
neo4j.create("Concept", ...)
duckdb.execute("SELECT ...")

# New (1 system)
db.add_node("thought_123", "Thought",
    fingerprint=fp,
    embedding=emb,
    content="...",
    qidx=200)

# Everything: SQL, graph, vectors, Hamming - all in one query
db.query("""
    MATCH (t:Thought)-[:CAUSES*1..5]->(c:Concept)
    WHERE RESONATE(t.fingerprint, $fp, 0.7)
    RETURN c
""")
```

---

## Files

```
ladybugdb/
├── ladybug/
│   ├── core/
│   │   ├── unified_engine.py    # Main query engine
│   │   ├── simd_kernel.py       # AVX-512 Hamming
│   │   ├── simd_fast.py         # FastVector, FastBatch
│   │   ├── l11_butterfly.py     # Butterfly causality
│   │   └── core.py              # LadybugDB class
│   │
│   ├── agents/
│   │   └── orchestrator.py      # Agent2Agent system
│   │
│   ├── schemas/
│   │   └── definitions.py       # PyArrow schemas
│   │
│   ├── prompts/
│   │   └── AGENT_PROMPTS.md     # Agent system prompts
│   │
│   └── integration/
│       └── INTEGRATION_PLAN.md  # Migration guide
│
├── SPEC.md                      # rDNA2 specification
├── LADYBUGDB_ALL_FOR_ONE.md     # 12-layer architecture
└── README.md                    # This file
```

---

## Why "LadybugDB"?

The ladybug (🐞) symbolizes:
- **Small but powerful** - Tiny insect, massive impact on ecosystems
- **Protective** - Guards against pests (bugs in code)
- **Lucky** - Good fortune in many cultures
- **Spotted pattern** - Like distributed nodes in a graph

Plus: **Ladybug → L11 → Butterfly Effect** 🦋

---

## License

Apache 2.0

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes
4. Run tests: `pytest`
5. Submit PR

---

*LadybugDB: One substrate to rule them all.* 🐞
