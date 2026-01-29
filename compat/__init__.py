"""
LadybugDB Compatibility Layer

Familiar APIs, alien speed.

This module provides compatibility wrappers that make LadybugDB feel like
familiar tools while being backed by AVX-512 Hamming and recursive CTEs.

## Jina-style API

```python
from ladybugdb.compat import JinaClient, Document, DocumentArray

client = JinaClient()
client.index([
    Document(id="1", content="Hello world"),
    Document(id="2", content="Goodbye world"),
])

results = client.search("Hello", top_k=10)
```

## Neo4j-style API

```python
from ladybugdb.compat import GraphDatabase

driver = GraphDatabase.driver("ladybug://./mydb")

with driver.session() as session:
    result = session.run('''
        MATCH (a:Thought)-[:CAUSES*1..5]->(b:Thought)
        WHERE a.qidx > 100
        RETURN b
    ''')
```

## DTOs (Pydantic-style)

```python
from ladybugdb.compat import Node, Edge, Thought, Concept

node = Node(id="1", content="The sky is blue")
node.fingerprint  # Auto-computed 10K bit fingerprint

edge = Edge(from_id="1", to_id="2", type="CAUSES", amplification=2.5)
```

## Compression

```python
from ladybugdb.compat import Compressor, ColumnStore

compressor = Compressor()
block = compressor.compress(data)  # Auto-selects best encoding
print(f"Compression ratio: {block.compression_ratio:.1f}x")

store = ColumnStore()
store.add_column("name", ["Alice", "Bob", "Alice"])
store.add_column("age", [25, 30, 25])
```

## Chunking

```python
from ladybugdb.compat import chunk_text, semantic_chunk

chunks = chunk_text(long_text, chunk_size=512, overlap=64)
chunks = semantic_chunk(long_text, min_chunk=100, max_chunk=1000)
```
"""

# DTOs
from .dto import (
    # Base
    BaseDTO,
    
    # Core types
    Node,
    Edge,
    
    # Specialized nodes
    Thought,
    Concept,
    LearningMoment,
    Decision,
    Blocker,
    
    # Results
    SearchResult,
    PathResult,
    QueryResult,
    
    # Agent coordination
    Handover,
    
    # Batch operations
    NodeBatch,
    
    # Utilities
    content_to_fingerprint,
    random_fingerprint,
    create_node,
    NODE_TYPES,
)

# Jina compatibility
from .jina_compat import (
    # Core classes
    Document,
    DocumentArray,
    JinaClient,
    
    # Pipeline
    Flow,
    Executor,
    requests,
    
    # Query builder
    ResonanceQuery,
    
    # Convenience functions
    resonate,
    batch_resonate,
)

# Neo4j compatibility
from .neo4j_compat import (
    # Driver
    GraphDatabase,
    Driver,
    Session,
    Transaction,
    
    # Results
    Record,
    Result,
    
    # Parser/Transpiler
    CypherParser,
    CypherTranspiler,
    CypherPattern,
    
    # Convenience
    cypher_to_sql,
    parse_cypher,
)

# Compression
from .compression import (
    # Encoding types
    EncodingType,
    
    # Core compression
    Compressor,
    CompressedBlock,
    DictionaryBuilder,
    
    # Column store
    ColumnStore,
    ColumnChunk,
    
    # Chunking
    chunk_text,
    chunk_tokens,
    semantic_chunk,
)

# Version
__version__ = "0.1.0"

# All exports
__all__ = [
    # DTOs
    'BaseDTO',
    'Node',
    'Edge',
    'Thought',
    'Concept',
    'LearningMoment',
    'Decision',
    'Blocker',
    'SearchResult',
    'PathResult',
    'QueryResult',
    'Handover',
    'NodeBatch',
    'content_to_fingerprint',
    'random_fingerprint',
    'create_node',
    'NODE_TYPES',
    
    # Jina
    'Document',
    'DocumentArray',
    'JinaClient',
    'Flow',
    'Executor',
    'requests',
    'ResonanceQuery',
    'resonate',
    'batch_resonate',
    
    # Neo4j
    'GraphDatabase',
    'Driver',
    'Session',
    'Transaction',
    'Record',
    'Result',
    'CypherParser',
    'CypherTranspiler',
    'CypherPattern',
    'cypher_to_sql',
    'parse_cypher',
    
    # Compression
    'EncodingType',
    'Compressor',
    'CompressedBlock',
    'DictionaryBuilder',
    'ColumnStore',
    'ColumnChunk',
    'chunk_text',
    'chunk_tokens',
    'semantic_chunk',
]
