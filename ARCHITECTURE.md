# Deep Research Architecture - Path A Implementation

This document explains the architectural decisions and implementation details for the interactive deep research system with clarifying questions.

## Overview

We implemented **Path A: Agentic Planner with Chat Tool**, where the planner agent autonomously decides when clarification is needed and generates questions directly, while the ResearchManager handles workflow orchestration.

## Architecture Components

### 1. **Planner Agent** (`planner_agent.py`)

**Responsibilities:**
- Analyze query clarity
- Decide autonomously if clarification is needed
- Generate clarifying questions (if needed)
- Generate search plan (when ready)

**Key Features:**
- Single agent handles both decision-making and question generation
- Returns `ResearchResponse` with type `'follow_up'` or `'answer'`
- Uses structured output (Pydantic models) for type safety

**Model:**
```python
class ResearchResponse(BaseModel):
    type: str  # 'follow_up' or 'answer'
    questions: list[str] | None  # Only if type='follow_up'
    searches: list[WebSearchItem] | None  # Only if type='answer'
```

### 2. **Research Manager** (`research_manager.py`)

**Responsibilities:**
- Orchestrate the research workflow
- Handle the follow_up flow by halting when clarifications are required
- Coordinate between agents (planner, search, writer, email)
- Stream status updates

**Key Features:**
- Can pause and convey clarifying questions to the caller when `require_clarifications=True`
- Optional `chat_callback` remains available for other interfaces, though the Gradio app passes clarifications directly
- Graceful fallback if no chat interface available
- Yields status updates for streaming to UI

**Workflow:**
```
1. Call planner agent
2. If response.type == 'follow_up':
   - Surface questions to the UI / caller and collect user answers
   - Re-run planner with clarified query
3. If response.type == 'answer':
   - Proceed with searches
4. Continue with search → write → email flow
```

### 3. **Interactive Gradio Interface** (`deep_research_interactive.py`)

**Implementation Pattern: Two-Phase Approach**

**Phase 1 - Clarification Check:**
1. User submits initial query
2. Invoke `ResearchManager.run(..., require_clarifications=True)` to check clarity
3. If `type='follow_up'`: Display questions and wait for user's next message
4. If `type='answer'`: Proceed directly to Phase 2

**Phase 2 - Research Execution:**
1. Run full ResearchManager workflow
2. Pass any collected clarification text via the `clarification_answers` argument
3. Stream status updates to chat interface
4. Display final report

**State Management:**
```python
state = {
    "phase": "initial" | "waiting_for_answers" | "researching" | "complete",
    "query": str,
}
```

## Design Decisions

### Why Path A?

**Chosen:** Agentic Planner + ResearchManager as Orchestrator

**Rejected:** ResearchManager as fully agentic with tool-wrapped agents

**Reasoning:**
1. **Separation of concerns**: Complex decisions (clarity) vs workflow orchestration
2. **Gradio compatibility**: Clear points where user interaction happens
3. **Cost efficiency**: Only one agent making routing decisions
4. **Maintainability**: Easy to understand and debug
5. **Flexibility**: ResearchManager can be used with or without chat interface

### Why Two-Phase Approach for Gradio?

**Challenge:** Can't pause async generator mid-execution to wait for user input

**Solution:** Separate clarification phase from execution phase

**Benefits:**
- Clean async flow without complex state management
- Easy to test each phase independently
- Matches user mental model: "answer questions first, then research"
- No generator suspension/resumption complexity

## File Changes Summary

### Modified Files:
1. **`planner_agent.py`**
   - Enhanced instructions for clarity evaluation
   - Updated `ResearchResponse` model with optional fields
   - Removed dependency on separate query_clarification agent

2. **`research_manager.py`**
   - Added optional `chat_callback` parameter to `run()`
   - Implemented follow_up handling in `plan_searches()`
   - Added fallback for non-interactive mode

### New Files:
1. **`deep_research_interactive.py`**
   - Full chatbot interface with clarification support
   - Two-phase implementation (clarification check + research execution)
   - Comprehensive documentation and examples

### Deleted Files:
1. **`query_clarification.py`** - No longer needed (planner handles this now)

## Usage

### Non-Interactive Mode (Simple)

```python
# In deep_research.py
async def run(query: str):
    async for chunk in ResearchManager().run(query):
        yield chunk
```

Use when:
- No user interaction needed
- Running batch research
- Query is already clear

### Interactive Mode (With Clarification)

```python
# In deep_research_interactive.py
# Automatically handles clarification flow
# User sees questions if needed, provides answers, then research runs
```

Use when:
- User-facing application
- Queries may be ambiguous
- Want to ensure high-quality, targeted research

## Testing Recommendations

### Test Cases:

1. **Clear Query**
   - Input: "Recent quantum computing breakthroughs in error correction from 2023-2024"
   - Expected: Planner returns type='answer', proceeds directly to research

2. **Unclear Query**
   - Input: "AI stuff"
   - Expected: Planner returns type='follow_up' with 2-3 questions about scope, time, depth

3. **Non-Interactive with Unclear Query**
   - Input: "blockchain" with `chat_callback=None`
   - Expected: Proceeds with best interpretation

4. **Interactive Flow**
   - Input: "machine learning"
   - Expected: Questions asked, user answers, research proceeds with context

## Future Enhancements

### Potential Improvements:

1. **Multi-Turn Clarification**
   - Currently: One round of questions
   - Enhancement: Allow planner to ask follow-up questions if answers are still unclear

2. **Clarification Templates**
   - Pre-defined question templates for common scenarios
   - Faster response, more consistent

3. **User Preferences**
   - Remember user's preferences (depth, time period, style)
   - Reduce clarification needs over time

4. **Partial Search Results**
   - Start searches while waiting for all clarifications
   - Parallelize when possible

5. **Structured Answer Format**
   - Instead of free-form answers, use structured inputs (dropdowns, sliders)
   - Better for mobile UX

## Conclusion

This implementation successfully achieves:
- ✅ Autonomous decision-making (planner decides when to clarify)
- ✅ Clean separation of concerns (planning vs orchestration)
- ✅ Gradio-compatible chat interface
- ✅ Graceful fallback for non-interactive use
- ✅ Maintainable and extensible architecture

The two-phase approach provides a clean, debuggable solution that works seamlessly with Gradio's event model while maintaining the flexibility of the ResearchManager orchestrator pattern.


