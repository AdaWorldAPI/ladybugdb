"""
LadybugDB Schema Definitions

All cognitive state in one unified schema.
"""

import pyarrow as pa
from typing import Dict, Any

# =============================================================================
# CORE SCHEMAS
# =============================================================================

# 10K bit fingerprint (1250 bytes)
FINGERPRINT_TYPE = pa.binary(1250)

# 7-dimensional thinking style vector
THINKING_STYLE_TYPE = pa.list_(pa.float32(), 7)

# 1024-dimensional embedding (Jina)
EMBEDDING_TYPE = pa.list_(pa.float32(), 1024)

# 48-dimensional memory scent
SCENT_TYPE = pa.list_(pa.float32(), 48)


# =============================================================================
# NODE SCHEMA (Universal)
# =============================================================================

NODES_SCHEMA = pa.schema([
    # Identity
    pa.field("id", pa.string(), nullable=False),
    pa.field("label", pa.string(), nullable=False),
    
    # Fingerprinting (10K Hamming)
    pa.field("fingerprint", FINGERPRINT_TYPE),
    
    # Semantic embedding (Jina)
    pa.field("embedding", EMBEDDING_TYPE),
    
    # Cognitive state
    pa.field("qidx", pa.uint8()),                    # Qualia index 0-255
    pa.field("thinking_style", THINKING_STYLE_TYPE), # τ vector
    pa.field("scent", SCENT_TYPE),                   # Memory scent
    
    # Content
    pa.field("content", pa.string()),
    pa.field("properties", pa.string()),             # JSON blob
    
    # Metadata
    pa.field("created_at", pa.timestamp('us')),
    pa.field("updated_at", pa.timestamp('us')),
    pa.field("version", pa.int64()),
    pa.field("created_by", pa.string()),             # Agent ID
])


# =============================================================================
# EDGE SCHEMA (Universal)
# =============================================================================

EDGES_SCHEMA = pa.schema([
    # Identity
    pa.field("id", pa.string(), nullable=False),
    
    # Relationship
    pa.field("from_id", pa.string(), nullable=False),
    pa.field("to_id", pa.string(), nullable=False),
    pa.field("type", pa.string(), nullable=False),   # CAUSES, ENABLES, etc.
    
    # Properties
    pa.field("weight", pa.float32()),
    pa.field("amplification", pa.float32()),         # For butterfly detection
    pa.field("confidence", pa.float32()),
    pa.field("properties", pa.string()),             # JSON blob
    
    # Metadata
    pa.field("created_at", pa.timestamp('us')),
    pa.field("created_by", pa.string()),
])


# =============================================================================
# SPECIALIZED SCHEMAS
# =============================================================================

# Thought: A cognitive unit
THOUGHT_SCHEMA = NODES_SCHEMA  # label = 'Thought'

# Concept: An extracted, generalizable idea
CONCEPT_SCHEMA = pa.schema([
    pa.field("id", pa.string(), nullable=False),
    pa.field("label", pa.string(), nullable=False),  # Always 'Concept'
    pa.field("fingerprint", FINGERPRINT_TYPE),
    pa.field("embedding", EMBEDDING_TYPE),
    pa.field("content", pa.string()),
    pa.field("definition", pa.string()),             # Formal definition
    pa.field("examples", pa.list_(pa.string())),     # Example instances
    pa.field("evidence_count", pa.int32()),          # How many supporting moments
    pa.field("confidence", pa.float32()),
    pa.field("properties", pa.string()),
    pa.field("created_at", pa.timestamp('us')),
    pa.field("updated_at", pa.timestamp('us')),
    pa.field("version", pa.int64()),
])

# LearningMoment: A captured learning experience
LEARNING_MOMENT_SCHEMA = pa.schema([
    pa.field("id", pa.string(), nullable=False),
    pa.field("label", pa.string(), nullable=False),  # Always 'LearningMoment'
    pa.field("fingerprint", FINGERPRINT_TYPE),
    pa.field("content", pa.string()),
    
    # Qualia (how it felt)
    pa.field("qidx", pa.uint8()),
    pa.field("certainty", pa.float32()),
    pa.field("novelty", pa.float32()),
    pa.field("effort", pa.float32()),
    pa.field("satisfaction", pa.float32()),
    pa.field("surprise", pa.float32()),
    pa.field("clarity", pa.float32()),
    pa.field("connection", pa.float32()),
    
    # Context
    pa.field("session_id", pa.string()),
    pa.field("agent_id", pa.string()),
    pa.field("task", pa.string()),
    
    # Classification
    pa.field("is_breakthrough", pa.bool_()),
    pa.field("concept_id", pa.string()),             # Extracted concept, if any
    
    pa.field("created_at", pa.timestamp('us')),
])

# Decision: A recorded decision
DECISION_SCHEMA = pa.schema([
    pa.field("id", pa.string(), nullable=False),
    pa.field("label", pa.string(), nullable=False),  # Always 'Decision'
    pa.field("fingerprint", FINGERPRINT_TYPE),
    pa.field("content", pa.string()),                # The decision
    pa.field("rationale", pa.string()),              # Why
    pa.field("gate", pa.string()),                   # FLOW | HOLD | BLOCK
    pa.field("agent_id", pa.string()),
    pa.field("task_id", pa.string()),
    pa.field("properties", pa.string()),
    pa.field("created_at", pa.timestamp('us')),
])

# Handover: Agent-to-agent state transfer
HANDOVER_SCHEMA = pa.schema([
    pa.field("id", pa.string(), nullable=False),
    pa.field("label", pa.string(), nullable=False),  # Always 'Handover'
    pa.field("from_agent", pa.string()),
    pa.field("to_agent", pa.string()),
    pa.field("task", pa.string()),
    pa.field("context", pa.string()),                # JSON
    pa.field("decisions_made", pa.string()),         # JSON array
    pa.field("files_modified", pa.list_(pa.string())),
    pa.field("blockers", pa.list_(pa.string())),
    pa.field("next_steps", pa.list_(pa.string())),
    pa.field("resonance_hits", pa.list_(pa.string())),
    pa.field("created_at", pa.timestamp('us')),
])


# =============================================================================
# EDGE TYPES
# =============================================================================

EDGE_TYPES = {
    # Causal
    "CAUSES": "Direct causation",
    "AMPLIFIES": "Increases effect (amplification > 1)",
    "DAMPENS": "Decreases effect (amplification < 1)",
    "TRIGGERS": "Initiates a cascade",
    "ENABLES": "Makes possible but doesn't cause",
    "PREVENTS": "Blocks from happening",
    
    # Structural
    "CONTAINS": "Hierarchical containment",
    "EXTENDS": "Inheritance/extension",
    "IMPLEMENTS": "Interface implementation",
    "DEPENDS_ON": "Dependency relationship",
    
    # Semantic
    "SIMILAR_TO": "Semantic similarity",
    "CONTRADICTS": "Logical contradiction",
    "REFINES": "More specific version",
    "ABSTRACTS": "More general version",
    
    # Learning
    "YIELDS": "Learning moment yields concept",
    "SUPPORTS": "Evidence supports concept",
    "RECALLS": "Triggers memory recall",
    
    # Workflow
    "HANDS_OVER": "Agent hands over to another",
    "RESOLVES": "Resolution resolves blocker",
    "BLOCKS": "Blocker blocks progress",
    "FOLLOWS": "Sequential ordering",
}


# =============================================================================
# LABEL TYPES
# =============================================================================

LABEL_TYPES = {
    # Cognitive
    "Thought": "A unit of thinking",
    "Concept": "An extracted, generalizable idea",
    "LearningMoment": "A captured learning experience",
    "MemoryScent": "An associative memory trigger",
    
    # Workflow
    "Decision": "A recorded decision",
    "Blocker": "Something blocking progress",
    "Resolution": "Resolution to a blocker",
    "Handover": "Agent-to-agent transfer",
    
    # Agents
    "Agent": "An agent in the system",
    "Session": "A work session",
    "Task": "A task being worked on",
    
    # Code
    "Atom": "A code atom (function, class, etc.)",
    "Module": "A code module",
    "Dependency": "A code dependency",
}


# =============================================================================
# QUALIA INDEX MAPPING
# =============================================================================

# qidx is a single byte (0-255) encoding emotional/cognitive state
# Higher values = more positive/energized
QIDX_RANGES = {
    (0, 31):    "crisis",         # Overwhelmed, stuck
    (32, 63):   "struggling",     # Difficult but progressing
    (64, 95):   "working",        # Steady progress
    (96, 127):  "flowing",        # Good progress
    (128, 159): "engaged",        # Actively interested
    (160, 191): "excited",        # High energy, positive
    (192, 223): "breakthrough",   # Major insight
    (224, 255): "transcendent",   # Peak experience
}

def qidx_to_label(qidx: int) -> str:
    """Convert qidx to human-readable label."""
    for (low, high), label in QIDX_RANGES.items():
        if low <= qidx <= high:
            return label
    return "unknown"


# =============================================================================
# THINKING STYLE VECTOR
# =============================================================================

# 7-dimensional vector encoding cognitive style
THINKING_STYLE_DIMENSIONS = {
    0: "analytical",    # Logical, systematic
    1: "creative",      # Novel, divergent
    2: "practical",     # Grounded, actionable
    3: "empathetic",    # People-focused
    4: "strategic",     # Long-term, big-picture
    5: "detailed",      # Precise, thorough
    6: "intuitive",     # Pattern-based, holistic
}


# =============================================================================
# SCHEMA REGISTRY
# =============================================================================

SCHEMAS = {
    "nodes": NODES_SCHEMA,
    "edges": EDGES_SCHEMA,
    "concepts": CONCEPT_SCHEMA,
    "learning_moments": LEARNING_MOMENT_SCHEMA,
    "decisions": DECISION_SCHEMA,
    "handovers": HANDOVER_SCHEMA,
}


def get_schema(name: str) -> pa.Schema:
    """Get schema by name."""
    if name not in SCHEMAS:
        raise ValueError(f"Unknown schema: {name}. Available: {list(SCHEMAS.keys())}")
    return SCHEMAS[name]


# =============================================================================
# SCHEMA EVOLUTION
# =============================================================================

def add_column(schema: pa.Schema, name: str, dtype: pa.DataType, 
               default: Any = None) -> pa.Schema:
    """Add a column to a schema (for evolution)."""
    fields = list(schema)
    fields.append(pa.field(name, dtype))
    return pa.schema(fields)


def remove_column(schema: pa.Schema, name: str) -> pa.Schema:
    """Remove a column from a schema."""
    fields = [f for f in schema if f.name != name]
    return pa.schema(fields)


# =============================================================================
# SQL DDL GENERATION
# =============================================================================

def schema_to_ddl(schema: pa.Schema, table_name: str) -> str:
    """Generate SQL DDL from PyArrow schema."""
    
    type_map = {
        pa.string(): "VARCHAR",
        pa.int32(): "INTEGER",
        pa.int64(): "BIGINT",
        pa.uint8(): "UTINYINT",
        pa.float32(): "FLOAT",
        pa.float64(): "DOUBLE",
        pa.bool_(): "BOOLEAN",
        pa.timestamp('us'): "TIMESTAMP",
        pa.binary(1250): "BLOB",
    }
    
    columns = []
    for field in schema:
        dtype = type_map.get(field.type)
        if dtype is None:
            if str(field.type).startswith("list<"):
                dtype = "VARCHAR"  # JSON-encode lists
            else:
                dtype = "VARCHAR"
        
        nullable = "" if field.nullable else " NOT NULL"
        columns.append(f"    {field.name} {dtype}{nullable}")
    
    return f"CREATE TABLE {table_name} (\n{',\n'.join(columns)}\n);"


if __name__ == "__main__":
    # Print DDL for all schemas
    for name, schema in SCHEMAS.items():
        print(f"\n-- {name}")
        print(schema_to_ddl(schema, name))
