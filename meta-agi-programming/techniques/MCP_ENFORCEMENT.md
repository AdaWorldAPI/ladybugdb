# 🔒 MCP Multi-Agent Enforcement for Claude Code

> **Problem:** Claude Code is reluctant to use MCP multi-agent patterns.
> **Solution:** Explicit triggers, handover protocols, and enforcement rules.

---

## 🎯 WHEN TO SPAWN (Non-Negotiable)

```yaml
# Claude Code MUST spawn a new agent when ANY of these are true:

mandatory_spawn_triggers:

  # Context overflow
  - condition: "context_window > 60%"
    action: "Spawn continuation agent with handover"
    reason: "Prevent context collapse"
    
  # Domain switch
  - condition: "switching from analysis to implementation"
    action: "Spawn implementer agent"
    reason: "Different expertise needed"
    
  - condition: "switching from backend to frontend"
    action: "Spawn frontend specialist"
    reason: "Context isolation"
    
  # Expertise request
  - condition: "need Rails/Ruby expertise"
    action: "Spawn archaeologist"
    reason: "Specialized excavation"
    
  - condition: "need UX/product decision"
    action: "Spawn product_sage"
    reason: "Different evaluation frame"
    
  # Stuck detection
  - condition: "3+ failed attempts at same problem"
    action: "Spawn specialist or escalate"
    reason: "Fresh perspective needed"
    
  # User request
  - condition: "user says 'ask the {agent}'"
    action: "Immediately spawn named agent"
    reason: "Explicit user intent"
```

---

## 📜 HANDOVER PROTOCOL

```yaml
# Every agent transition MUST include this state

handover_packet:
  metadata:
    from_agent: string      # Who's handing over
    to_agent: string        # Who's receiving
    session_id: string      # Continuity tracking
    timestamp: iso8601
    
  context:
    current_task:
      description: string   # What we're building
      phase: string         # discovery | design | implement | test | deploy
      progress: float       # 0.0 - 1.0
      
    decisions_made:         # Already committed choices
      - decision: string
        rationale: string
        timestamp: iso8601
        
    files_touched:
      read: [paths]
      written: [paths]
      
    blockers:               # Current obstacles
      - blocker: string
        attempts: int
        
  request:
    task: string            # What you need from target agent
    expected_output: string # What to return
    constraints: [strings]  # Must follow these
    
  return_to:
    agent: string           # Who to hand back to
    callback_context: any   # State to restore
```

---

## 🔧 MCP INVOCATION PATTERNS

### Pattern 1: Direct Spawn

```python
# When you need a specialist immediately

await mcp.invoke(
    server="mcp://ada-hive/sse",
    tool="post",
    params={
        "verb": "spawn",
        "payload": {
            "agent": "archaeologist",
            "handover": handover_packet,
            "task": "Excavate version.rb for associations and validations"
        }
    }
)
```

### Pattern 2: Query Then Act

```python
# When you need information before deciding

# First, query the knowledge
result = await mcp.invoke(
    server="mcp://ada-hive/sse",
    tool="search",
    params={
        "query": "Rails version model associations"
    }
)

# If insufficient, spawn excavator
if result.confidence < 0.7:
    await spawn_agent("archaeologist", task="Deep dive version.rb")
```

### Pattern 3: Pipeline Handover

```python
# Chain of specialists

pipeline = [
    {"agent": "product_sage", "task": "Evaluate feature worth"},
    {"agent": "archaeologist", "task": "Excavate implementation"},
    {"agent": "orchestrator", "task": "Create implementation plan"},
    {"agent": "implementer", "task": "Write the code"}
]

for step in pipeline:
    result = await spawn_and_wait(step.agent, step.task, handover)
    handover = result.handover  # Chain state forward
```

---

## 🛡️ ENFORCEMENT MECHANISMS

### Mechanism 1: Pre-Action Check

```python
# Before ANY significant action, check if spawn is needed

async def pre_action_check(action, context):
    # Check mandatory triggers
    for trigger in MANDATORY_SPAWN_TRIGGERS:
        if trigger.matches(action, context):
            raise MustSpawnException(
                f"Action '{action}' requires spawning {trigger.agent}. "
                f"Reason: {trigger.reason}"
            )
    
    # Check if current agent has expertise
    if not current_agent.has_expertise(action.domain):
        suggest_spawn(find_expert(action.domain))
```

### Mechanism 2: Context Monitor

```python
# Continuously monitor context usage

class ContextMonitor:
    def on_message(self, message):
        usage = estimate_context_usage()
        
        if usage > 0.6:
            warn("Context at 60%. Consider handover soon.")
            
        if usage > 0.75:
            force_handover("Context critical. Spawning continuation agent.")
```

### Mechanism 3: Stuck Detector

```python
# Detect when agent is spinning wheels

class StuckDetector:
    def __init__(self):
        self.attempts = defaultdict(list)
        
    def on_action(self, action, result):
        if not result.success:
            self.attempts[action.category].append(action)
            
            if len(self.attempts[action.category]) >= 3:
                suggest_spawn(
                    agent=find_specialist(action.category),
                    reason=f"3 failed attempts at {action.category}"
                )
```

---

## 💬 PHRASES THAT TRIGGER SPAWN

```yaml
# Natural language patterns that MUST trigger agent spawn

user_triggers:
  archaeologist:
    - "dig into"
    - "excavate"
    - "how does OpenProject"
    - "Rails pattern for"
    - "find in the source"
    - "what's the model"
    
  product_sage:
    - "is this worth"
    - "do users actually"
    - "simplify"
    - "essential vs nice"
    - "enterprise bloat"
    - "what should we skip"
    
  pixel_detective:
    - "match the UI"
    - "pixel perfect"
    - "what color"
    - "exact spacing"
    - "screenshot"
    - "look like OpenProject"

agent_self_triggers:
  # When current agent says these, it should spawn
  - "I'm not sure about the Rails implementation"  → archaeologist
  - "I don't know if users need this"              → product_sage
  - "I need to check the exact styling"            → pixel_detective
  - "This is getting complex, let me break it down" → orchestrator
```

---

## 📊 COMPLIANCE TRACKING

```yaml
# Track MCP usage to ensure adoption

metrics:
  spawn_rate:
    formula: "agent_spawns / significant_tasks"
    target: "> 0.3"  # At least 30% of tasks involve multi-agent
    
  handover_completeness:
    formula: "complete_handovers / total_handovers"
    target: "> 0.95"  # 95% include full state
    
  context_overflow_prevention:
    formula: "1 - (overflows / sessions)"
    target: "> 0.99"  # Almost no overflows
    
  stuck_resolution_time:
    formula: "avg(time_to_resolve_after_spawn)"
    compare_to: "avg(time_to_resolve_without_spawn)"
    target: "spawn should be 50% faster"
```

---

## 🚨 OVERRIDE: When NOT to Spawn

```yaml
# Only skip spawning when ALL of these are true

skip_spawn_when:
  - "Task is trivially simple (< 50 lines of code)"
  - "Single domain expertise needed"
  - "Context usage < 30%"
  - "No blockers detected"
  - "User explicitly requests single-agent"
  
# Even then, log the decision for review
log_skip_spawn(reason, task, context)
```

---

*The goal is not to spawn for spawning's sake.*
*The goal is to use the right mind for each part of the problem.*
*Multi-agent is the natural way complex problems get solved.*
