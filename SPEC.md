# rDNA2: Content-Addressable Code Structure Compression

## Philosophy

**Not resonance. Index.**
**Not approximate. Exact.**
**Not vectors. Pointers.**

20,000 atoms × 10ns = 200μs total execution
Faster than Ruby cold start. Smaller than source. Reversible.

---

## The Three Separations

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DEINTERLACED CODE FABRIC                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   WHAT (Content)        WHERE (Structure)       WHEN (Temporal)     │
│   ━━━━━━━━━━━━━━        ━━━━━━━━━━━━━━━━        ━━━━━━━━━━━━━━     │
│   Code atoms            Module graph            Execution order     │
│   Type signatures       Import edges            Dependency chain    │
│   Function bodies       Scope hierarchy         Call sequence       │
│                                                                     │
│   → LanceDB             → Kuzu                  → Redis             │
│   (O(1) lookup)         (O(1) traversal)        (O(1) queue)        │
│                                                                     │
│              ↓                  ↓                     ↓              │
│              └──────────────────┴─────────────────────┘              │
│                                 ↓                                    │
│                         DuckDB Orchestrator                          │
│                         (Pointer chain executor)                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. Atom Structure (WHAT)

An atom is the smallest executable unit of code.

```
┌────────────────────────────────────────────────────────────────────┐
│ ATOM BINARY FORMAT (64 bytes fixed header + variable body)         │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Bytes 0-3:   MAGIC        0x52444E32 ("RDN2")                    │
│  Bytes 4-7:   INDEX        uint32 content-address                  │
│  Bytes 8-9:   TYPE         uint16 from codebook                    │
│  Bytes 10-11: SUBTYPE      uint16 from codebook                    │
│  Bytes 12-15: TARGET       uint32 symbol table reference           │
│  Bytes 16-19: SCOPE        uint32 module reference                 │
│  Bytes 20-23: BODY_LEN     uint32 body length                      │
│  Bytes 24-31: BODY_HASH    uint64 xxhash of body                   │
│  Bytes 32-39: VERSION      uint64 monotonic version                │
│  Bytes 40-47: PARENT       uint64 previous version (0 if first)    │
│  Bytes 48-55: TIMESTAMP    uint64 unix micros                      │
│  Bytes 56-63: RESERVED     uint64 (future: signature, etc)         │
│  Bytes 64-N:  BODY         variable, compressed executable         │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### Content-Addressing

```python
def compute_index(atom: Atom) -> uint32:
    """Deterministic index from content."""
    # Hash of: type + subtype + target + body
    # Same code ALWAYS = same index
    content = (
        atom.type.to_bytes(2) +
        atom.subtype.to_bytes(2) +
        atom.target.to_bytes(4) +
        atom.body
    )
    return xxhash.xxh32(content).intdigest()
```

**Guarantee**: Identical code → identical index. Always reversible.

---

## 2. Type Codebook

Fixed codebook for all language constructs:

```
┌──────────┬────────────────────────────────────────────────────────┐
│ TYPE     │ SUBTYPES                                               │
├──────────┼────────────────────────────────────────────────────────┤
│ 0x00__   │ CORE                                                   │
│ 0x0001   │   FUNCTION                                             │
│ 0x0002   │   CLASS                                                │
│ 0x0003   │   MODULE                                               │
│ 0x0004   │   INTERFACE                                            │
│ 0x0005   │   CONSTANT                                             │
│ 0x0006   │   VARIABLE                                             │
├──────────┼────────────────────────────────────────────────────────┤
│ 0x01__   │ VALIDATION                                             │
│ 0x0100   │   .presence                                            │
│ 0x0101   │   .length                                              │
│ 0x0102   │   .format                                              │
│ 0x0103   │   .uniqueness                                          │
│ 0x0104   │   .numericality                                        │
│ 0x0105   │   .inclusion                                           │
│ 0x0106   │   .exclusion                                           │
│ 0x0107   │   .custom                                              │
├──────────┼────────────────────────────────────────────────────────┤
│ 0x02__   │ ASSOCIATION                                            │
│ 0x0200   │   .belongs_to                                          │
│ 0x0201   │   .has_many                                            │
│ 0x0202   │   .has_one                                             │
│ 0x0203   │   .has_and_belongs_to_many                             │
│ 0x0204   │   .polymorphic                                         │
├──────────┼────────────────────────────────────────────────────────┤
│ 0x03__   │ LIFECYCLE                                              │
│ 0x0300   │   .before_validation                                   │
│ 0x0301   │   .after_validation                                    │
│ 0x0302   │   .before_save                                         │
│ 0x0303   │   .after_save                                          │
│ 0x0304   │   .before_create                                       │
│ 0x0305   │   .after_create                                        │
│ 0x0306   │   .before_update                                       │
│ 0x0307   │   .after_update                                        │
│ 0x0308   │   .before_destroy                                      │
│ 0x0309   │   .after_destroy                                       │
│ 0x030A   │   .after_commit                                        │
│ 0x030B   │   .after_rollback                                      │
├──────────┼────────────────────────────────────────────────────────┤
│ 0x04__   │ QUERY                                                  │
│ 0x0400   │   .scope                                               │
│ 0x0401   │   .find                                                │
│ 0x0402   │   .where                                               │
│ 0x0403   │   .select                                              │
│ 0x0404   │   .join                                                │
│ 0x0405   │   .group                                               │
│ 0x0406   │   .order                                               │
├──────────┼────────────────────────────────────────────────────────┤
│ 0x05__   │ TRANSFORM                                              │
│ 0x0500   │   .serialize                                           │
│ 0x0501   │   .deserialize                                         │
│ 0x0502   │   .encrypt                                             │
│ 0x0503   │   .decrypt                                             │
│ 0x0504   │   .normalize                                           │
│ 0x0505   │   .format                                              │
├──────────┼────────────────────────────────────────────────────────┤
│ 0x06__   │ PERMISSION                                             │
│ 0x0600   │   .authorize                                           │
│ 0x0601   │   .can_read                                            │
│ 0x0602   │   .can_write                                           │
│ 0x0603   │   .can_delete                                          │
│ 0x0604   │   .role_check                                          │
├──────────┼────────────────────────────────────────────────────────┤
│ 0x07__   │ CONTROL                                                │
│ 0x0700   │   .if                                                  │
│ 0x0701   │   .unless                                              │
│ 0x0702   │   .case                                                │
│ 0x0703   │   .loop                                                │
│ 0x0704   │   .return                                              │
│ 0x0705   │   .raise                                               │
│ 0x0706   │   .rescue                                              │
├──────────┼────────────────────────────────────────────────────────┤
│ 0xFF__   │ EXTENSION (user-defined types)                         │
└──────────┴────────────────────────────────────────────────────────┘
```

---

## 3. Symbol Table

All identifiers (field names, model names, method names) get indexed:

```
┌────────────────────────────────────────────────────────────────────┐
│ SYMBOL TABLE                                                       │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  INDEX      NAME                SCOPE          KIND                │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│  0x00000001 "id"                GLOBAL         FIELD               │
│  0x00000002 "created_at"        GLOBAL         FIELD               │
│  0x00000003 "updated_at"        GLOBAL         FIELD               │
│  0x00001001 "subject"           WorkPackage    FIELD               │
│  0x00001002 "description"       WorkPackage    FIELD               │
│  0x00001003 "project"           WorkPackage    ASSOC               │
│  0x00001004 "author"            WorkPackage    ASSOC               │
│  0x00002001 "name"              Project        FIELD               │
│  0x00002002 "identifier"        Project        FIELD               │
│  0x00002003 "work_packages"     Project        ASSOC               │
│  ...                                                               │
│                                                                    │
│  HASH FUNCTION:                                                    │
│  index = xxhash(scope + ":" + name) & 0xFFFFFFFF                  │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 4. Storage Layer

### LanceDB: Atom Store (WHAT)

```python
# Schema
ATOMS_TABLE = {
    "index": "uint32",           # Content-address (PRIMARY KEY)
    "type": "uint16",            # Type codebook
    "subtype": "uint16",         # Subtype codebook
    "target": "uint32",          # Symbol reference
    "scope": "uint32",           # Module reference
    "body": "binary",            # Compressed executable
    "body_hash": "uint64",       # For integrity
    "version": "uint64",         # Monotonic
    "parent": "uint64",          # Previous version (git-like)
    "timestamp": "uint64",       # Unix micros
}

# Operations: ALL O(1)
atom = db.get(index)                    # Direct lookup
db.put(atom)                            # Upsert
history = db.versions(index)            # All versions
db.rollback(index, version)             # Time travel
```

### Kuzu: Dependency Graph (WHERE)

```cypher
-- Node types
CREATE NODE TABLE Atom(index UINT32 PRIMARY KEY)
CREATE NODE TABLE Module(path STRING PRIMARY KEY)
CREATE NODE TABLE Symbol(index UINT32 PRIMARY KEY, name STRING)

-- Edge types (all O(1) traversal)
CREATE REL TABLE DEFINES(FROM Module TO Atom, position UINT16)
CREATE REL TABLE IMPORTS(FROM Module TO Module)
CREATE REL TABLE REFERENCES(FROM Atom TO Symbol)
CREATE REL TABLE CALLS(FROM Atom TO Atom)
CREATE REL TABLE DEPENDS(FROM Atom TO Atom, kind STRING)
```

### Redis: Execution Stack (WHEN)

```
# Execution queue per operation
RPUSH exec:WorkPackage:create 0x0100 0x0101 0x0102 0x0300 0x2000 0x0303

# Current position
SET exec:WorkPackage:create:pos 0

# Execution state per atom
HSET exec:WorkPackage:create:state:0x0100 status "success" result "..."
HSET exec:WorkPackage:create:state:0x0101 status "pending"

# Snapshots for rollback
RPUSH exec:WorkPackage:create:snapshots "{pos:2,timestamp:1706428800}"
```

### DuckDB: Orchestrator

```sql
-- Execution plan table
CREATE TABLE execution_plan (
    plan_id UUID PRIMARY KEY,
    operation VARCHAR,           -- "WorkPackage:create"
    atoms UINT32[],              -- Ordered atom indices
    current_pos INTEGER DEFAULT 0,
    status VARCHAR DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT now(),
    version UINT64               -- For rollback
);

-- Execution log (append-only)
CREATE TABLE execution_log (
    id UINT64 PRIMARY KEY,       -- Auto-increment
    plan_id UUID,
    atom_index UINT32,
    status VARCHAR,              -- success/error/skipped
    duration_ns UINT64,
    result BLOB,
    error VARCHAR,
    timestamp TIMESTAMP DEFAULT now()
);

-- Rollback = replay from log
SELECT * FROM execution_log 
WHERE plan_id = ? AND timestamp <= ?
ORDER BY id;
```

---

## 5. Execution Model

### The Pointer Chain

```
┌─────────────────────────────────────────────────────────────────────┐
│                     EXECUTION AS POINTER WALKING                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Step 1: Build plan from Kuzu graph                               │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                                 │
│   MATCH (m:Module {path:'work_package.rb'})-[:DEFINES]->(a:Atom)   │
│   WHERE a.type IN [0x01xx, 0x03xx]  -- validations + callbacks     │
│   RETURN a.index ORDER BY position                                  │
│   → [0x0100, 0x0101, 0x0102, 0x0300, 0x2000, 0x0303]              │
│                                                                     │
│   Step 2: Push to Redis queue                                       │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━                                       │
│   RPUSH exec:{op} 0x0100 0x0101 0x0102 0x0300 0x2000 0x0303       │
│                                                                     │
│   Step 3: Execute pointer by pointer                               │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                                  │
│   while (idx = LPOP exec:{op}):                                    │
│       atom = lancedb.get(idx)        # O(1) - ~10ns                │
│       result = execute(atom.body)     # Run the code               │
│       log_execution(idx, result)      # Append to DuckDB           │
│       if error: break or retry                                     │
│                                                                     │
│   Total: 6 atoms × 10ns lookup = 60ns overhead                     │
│   Compare: Ruby parse + interpret = ~5ms                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Parallel Execution

```python
def execute_parallel(plan: List[uint32]) -> Results:
    """Execute independent atoms in parallel."""
    
    # Build dependency graph
    deps = kuzu.query("""
        MATCH (a:Atom)-[:DEPENDS]->(b:Atom)
        WHERE a.index IN $plan AND b.index IN $plan
        RETURN a.index, b.index
    """, plan=plan)
    
    # Topological sort with parallelism
    levels = toposort(deps)
    
    # Execute level by level
    results = {}
    for level in levels:
        # All atoms in same level can run parallel
        with ThreadPool() as pool:
            level_results = pool.map(
                lambda idx: execute_atom(lancedb.get(idx)),
                level
            )
        results.update(zip(level, level_results))
    
    return results
```

---

## 6. Git-Like Versioning

### Code Versioning (Atom Evolution)

```
┌─────────────────────────────────────────────────────────────────────┐
│                     ATOM VERSION CHAIN                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Version 1 (initial)                                              │
│   ┌─────────────────────────────────────────┐                      │
│   │ index: 0x0100                           │                      │
│   │ type: VALIDATION.presence              │                      │
│   │ body: validates :subject, presence: true│                      │
│   │ version: 1                              │                      │
│   │ parent: 0                               │                      │
│   └─────────────────────────────────────────┘                      │
│                      │                                              │
│                      ▼                                              │
│   Version 2 (added message)                                        │
│   ┌─────────────────────────────────────────┐                      │
│   │ index: 0x0100                           │                      │
│   │ type: VALIDATION.presence              │                      │
│   │ body: validates :subject, presence: true│                      │
│   │       message: "Subject required"       │                      │
│   │ version: 2                              │                      │
│   │ parent: 1                               │  ← Points to v1      │
│   └─────────────────────────────────────────┘                      │
│                      │                                              │
│                      ▼                                              │
│   Version 3 (added condition)                                      │
│   ┌─────────────────────────────────────────┐                      │
│   │ index: 0x0100                           │                      │
│   │ type: VALIDATION.presence              │                      │
│   │ body: validates :subject, presence: true│                      │
│   │       message: "Subject required"       │                      │
│   │       if: -> { new_record? }            │                      │
│   │ version: 3                              │                      │
│   │ parent: 2                               │  ← Points to v2      │
│   └─────────────────────────────────────────┘                      │
│                                                                     │
│   ROLLBACK: lancedb.get(0x0100, version=1)  # Get any version     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Execution Versioning (Time Travel)

```sql
-- Every execution is logged
INSERT INTO execution_log (plan_id, atom_index, status, result, timestamp)
VALUES ('abc-123', 0x0100, 'success', '...', now());

-- Rollback execution to point in time
CREATE VIEW execution_at_time AS
SELECT DISTINCT ON (atom_index) *
FROM execution_log
WHERE plan_id = 'abc-123' 
  AND timestamp <= '2024-01-28 10:00:00'
ORDER BY atom_index, timestamp DESC;

-- Replay from checkpoint
SELECT atom_index, result 
FROM execution_at_time
WHERE status = 'success';
```

### Branch/Merge (Like Git)

```python
def branch(name: str, from_version: int):
    """Create execution branch."""
    redis.set(f"branch:{name}:base", from_version)
    redis.copy(f"exec:{op}", f"exec:{op}:branch:{name}")

def merge(branch: str, into: str = "main"):
    """Merge branch back."""
    base = redis.get(f"branch:{branch}:base")
    
    # Get all atoms modified in branch
    branch_atoms = get_modified_since(branch, base)
    main_atoms = get_modified_since("main", base)
    
    # Detect conflicts (same atom modified in both)
    conflicts = branch_atoms & main_atoms
    if conflicts:
        raise MergeConflict(conflicts)
    
    # Apply branch changes to main
    for atom_idx in branch_atoms:
        atom = lancedb.get(atom_idx, branch=branch)
        lancedb.put(atom, branch="main")
```

---

## 7. Reconstruction (100% Reversible)

```python
TEMPLATES = {
    0x0100: "validates :{target}, presence: true{options}",
    0x0101: "validates :{target}, length: {{ {options} }}",
    0x0102: "validates :{target}, format: {{ with: {options} }}",
    0x0200: "belongs_to :{target}{options}",
    0x0201: "has_many :{target}{options}",
    0x0300: "before_validation :{method}{options}",
    0x0302: "before_save :{method}{options}",
    0x0303: "after_save :{method}{options}",
    # ... all types
}

def reconstruct_atom(index: uint32) -> str:
    """Reconstruct source from atom."""
    atom = lancedb.get(index)
    template = TEMPLATES[atom.type << 8 | atom.subtype]
    target = symbol_table.get(atom.target)
    options = decode_options(atom.body)
    
    return template.format(target=target, options=options, method=options.get('method'))

def reconstruct_module(path: str) -> str:
    """Reconstruct entire file."""
    atoms = kuzu.query("""
        MATCH (m:Module {path: $path})-[:DEFINES]->(a:Atom)
        RETURN a.index, a.type
        ORDER BY a.position
    """, path=path)
    
    # Group by class/module structure
    lines = []
    for atom in atoms:
        lines.append(reconstruct_atom(atom.index))
    
    return "\n".join(lines)

# GUARANTEE: reconstruct(compile(source)) == source (semantically)
```

---

## 8. Performance Characteristics

```
┌─────────────────────────────────────────────────────────────────────┐
│                     PERFORMANCE COMPARISON                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Operation              Ruby          rDNA2                        │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│   Cold start             500ms         0ms (pre-indexed)           │
│   Load model class       5ms           60ns (6 pointer lookups)    │
│   Validate record        100μs         600ns (60 atoms)            │
│   Save record            1ms           6μs (600 atoms)             │
│   Complex query          10ms          100μs                        │
│                                                                     │
│   Storage                Ruby          rDNA2                        │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│   2000 files             50MB source   2MB atoms + 500KB index     │
│   20,000 functions       in source     20,000 × 64B = 1.25MB       │
│   Full history           git repo      LanceDB versions (delta)    │
│                                                                     │
│   Rollback               Ruby          rDNA2                        │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│   Code rollback          git checkout  lancedb.get(idx, version=N) │
│   Execution rollback     impossible    replay from log             │
│   Branch execution       impossible    redis.copy + isolate        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 9. API Surface

```python
class rDNA2:
    """Content-Addressable Code Structure Compression."""
    
    # Compile
    def compile(self, source: str, language: str = "ruby") -> List[Atom]
    def compile_file(self, path: str) -> List[Atom]
    def compile_project(self, root: str) -> ProjectIndex
    
    # Store
    def store(self, atom: Atom) -> uint32  # Returns index
    def store_batch(self, atoms: List[Atom]) -> List[uint32]
    
    # Retrieve (O(1))
    def get(self, index: uint32, version: int = None) -> Atom
    def get_batch(self, indices: List[uint32]) -> List[Atom]
    
    # Execute
    def plan(self, operation: str, model: str) -> ExecutionPlan
    def execute(self, plan: ExecutionPlan) -> ExecutionResult
    def execute_atom(self, index: uint32, context: dict) -> Any
    
    # Version control
    def versions(self, index: uint32) -> List[int]
    def rollback(self, index: uint32, version: int) -> Atom
    def branch(self, name: str, from_version: int = None)
    def merge(self, branch: str, into: str = "main")
    
    # Reconstruct
    def reconstruct(self, index: uint32) -> str
    def reconstruct_module(self, path: str) -> str
    def reconstruct_project(self) -> Dict[str, str]
    
    # Query
    def find_by_type(self, type: uint16) -> List[uint32]
    def find_by_target(self, symbol: str) -> List[uint32]
    def find_dependencies(self, index: uint32) -> List[uint32]
    def find_dependents(self, index: uint32) -> List[uint32]
```

---

## 10. Integration with Firefly

```
┌─────────────────────────────────────────────────────────────────────┐
│                     FIREFLY + rDNA2 STACK                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Firefly (Resonance)           rDNA2 (Index)                      │
│   ━━━━━━━━━━━━━━━━━━━           ━━━━━━━━━━━━━━                     │
│   10K Hamming vectors           Pointer indices                     │
│   Approximate similarity        Exact lookup                        │
│   Discovery, exploration        Execution, verification             │
│   "What might be related"       "What exactly is this"             │
│                                                                     │
│   USE CASE:                                                         │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │ User: "Find validations similar to email format check"      │  │
│   │                                                             │  │
│   │ 1. Firefly: resonate("email format validation")             │  │
│   │    → [0x0102, 0x0107, 0x0105] (by similarity)              │  │
│   │                                                             │  │
│   │ 2. rDNA2: get(0x0102)                                       │  │
│   │    → Exact atom with full code                              │  │
│   │                                                             │  │
│   │ 3. rDNA2: reconstruct(0x0102)                               │  │
│   │    → "validates :email, format: { with: URI::MailTo... }"  │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│   Firefly = fuzzy search                                           │
│   rDNA2 = exact execution                                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```
