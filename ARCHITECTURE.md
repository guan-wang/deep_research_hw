# Deep Research Architecture - Agent-Based Implementation

This document explains the architectural decisions and implementation details for the interactive deep research system with clarifying questions, using the OpenAI Agent SDK.

## Overview

We implemented an **Agent-based architecture with exception-based clarification**, where `ResearchManager` is transformed into an `Agent` that orchestrates the research workflow using tools. The clarification flow uses exceptions to pause agent execution and request user input.

## Architecture Components

### 1. **Research Manager Agent** (`research_manager.py`)

**Responsibilities:**
- Orchestrate the complete research workflow as an autonomous agent
- Use tools to plan searches, execute searches, write reports
- Hand off to email agent for final delivery
- Raise exceptions when clarification is needed

**Key Features:**
- **Agent with Tools**: Uses OpenAI Agent SDK with `search_planning_tool`, `search_agent_tool`, `writer_agent_tool`
- **Exception-Based Flow Control**: Raises `ClarificationNeeded` exception when user input is required
- **Autonomous Orchestration**: Agent decides when to call which tool
- **Handoffs**: Hands off to `email_agent` to complete the workflow

**Agent Structure:**
```python
research_agent = Agent(
    name="Research Manager",
    instructions=RESEARCH_AGENT_INSTRUCTIONS,
    tools=[search_planning_tool, search_agent_tool, writer_agent_tool],
    handoffs=[email_agent],
    model="gpt-4o-mini",
)
```

**Workflow:**
1. Agent receives query (and optional clarifications)
2. Calls `search_planning_tool` → may raise `ClarificationNeeded` exception
3. For each search item, calls `search_agent_tool`
4. Calls `writer_agent_tool` with all search results
5. Hands off to `email_agent` with the markdown report

### 2. **Tool Wrappers** (`research_manager.py`)

Each tool wraps an existing agent or functionality:

#### **`search_planning_tool`**
- **Purpose**: Plans searches needed for a research query
- **Wraps**: `planner_agent`
- **Behavior**:
  - If query unclear → raises `ClarificationNeeded(questions)`
  - If clarifications provided → uses them to create better search plan
  - Returns list of search items with `query` and `reason`

#### **`search_agent_tool`**
- **Purpose**: Performs individual web searches
- **Wraps**: `search_agent`
- **Behavior**: Takes search query and reason, returns search summary

#### **`writer_agent_tool`**
- **Purpose**: Writes comprehensive research reports
- **Wraps**: `writer_agent`
- **Behavior**: Takes query and search results, returns report dict (stored globally for later access)

### 3. **Exception-Based Clarification Flow**

**Key Mechanism:** `ClarificationNeeded` exception

**Flow:**
```
1. research_agent calls search_planning_tool(query, clarifications=None)
   ↓
2. Tool calls planner_agent → returns ResearchResponse(type='follow_up', questions=[...])
   ↓
3. Tool raises ClarificationNeeded(questions)
   ↓
4. Exception propagates through:
   - Tool execution context
   - Agent SDK internal handling
   - Runner.run() → re-raises
   ↓
5. ResearchManager.run() catches it
   - Converts to dict: {"type": "clarification_needed", "questions": [...]}
   - Yields dict and returns (generator stops)
   ↓
6. run_research() receives dict
   - Formats questions for display
   - Yields history with questions
   - Breaks out of loop
   - Raises ClarificationNeeded(questions) after loop
   ↓
7. research_chatbot() catches exception
   - Sets state["phase"] = "waiting_for_answers"
   - Yields updated state
   - Returns (exits function)
```

**Why This Works:**
- Generator stops cleanly when clarification needed
- Exception propagates through all layers
- State updated before yielding to Gradio
- User provides answers → agent re-run with enriched input

### 4. **Interactive Gradio Interface** (`deep_research_interactive.py`)

**State Machine:**

```python
state = {
    "phase": "initial" | "waiting_for_answers" | "researching" | "complete",
    "query": str,  # Original user query (persisted across clarification rounds)
}
```

**State Transitions:**

```
┌─────────────┐
│  "initial"  │ ← User submits query
└──────┬──────┘
       │
   ┌───┴───┐
   │       │
   ▼       ▼
[Clear] [Needs clarification]
   │       │
   │       └───► ┌──────────────────────┐
   │             │"waiting_for_answers" │ ← Exception raised
   │             └──────────┬───────────┘
   │                        │
   │                   [User answers]
   │                        │
   └────────────────────────┴───► ┌──────────────┐
                                   │"researching" │
                                   └──────┬───────┘
                                          │
                                   [Complete]
                                          │
                                          ▼
                                   ┌──────────────┐
                                   │  "complete"  │
                                   └──────────────┘
```

**Key Implementation Details:**

1. **Phase: "initial"**
   - User submits query
   - Query stored in state
   - Attempts to run research
   - If `ClarificationNeeded` raised → transition to `"waiting_for_answers"`
   - If successful → transition to `"complete"`

2. **Phase: "waiting_for_answers"**
   - User's message is treated as answers
   - Research re-run with `clarification_answers` parameter
   - Agent receives enriched input: `"Research query: {query}\n\nPrevious clarification conversation:\n{answers}"`
   - If successful → transition to `"complete"`
   - If still unclear → stay in `"waiting_for_answers"` (can ask follow-ups)

3. **Phase: "complete"**
   - Research finished
   - Any new messages ignored (user prompted to clear chat)

**Critical Bug Fix:**
- Phase is **NOT** set to `"researching"` before the async loop
- Phase only changes **after** we know the outcome (success or exception)
- Prevents race condition where state is set prematurely

### 5. **Exception Handling** (`exceptions.py`)

```python
class ClarificationNeeded(Exception):
    """
    Raised when the research manager needs user clarification.
    
    Exception message is intentionally minimal ("USER_CLARIFICATION_REQUIRED")
    to prevent the agent from trying to answer questions itself.
    """
    
    def __init__(self, questions: list[str]):
        super().__init__("USER_CLARIFICATION_REQUIRED")
        self.questions = questions
```

**Design Decisions:**
- Minimal exception message to prevent agent from interpreting questions as instructions
- Questions stored separately as attribute
- Explicit documentation that agent should not catch/handle this

## Design Decisions

### Why Agent-Based Architecture?

**Benefits:**
1. **Autonomous Orchestration**: Agent decides tool call order and handles complexity
2. **Tool Composition**: Existing agents wrapped as tools for reuse
3. **Agent Handoffs**: Natural pattern for email delivery
4. **Extensibility**: Easy to add new tools or modify workflow

**Trade-offs:**
- Agent instructions must be carefully crafted
- Exception handling more complex (bubbles through multiple layers)
- Requires clear instructions to prevent agent from working around exceptions

### Why Exception-Based Clarification?

**Challenge:** How to pause agent execution to request user input?

**Solution:** Raise exception that propagates through generator → caught by Gradio

**Benefits:**
- Works seamlessly with async generators
- Clean separation: tool raises, Gradio catches
- Exception message intentionally minimal to prevent agent interference
- State management happens at Gradio level (not agent level)

**Implementation Pattern:**
```python
# In tool:
if needs_clarification:
    raise ClarificationNeeded(questions)

# In manager.run() (generator):
except ClarificationNeeded as e:
    yield {"type": "clarification_needed", "questions": e.questions}
    return  # Stop generator

# In run_research() (generator):
if status.get("type") == "clarification_needed":
    # Format and display questions
    yield history
    break  # Exit loop
    # Raise exception after loop exits
    raise ClarificationNeeded(questions)

# In research_chatbot():
except ClarificationNeeded:
    state["phase"] = "waiting_for_answers"
    yield "", history, state
    return
```

### Why Break + Raise Pattern?

**Problem:** If exception raised inside `async for` loop after yielding, the loop may complete normally before exception propagates.

**Solution:** 
1. Detect clarification dict → `break` out of loop immediately
2. After loop exits → raise exception
3. Exception propagates to outer handler

This ensures:
- Loop exits cleanly when clarification needed
- Exception raised at correct point in execution
- No race conditions with `research_completed` flag

## File Changes Summary

### Modified Files:

1. **`research_manager.py`**
   - **Transformed**: `ResearchManager` is now an `Agent` with tools
   - **Tools**: `search_planning_tool`, `search_agent_tool`, `writer_agent_tool`
   - **Exception Handling**: Catches `ClarificationNeeded`, yields dict, returns
   - **Report Storage**: Global state to access report after agent execution

2. **`deep_research_interactive.py`**
   - **State Management**: Improved phase transitions (don't set prematurely)
   - **Exception Flow**: Break + raise pattern for proper exception propagation
   - **Debug Logging**: Added comprehensive logging for state tracking

3. **`exceptions.py`** (NEW)
   - Shared exception class for clarification needs
   - Minimal exception message to prevent agent interference

### New Architecture:

**Old Pattern (Orchestrator):**
```
ResearchManager (orchestrator)
  ├─> plan_searches() → calls planner_agent
  ├─> perform_searches() → calls search_agent
  ├─> write_report() → calls writer_agent
  └─> send_email() → calls email_agent
```

**New Pattern (Agent with Tools):**
```
research_agent (Agent)
  ├─> search_planning_tool → wraps planner_agent
  ├─> search_agent_tool → wraps search_agent
  ├─> writer_agent_tool → wraps writer_agent
  └─> handoff to email_agent
```

## State Management Details

### Gradio State

```python
state = {
    "phase": "initial" | "waiting_for_answers" | "complete",
    "query": str,  # Persisted across clarification rounds
}
```

### Agent Input Construction

**First Run (No Clarifications):**
```python
agent_input = "Research query: {query}"
```

**After Clarifications Provided:**
```python
agent_input = f"""Research query: {query}

Previous clarification conversation:
{clarification_answers}

Proceed with research using the clarified understanding."""
```

### State Transition Rules

1. **Never set phase to "researching"** before async loop starts
2. **Only set phase after outcome known:**
   - Exception raised → `"waiting_for_answers"`
   - Loop completed successfully → `"complete"`
3. **Always return after setting phase** in exception handler
4. **Use `break` + raise pattern** in `run_research()` for clean loop exit

## Usage

### Interactive Mode (Gradio)

```python
# Start the interface
python deep_research_interactive.py
```

**Flow:**
1. User submits query
2. Agent evaluates clarity via `search_planning_tool`
3. If unclear → questions displayed, state = `"waiting_for_answers"`
4. User provides answers
5. Agent re-run with enriched input
6. Research completes → state = `"complete"`

### Non-Interactive Mode

```python
# In deep_research.py
manager = ResearchManager()
async for status in manager.run(query, require_clarifications=False):
    print(status)
```

## Testing Recommendations

### Test Cases:

1. **Clear Query**
   - Input: "Recent quantum computing breakthroughs in error correction from 2023-2024"
   - Expected: Agent proceeds directly, no clarification needed

2. **Unclear Query**
   - Input: "AI stuff"
   - Expected: `search_planning_tool` raises `ClarificationNeeded`, questions displayed

3. **Clarification Flow**
   - Input: "AI stuff" → agent asks questions
   - User: "Healthcare applications, last 2 years, technical depth"
   - Expected: Agent receives enriched input, proceeds with research

4. **State Persistence**
   - Verify state["phase"] transitions correctly
   - Verify state["query"] persists across clarification rounds

## Known Limitations

1. **Single Round Clarification**: Currently one round of questions (can be extended)
2. **Exception Propagation**: Relies on proper exception bubbling (must be careful with nested generators)
3. **Agent Autonomy**: Agent must follow instructions strictly (could try to work around exceptions)

## Future Enhancements

### Potential Improvements:

1. **Multi-Turn Clarification**
   - Allow agent to ask follow-up questions if answers still unclear
   - Maintain conversation history in state

2. **Streaming Status Updates**
   - Capture tool execution events from agent
   - Stream real-time status (not just after completion)

3. **Tool Result Access**
   - Better way to access intermediate tool results
   - Currently using global state for report (could be improved)

4. **Agent Instruction Refinement**
   - Continuously improve instructions based on agent behavior
   - Add examples of correct tool usage patterns

## Conclusion

This implementation successfully achieves:
- ✅ Agent-based orchestration (autonomous, flexible)
- ✅ Exception-based clarification (works with async generators)
- ✅ Clean state management (Gradio-level, not agent-level)
- ✅ Tool composition (existing agents as tools)
- ✅ Maintainable architecture (clear separation of concerns)

The exception-based approach provides a clean way to pause agent execution for user input while maintaining the benefits of agent-based orchestration. The key insight is using exceptions to bridge the gap between agent execution and user interaction, with careful state management to ensure proper flow control.
