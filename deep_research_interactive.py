"""
Interactive Deep Research with Clarifying Questions
This version uses a chatbot interface to ask clarifying questions when needed
"""

import gradio as gr
from dotenv import load_dotenv
from research_manager import ResearchManager
from exceptions import ClarificationNeeded
import asyncio

load_dotenv(override=True)


async def research_chatbot(message, history, state):
    """
    Chatbot function that handles the interactive research flow using a two-phase approach.
    
    Phase 1: Check if clarification needed, ask questions if needed, get answers
    Phase 2: Run full research workflow with clarified query
    
    Args:
        message: User's current message
        history: Chat history
        state: Persistent state across messages
    
    Yields:
        tuple: (cleared_input, updated_history, updated_state)
    """
    # Initialize state on first call
    if state is None or not state:
        state = {
            "phase": "initial",  # initial, waiting_for_answers, researching, complete
            "query": None,
        }
    
    # Debug: Log incoming state
    current_phase = state.get("phase", "unknown")
    print(f"[DEBUG] research_chatbot called with phase: {current_phase}, message: {message[:50]}")
    
    # PHASE: Initial query submission
    if state["phase"] == "initial":
        state["query"] = message
        
        # Start with user's message
        history.append([message, ""])
        history[-1][1] = "**[System]**: Analyzing your query...\n"
        yield "", history, state
        
        await asyncio.sleep(0.5)
        
        history[-1][1] += "**[Planner]**: Evaluating query clarity...\n"
        yield "", history, state
        
        try:
            # require_clarifications defaults to True, which is correct for interactive mode
            # Keep phase as "initial" during execution - only change after we know the outcome
            research_completed = False
            clarification_seen = False
            
            try:
                async for chunk in run_research(
                    state["query"],
                    history,
                ):
                    # Note: chunk is the history list, not the dict
                    print(f"[DEBUG] Received chunk from run_research, yielding to Gradio")
                    yield "", chunk, state
                    print(f"[DEBUG] After yield - this should NOT execute if exception was raised")
                    # CRITICAL: Don't set research_completed here - if exception is raised
                    # after the yield above, this line won't execute, which is what we want
                    
                # If we reach here WITHOUT exception, loop completed normally
                print(f"[DEBUG] async for loop completed normally (no exception), setting research_completed")
                research_completed = True
            except StopAsyncIteration:
                # This shouldn't happen with our code, but catch it just in case
                print(f"[DEBUG] StopAsyncIteration caught - generator exhausted normally")
                research_completed = True
            
            # If we reach here WITHOUT ClarificationNeeded exception, all iterations completed successfully
            # But only set to complete if we actually completed research
            if research_completed:
                print(f"[DEBUG] Loop completed normally without exception, setting phase to complete")
                state["phase"] = "complete"
                yield "", history, state
        except ClarificationNeeded as clar:
            # Exception was raised - clarification needed
            print(f"[DEBUG] Exception caught in except handler, setting phase to waiting_for_answers")
            # Set phase BEFORE yielding to ensure state is updated
            state["phase"] = "waiting_for_answers"
            print(f"[DEBUG] Phase set to: {state['phase']}")
            # Verify state was set correctly before yielding
            assert state["phase"] == "waiting_for_answers", f"State phase not set correctly: {state.get('phase')}"
            yield "", history, state
            print(f"[DEBUG] Yielding with phase: {state.get('phase')}, returning from function")
            # Critical: return here to prevent any code after the try/except from executing
            return
    
    # PHASE: User is providing answers to clarifying questions
    elif state.get("phase") == "waiting_for_answers":
        print(f"[DEBUG] Entering waiting_for_answers phase with query: {state.get('query', 'None')}")
        answers = message
        
        history.append([message, ""])
        history[-1][1] = "**[System]**: Thank you for the clarifications! Starting research...\n\n"
        yield "", history, state
        
        await asyncio.sleep(0.5)
        
        try:
            # require_clarifications defaults to True, which is correct for interactive mode
            research_completed = False
            async for chunk in run_research(
                state["query"],
                history,
                clarification_answers=answers,
            ):
                yield "", chunk, state
                research_completed = True
            
            # Only set to complete if we actually completed research without exception
            if research_completed:
                state["phase"] = "complete"
                yield "", history, state
        except ClarificationNeeded:
            # Still unclear – ask additional questions
            state["phase"] = "waiting_for_answers"
            yield "", history, state
            return  # Exit to prevent further execution
        
    # PHASE: Research complete - acknowledge messages
    else:
        # Debug: Log what phase we're actually in
        current_phase = state.get("phase", "unknown")
        print(f"[DEBUG] Hit else block! Current phase: {current_phase}, state keys: {list(state.keys()) if state else 'None'}")
        history.append([message, ""])
        history[-1][1] = f"**[System]**: Research already completed! (Current phase: {current_phase}) Clear the chat to start a new research."
        yield "", history, state


async def run_research(
    query,
    history,
    require_clarifications: bool = True,
    clarification_answers: str | None = None,
):
    """
    Run the research workflow and yield updates to the chat history.
    
    Args:
        query: The research query
        history: Chat history to update
        require_clarifications: Whether the manager should pause for clarifications
        clarification_answers: Clarification text supplied by the user (if available)
    
    Yields:
        Updated history
    """
    manager = ResearchManager()
    clarification_questions = None  # Track if clarification was seen
    
    try:
        async for status in manager.run(
            query,
            clarification_answers=clarification_answers,
            require_clarifications=require_clarifications,
        ):
            print(f"[DEBUG] run_research: Received status from manager.run: type={type(status)}, value={status}")
            # Manager needs clarification – format and propagate
            if isinstance(status, dict) and status.get("type") == "clarification_needed":
                print(f"[DEBUG] run_research: Detected clarification_needed dict!")
                questions = status.get("questions", [])
                # Validate questions exist
                if not questions:
                    questions = ["Could you provide more details about your research query?"]
                
                # Store questions to raise exception after yielding
                clarification_questions = questions
                
                questions_text = "\n**[Planner]**: I need some clarification to better understand your research needs:\n\n"
                for i, q in enumerate(questions, 1):
                    questions_text += f"**{i}.** {q}\n\n"
                questions_text += "_Please answer these questions in your next message. You can answer in free form._"
                
                history[-1][1] += questions_text
                yield history
                print(f"[DEBUG] run_research: Yielded clarification questions, breaking now")
                # Break out of loop immediately - don't continue processing
                break
            
            # Only process other statuses if we didn't see clarification
            # Update status in the last message
            if isinstance(status, str) and status.startswith("View trace:"):
                history[-1][1] += f"\n_{status}_\n\n"
            elif isinstance(status, str) and status.startswith("#"):
                # Final report - replace the message with the report
                history[-1][1] = status
            else:
                history[-1][1] += f"**[Status]**: {status}\n\n"
            
            yield history
            print(f"[DEBUG] run_research: After yield - continuing loop")
            await asyncio.sleep(0.2)
        
        # After loop exits: check if we broke out due to clarification
        if clarification_questions is not None:
            print(f"[DEBUG] run_research: Loop exited due to clarification, raising exception with {len(clarification_questions)} questions")
            raise ClarificationNeeded(clarification_questions)
            
    except ClarificationNeeded as e:
        print(f"[DEBUG] run_research: Caught ClarificationNeeded, re-raising with {len(e.questions) if e.questions else 0} questions")
        raise
    except Exception as e:
        history[-1][1] += f"\n\n**[Error]**: {str(e)}\n\n"
        history[-1][1] += "_Please try again or rephrase your query._"
        yield history


# ============================================================================
# CREATE THE GRADIO INTERFACE
# ============================================================================

with gr.Blocks(theme=gr.themes.Default(primary_hue="blue")) as demo:
    gr.Markdown("# 🔬 Deep Research - Interactive Mode")
    gr.Markdown("""
    This interactive research assistant can ask clarifying questions to better understand your needs.
    
    **How to use:**
    1. Enter your research topic in the text box below
    2. If the topic is unclear, the planner will ask 2-3 clarifying questions
    3. Answer the questions in free-form text
    4. The system will continue with the research based on your clarifications
    5. Wait for the full research report to be generated
    
    **Examples of queries:**
    - Clear: "Recent quantum computing breakthroughs in error correction from 2023-2024"
    - Unclear: "AI stuff" (will ask clarifying questions about scope, time period, depth)
    """)
    
    chatbot = gr.Chatbot(label="Research Assistant", height=600, type="tuples")
    msg = gr.Textbox(
        label="Your message", 
        placeholder="Enter your research topic (e.g., 'machine learning applications in healthcare')...",
        lines=3
    )
    
    with gr.Row():
        send = gr.Button("Send", variant="primary")
        clear = gr.Button("Clear Chat")
    
    # State to persist data across interactions
    state = gr.State()
    
    # Wire up the events. Capture both the click (button) and the submit event (enter key) of the textbox.
    send.click(
        research_chatbot,
        inputs=[msg, chatbot, state],
        outputs=[msg, chatbot, state]
    )
    msg.submit(
        research_chatbot,
        inputs=[msg, chatbot, state],
        outputs=[msg, chatbot, state]
    )
    
    # Clear button resets everything
    clear.click(
        lambda: ([], "", None),
        outputs=[chatbot, msg, state]
    )
    
    gr.Markdown("""
    ---
    ### 💡 Architecture
    
    This implementation uses an **Agent-based architecture with exception-based clarification**:
    
    1. **Research Manager Agent**:
       - Transformed into an OpenAI Agent SDK `Agent` with tools
       - Tools: `search_planning_tool`, `search_agent_tool`, `writer_agent_tool`
       - Each tool wraps an existing agent (planner_agent, search_agent, writer_agent)
       - Agent autonomously orchestrates: plan → search → write → email
       - Hands off to `email_agent` for final delivery
    
    2. **Exception-Based Clarification Flow**:
       - When `search_planning_tool` detects unclear query, it raises `ClarificationNeeded(questions)`
       - Exception propagates: Tool → Agent SDK → `Runner.run()` → `ResearchManager.run()`
       - `ResearchManager.run()` catches it, yields `{"type": "clarification_needed", "questions": [...]}`, returns
       - `run_research()` receives dict, formats questions, yields history, breaks out of loop, raises exception
       - `research_chatbot()` catches exception, sets `state["phase"] = "waiting_for_answers"`, yields state
       - User provides answers → Agent re-run with enriched input: `"Research query: {query}\\n\\nPrevious clarification conversation:\\n{answers}"`
    
    3. **State Management** (Gradio-Level):
       - State: `{"phase": "initial" | "waiting_for_answers" | "complete", "query": str}`
       - Phase transitions:
         * `"initial"` → Attempt research → Exception? → `"waiting_for_answers"` | Success → `"complete"`
         * `"waiting_for_answers"` → User provides answers → Research re-run → `"complete"` | Still unclear → `"waiting_for_answers"`
       - Critical: Phase only changes AFTER outcome is known (never set prematurely)
       - Query persists across clarification rounds in state
    
    4. **Break + Raise Pattern**:
       - When clarification dict detected: `break` out of loop immediately
       - After loop exits: check if clarification was seen, raise exception
       - Prevents loop from completing normally when clarification needed
       - Ensures exception propagates correctly to outer handler
    
    **Key Benefits:**
    - ✅ Agent-based orchestration (autonomous, flexible workflow)
    - ✅ Exception-based control flow (clean async generator integration)
    - ✅ Tool composition (existing agents as reusable tools)
    - ✅ Clean separation: Gradio handles UI/state, Agent handles research logic
    - ✅ No agent-internal state needed (all context via input enrichment)
    - ✅ Planner makes autonomous decisions about clarification needs
    
    **Implementation Details:**
    - Exception message is minimal ("USER_CLARIFICATION_REQUIRED") to prevent agent from trying to answer questions itself
    - Agent instructions explicitly forbid working around clarification exceptions
    - Tool docstrings warn against handling clarification exceptions
    - Global state used to access final report after agent execution completes
    
    See `deep_research.py` for a simpler non-interactive version.
    See `ARCHITECTURE.md` for detailed architecture documentation.
    """)


if __name__ == "__main__":
    demo.launch(inbrowser=True)

