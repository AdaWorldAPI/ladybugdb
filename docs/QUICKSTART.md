# Quickstart Guide

Get LadybugDB running in 5 minutes.

---

## Installation

```bash
pip install ladybugdb
```

## Create Your First Database

```python
from ladybugdb import connect

# Create/connect to database
db = connect("./my_first_db")
```

## Add Data

### Nodes (Thoughts, Concepts, etc.)

```python
from ladybugdb.compat import Node, Thought

# Basic node
node = Node(
    id="thought_1",
    content="The sky appears blue due to Rayleigh scattering",
    label="Thought",
    qidx=180  # Qualia index (0-255)
)
db.add_node(node)

# Specialized thought node
thought = Thought(
    id="thought_2",
    content="This makes sunsets appear red",
    intensity=0.8,
    valence=0.6  # Positive sentiment
)
db.add_node(thought)
```

### Edges (Relationships)

```python
from ladybugdb.compat import Edge

edge = Edge(
    from_id="thought_1",
    to_id="thought_2",
    type="CAUSES",
    amplification=1.5  # For butterfly detection
)
db.add_edge(edge)
```

## Query Your Data

### SQL

```python
results = db.sql("""
    SELECT id, content, qidx 
    FROM nodes 
    WHERE label = 'Thought' AND qidx > 100
    ORDER BY qidx DESC
""")

for row in results:
    print(f"{row['id']}: {row['content']}")
```

### Cypher (Graph Queries)

```python
results = db.cypher("""
    MATCH (a:Thought)-[:CAUSES]->(b:Thought)
    WHERE a.qidx > 150
    RETURN a.content AS cause, b.content AS effect
""")
```

### Resonance Search (Hamming Similarity)

```python
# Search by content (auto-generates fingerprint)
similar = db.resonate_content(
    "Why is the sky blue?",
    threshold=0.6,
    limit=10
)

# Search by fingerprint
from ladybugdb.compat import content_to_fingerprint
fp = content_to_fingerprint("sky color physics")
similar = db.resonate(fp, threshold=0.6, limit=10)
```

### Vector Search

```python
# If you have embeddings
results = db.vector_search(
    embedding,  # Your embedding vector
    k=10
)
```

## Jina-Style API

For those familiar with Jina:

```python
from ladybugdb.compat import JinaClient, Document, DocumentArray

# Create client
client = JinaClient()

# Index documents
docs = [
    Document(id="1", content="Machine learning fundamentals"),
    Document(id="2", content="Deep learning architectures"),
    Document(id="3", content="Natural language processing"),
]
client.index(docs)

# Search
results = client.search("neural networks", top_k=5)

for doc in results:
    print(f"{doc.id}: {doc.scores['hamming_similarity']:.2%}")
```

## Neo4j-Style API

For those familiar with Neo4j:

```python
from ladybugdb.compat import GraphDatabase

driver = GraphDatabase.driver("ladybug://./my_first_db")

with driver.session() as session:
    # Create nodes
    session.run("""
        CREATE (a:Person {name: 'Alice', age: 30})
        CREATE (b:Person {name: 'Bob', age: 25})
    """)
    
    # Query
    result = session.run("""
        MATCH (p:Person)
        WHERE p.age > 20
        RETURN p.name, p.age
        ORDER BY p.age DESC
    """)
    
    for record in result:
        print(f"{record['p.name']}: {record['p.age']}")
```

## Butterfly Detection

Find causal chains where small changes amplify:

```python
# Add some connected nodes
db.add_node(Node(id="config", content="Enable feature flag", label="Config"))
db.add_node(Node(id="behavior", content="User behavior changed", label="Event"))
db.add_node(Node(id="cascade", content="System overload", label="Failure"))

db.add_edge(Edge(from_id="config", to_id="behavior", type="CAUSES", amplification=2.0))
db.add_edge(Edge(from_id="behavior", to_id="cascade", type="CAUSES", amplification=3.0))

# Detect butterflies (amplification > threshold)
butterflies = db.detect_butterflies(
    source="config",
    threshold=2.0,
    max_depth=10
)

for path, total_amplification in butterflies:
    print(f"Amplification: {total_amplification:.1f}x")
    print(f"Path: {' → '.join(n.id for n in path)}")
```

## Compression

For large datasets:

```python
from ladybugdb.compat import Compressor, ColumnStore

# Compress arbitrary data
compressor = Compressor()
block = compressor.compress(my_array)
print(f"Compression: {block.compression_ratio:.1f}x ({block.encoding.name})")

# Column store for analytics
store = ColumnStore(chunk_size=10000)
store.add_column("timestamp", timestamps)
store.add_column("value", values)
store.add_column("label", labels)  # Auto-dictionary encoded

# Query with chunk pruning
chunks = store.get_chunks("value", min_val=100, max_val=200)
```

## Next Steps

- **[API Reference](API.md)** — Complete function documentation
- **[Architecture](ARCHITECTURE.md)** — How it works under the hood
- **[Performance](PERFORMANCE.md)** — Optimization tips
- **[Migration](MIGRATION.md)** — Moving from Neo4j/Pinecone

---

## Common Patterns

### Pattern 1: Knowledge Graph

```python
# Build a knowledge graph
concepts = ["Physics", "Chemistry", "Biology"]
for c in concepts:
    db.add_node(Node(id=c.lower(), content=c, label="Concept"))

# Add relationships
db.add_edge(Edge(from_id="physics", to_id="chemistry", type="RELATES_TO"))
db.add_edge(Edge(from_id="chemistry", to_id="biology", type="RELATES_TO"))

# Query paths
paths = db.cypher("""
    MATCH path = (a:Concept)-[:RELATES_TO*1..3]->(b:Concept)
    RETURN path
""")
```

### Pattern 2: Semantic Memory

```python
# Store memories with fingerprints
memories = [
    "Had coffee with Sarah at Blue Bottle",
    "Discussed the new project timeline",
    "Sarah mentioned her trip to Japan"
]

for i, m in enumerate(memories):
    db.add_node(Node(id=f"mem_{i}", content=m, label="Memory"))

# Find related memories
similar = db.resonate_content("meeting with Sarah", threshold=0.5)
```

### Pattern 3: Agent Coordination

```python
from ladybugdb.compat import Handover, Decision

# Record a decision
decision = Decision(
    id="d1",
    decision_type="GATE",
    gate_result="FLOW",
    rationale="All tests pass",
    agent_id="reviewer"
)
db.add_node(decision)

# Create handover packet
handover = Handover(
    from_agent="Researcher",
    to_agent="Writer",
    task="Draft blog post",
    context="Research complete on quantum computing",
    next_steps=["Write intro", "Add examples", "Review citations"]
)

# Render for LLM context window
print(handover.to_markdown())
```

---

<p align="center"><i>Questions? Open an issue on GitHub.</i></p>
