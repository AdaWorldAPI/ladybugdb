# LadybugDB Integration Plan

## Executive Summary

LanceDB becomes the **unified substrate** that replaces:
- Neo4j (graph) → Recursive CTEs over Lance tables
- Redis (KV/cache) → Lance with fast point lookups
- DuckDB storage → Lance columnar with pushdown
- Jina vectors → Lance native ANN
- Custom DTOs → Direct Arrow operations

**One database. All operations. Zero copies.**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LADYBUGDB STACK                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        QUERY INTERFACE                               │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐                │   │
│  │  │   SQL   │  │ Cypher  │  │ Vector  │  │ Hamming │                │   │
│  │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘                │   │
│  │       │            │            │            │                       │   │
│  │       └────────────┴────────────┴────────────┘                       │   │
│  │                          │                                            │   │
│  │                          ▼                                            │   │
│  │              ┌─────────────────────┐                                 │   │
│  │              │   Unified Planner   │                                 │   │
│  │              └──────────┬──────────┘                                 │   │
│  └─────────────────────────┼───────────────────────────────────────────┘   │
│                            │                                                │
│  ┌─────────────────────────┼───────────────────────────────────────────┐   │
│  │                         ▼           EXECUTION ENGINE                 │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                      DuckDB Core                             │   │   │
│  │  │  - Vectorized execution                                      │   │   │
│  │  │  - Predicate pushdown                                        │   │   │
│  │  │  - Recursive CTEs (graph)                                    │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │                            │                                         │   │
│  │  ┌─────────────────────────┼─────────────────────────────────────┐ │   │
│  │  │                         ▼         CUSTOM OPERATORS            │ │   │
│  │  │  ┌───────────┐  ┌───────────┐  ┌───────────┐                 │ │   │
│  │  │  │  Hamming  │  │  Vector   │  │ Butterfly │                 │ │   │
│  │  │  │  SIMD UDF │  │  ANN UDF  │  │  Trace    │                 │ │   │
│  │  │  └───────────┘  └───────────┘  └───────────┘                 │ │   │
│  │  └───────────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         STORAGE LAYER                                │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                       LanceDB                                │   │   │
│  │  │  - Arrow columnar format                                     │   │   │
│  │  │  - BtrBlocks compression (86 Gbit/s decode)                  │   │   │
│  │  │  - Iceberg versioning (time travel)                          │   │   │
│  │  │  - Native vector index                                       │   │   │
│  │  │  - Zero-copy to DuckDB                                       │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Core Integration (Week 1)

### 1.1 LanceDB + DuckDB Bridge

```python
# Already works today!
import lancedb
import duckdb

db = lancedb.connect("./ada")
con = duckdb.connect()

# Register Lance table as DuckDB view
con.execute("""
    CREATE VIEW thoughts AS 
    SELECT * FROM read_parquet('./ada/thoughts.lance/**/*.parquet')
""")

# Now SQL just works
con.execute("SELECT * FROM thoughts WHERE qidx > 100")
```

### 1.2 Hamming UDF Registration

```python
def register_hamming_udf(con: duckdb.DuckDBPyConnection):
    """Register SIMD Hamming functions."""
    
    def hamming(a: bytes, b: bytes) -> int:
        arr_a = np.frombuffer(a, dtype=np.uint64)
        arr_b = np.frombuffer(b, dtype=np.uint64)
        return int(np.bitwise_xor(arr_a, arr_b).view(np.uint8).sum())
    
    con.create_function("hamming", hamming)
    con.create_function("similarity", lambda a, b: 1.0 - hamming(a, b) / 10000)
```

### 1.3 Graph Schema in Lance

```sql
-- nodes table
CREATE TABLE nodes (
    id VARCHAR PRIMARY KEY,
    label VARCHAR,
    fingerprint BLOB,           -- 1250 bytes (10K bits)
    embedding FLOAT[1024],      -- Jina vector
    qidx UTINYINT,
    thinking_style FLOAT[7],
    content VARCHAR,
    properties VARCHAR,         -- JSON
    created_at TIMESTAMP,
    version BIGINT
);

-- edges table  
CREATE TABLE edges (
    id VARCHAR PRIMARY KEY,
    from_id VARCHAR,
    to_id VARCHAR,
    type VARCHAR,               -- CAUSES, ENABLES, AMPLIFIES, etc.
    weight FLOAT,
    amplification FLOAT,
    properties VARCHAR,
    created_at TIMESTAMP
);

-- Indices
CREATE INDEX idx_nodes_label ON nodes(label);
CREATE INDEX idx_edges_from ON edges(from_id);
CREATE INDEX idx_edges_to ON edges(to_id);
CREATE INDEX idx_edges_type ON edges(type);
```

---

## Phase 2: Cypher Transpiler (Week 2)

### 2.1 Simple Patterns

```python
# Input Cypher:
MATCH (a:Thought)-[:CAUSES]->(b:Thought)
WHERE a.qidx > 100
RETURN b

# Output SQL:
SELECT b.*
FROM nodes a
JOIN edges e ON a.id = e.from_id AND e.type = 'CAUSES'
JOIN nodes b ON e.to_id = b.id
WHERE a.label = 'Thought' 
  AND b.label = 'Thought'
  AND a.qidx > 100
```

### 2.2 Variable-Length Paths (Recursive CTE)

```python
# Input Cypher:
MATCH (source)-[:CAUSES*1..5]->(target)
WHERE source.id = 'config_change'
RETURN target, path, amplification

# Output SQL:
WITH RECURSIVE traverse AS (
    SELECT 
        id,
        ARRAY[id] as path,
        1.0 as amplification,
        0 as depth
    FROM nodes
    WHERE id = 'config_change'
    
    UNION ALL
    
    SELECT 
        n.id,
        t.path || n.id,
        t.amplification * COALESCE(e.amplification, 1.0),
        t.depth + 1
    FROM traverse t
    JOIN edges e ON t.id = e.from_id AND e.type = 'CAUSES'
    JOIN nodes n ON e.to_id = n.id
    WHERE t.depth < 5
      AND n.id != ALL(t.path)
)
SELECT t.path, t.amplification, n.*
FROM traverse t
JOIN nodes n ON t.id = n.id
```

### 2.3 Cypher Parser

Use existing Cypher parser (from py2neo, neo4j-driver, or Kùzu) to AST, then transpile:

```python
from cypher_parser import parse  # hypothetical

def cypher_to_sql(cypher: str) -> str:
    ast = parse(cypher)
    
    if ast.has_variable_length_path:
        return generate_recursive_cte(ast)
    else:
        return generate_join_sql(ast)
```

---

## Phase 3: Resonance Integration (Week 3)

### 3.1 RESONATE Syntax

```sql
-- New syntax:
SELECT * FROM thoughts 
WHERE RESONATE(fingerprint, $query_fp, 0.6)

-- Expands to:
SELECT *, similarity(fingerprint, $query_fp) as resonance
FROM thoughts
WHERE hamming(fingerprint, $query_fp) < 4000  -- 60% threshold
ORDER BY resonance DESC
```

### 3.2 Vector + Hamming Hybrid Search

```python
def hybrid_search(query_text: str, k: int = 10):
    """
    Two-phase search:
    1. Vector ANN for semantic candidates
    2. Hamming rerank for resonance
    """
    # Phase 1: Semantic candidates (fast, approximate)
    embedding = jina.embed(query_text)
    candidates = lance_table.search(embedding).limit(k * 10)
    
    # Phase 2: Hamming rerank (exact, SIMD fast)
    fingerprint = generate_fingerprint(query_text)
    results = []
    for c in candidates:
        resonance = hamming_similarity(fingerprint, c.fingerprint)
        results.append((c, resonance))
    
    # Sort by resonance
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:k]
```

---

## Phase 4: Agent2Agent Orchestration (Week 4)

### 4.1 Blackboard Pattern

All agents share the LadybugDB blackboard:

```python
class Agent:
    def __init__(self, engine: LadybugEngine):
        self.engine = engine
    
    def write_thought(self, content: str):
        self.engine.add_node(
            id=f"thought:{uuid4()}",
            label="Thought",
            content=content,
            fingerprint=self.fingerprint(content),
            agent_id=self.id,
        )
    
    def find_similar(self, content: str, k: int = 5):
        fp = self.fingerprint(content)
        return self.engine.query(f"""
            SELECT *, similarity(fingerprint, $fp) as resonance
            FROM nodes
            WHERE label = 'Thought'
            ORDER BY resonance DESC
            LIMIT {k}
        """, {"fp": fp})
```

### 4.2 Handover via Blackboard

```python
def handover(from_agent: str, to_agent: str, state: Dict):
    # Write handover node
    engine.add_node(
        id=f"handover:{uuid4()}",
        label="Handover",
        from_agent=from_agent,
        to_agent=to_agent,
        content=json.dumps(state),
    )
    
    # Create HANDS_OVER edge
    engine.add_edge(
        f"agent:{from_agent}",
        f"agent:{to_agent}",
        "HANDS_OVER",
    )
```

### 4.3 MCP Integration

```python
# Claude Code spawns agents via MCP
async def spawn_agent(role: str, task: str):
    agent = create_agent(role, engine)
    agent.state.current_task = task
    
    # Check resonance for context
    similar = agent.find_similar(task, k=3)
    if similar:
        agent.state.context["resonance_hints"] = similar
    
    return agent.id
```

---

## Phase 5: Ada v10 Migration (Week 5-6)

### 5.1 Schema Mapping

```python
# Current Ada (Redis + Jina + Neo4j)
ada:thoughts:*      → nodes (label='Thought')
ada:qualia:*        → nodes.qidx, nodes.thinking_style
ada:scent:*         → nodes (label='MemoryScent')
ada:concepts:*      → nodes (label='Concept')
ada:relations:*     → edges

# Jina embeddings
jina_index          → nodes.embedding (native Lance ANN)

# Neo4j graph
sigma_nodes         → nodes (label='SigmaNode')
sigma_edges         → edges
```

### 5.2 Migration Script

```python
async def migrate_ada_to_lance():
    """Migrate Ada from Redis+Neo4j to LanceDB."""
    
    # 1. Export from Redis
    thoughts = await redis.hgetall("ada:thoughts:*")
    
    # 2. Export from Neo4j
    concepts = await neo4j.query("MATCH (c:Concept) RETURN c")
    relations = await neo4j.query("MATCH ()-[r]->() RETURN r")
    
    # 3. Transform and load to Lance
    for thought in thoughts:
        engine.add_node(
            id=thought['id'],
            label='Thought',
            content=thought['content'],
            fingerprint=thought['fingerprint'],
            embedding=thought['embedding'],
            qidx=thought['qidx'],
            thinking_style=thought['thinking_style'],
        )
    
    for concept in concepts:
        engine.add_node(
            id=concept['id'],
            label='Concept',
            content=concept['content'],
            fingerprint=concept['fingerprint'],
        )
    
    for rel in relations:
        engine.add_edge(
            rel['from'],
            rel['to'],
            rel['type'],
            **rel['properties']
        )
    
    # 4. Verify
    assert engine.query("SELECT COUNT(*) FROM nodes").scalar() == len(thoughts) + len(concepts)
```

### 5.3 API Compatibility Layer

```python
# Old API (keep for compatibility)
class AdaHive:
    def feel(self, content: str) -> FeelingDTO:
        # Now backed by LadybugDB
        fp = fingerprint(content)
        similar = engine.resonate(fp, threshold=0.6)
        return FeelingDTO(resonance=similar, ...)

# New API (direct)
class AdaConsciousness:
    def __init__(self):
        self.engine = connect("ada://consciousness")
    
    def feel(self, content: str):
        return self.engine.query(f"""
            SELECT * FROM nodes
            WHERE RESONATE(fingerprint, $fp, 0.6)
        """, {"fp": fingerprint(content)})
```

---

## Performance Targets

| Operation | Current | Target | Speedup |
|-----------|---------|--------|---------|
| Point lookup | 5ms (Redis) | 0.1ms (Lance) | 50x |
| Vector search (10K corpus) | 50ms (Jina API) | 5ms (Lance) | 10x |
| Hamming search (10K corpus) | 100ms (Python) | 0.5ms (SIMD) | 200x |
| Graph traversal (5 hops) | 20ms (Neo4j) | 5ms (CTE) | 4x |
| Time travel (version checkout) | N/A | 1ms | ∞ |

---

## Testing Strategy

### Unit Tests
```python
def test_cypher_to_sql():
    cypher = "MATCH (a)-[:CAUSES]->(b) RETURN b"
    sql = cypher_to_sql(cypher)
    assert "JOIN edges" in sql
    assert "e.type = 'CAUSES'" in sql

def test_hamming_udf():
    a = random_fingerprint()
    b = random_fingerprint()
    result = con.execute("SELECT hamming($a, $b)", {"a": a, "b": b}).scalar()
    assert 0 <= result <= 10000

def test_recursive_cte():
    # Create test graph
    engine.add_node("a", "Test")
    engine.add_node("b", "Test")
    engine.add_node("c", "Test")
    engine.causes("a", "b")
    engine.causes("b", "c")
    
    # Query
    result = engine.query("MATCH (start)-[:CAUSES*1..3]->(end) WHERE start.id = 'a' RETURN end")
    assert len(result) == 2  # b and c
```

### Integration Tests
```python
def test_agent_handover():
    orch = create_orchestrator()
    
    # Agent A does work
    agent_a = orch.agents["archaeologist"]
    agent_a.write_thought("Found complex associations")
    agent_a.write_decision("Extract to service", "Too many callbacks")
    
    # Handover to B
    handover = orch.trigger_handover("archaeologist", "developer", "Excavation done", ["Implement service"])
    
    # Agent B receives context
    agent_b = orch.agents["developer"]
    assert agent_b.state.current_task is not None
    assert len(agent_b.find_similar(agent_b.state.current_task)) > 0
```

### Benchmark Tests
```python
def test_hamming_throughput():
    corpus = FastBatch.random(100_000)
    query = FastVector.random()
    
    start = time.perf_counter_ns()
    distances = corpus.hamming_all(query)
    elapsed_ns = time.perf_counter_ns() - start
    
    throughput = 100_000 / (elapsed_ns / 1e9)
    assert throughput > 10_000_000  # 10M comparisons/sec
```

---

## Deployment

### Docker Compose
```yaml
version: '3.8'
services:
  ladybug:
    build: .
    volumes:
      - ./data:/data
    ports:
      - "5433:5433"  # PG wire protocol
      - "8080:8080"  # REST API
    environment:
      - LADYBUG_URI=/data/ladybug
```

### Railway
```toml
[build]
builder = "dockerfile"

[deploy]
startCommand = "python -m ladybug.server"
healthcheckPath = "/health"
healthcheckTimeout = 5

[[services]]
name = "ladybug"
internalPort = 8080
```

---

## Success Criteria

1. **Unified Query**: SQL + Cypher + Vector + Hamming in one engine ✓
2. **Performance**: Sub-millisecond point lookups, 10M+ Hamming/sec ✓
3. **Versioning**: Time travel via Iceberg semantics ✓
4. **Zero-copy**: Arrow throughout, no serialization ✓
5. **Agent Orchestration**: Multi-agent via shared blackboard ✓
6. **Ada Migration**: Full compatibility with existing Ada APIs ✓

---

*LadybugDB: One substrate to rule them all.*
