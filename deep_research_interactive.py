"""
Interactive Deep Research with Clarifying Questions
This version uses a chatbot interface to ask clarifying questions when needed
"""

import gradio as gr
from dotenv import load_dotenv
from research_manager import ResearchManager
import asyncio

load_dotenv(override=True)


class ClarificationNeeded(Exception):
    """Raised when the research manager needs user clarification."""

    def __init__(self, questions: list[str]):
        super().__init__("Clarification needed")
        self.questions = questions


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
    if state is None or len(state) == 0:
        state = {
            "phase": "initial",  # initial, waiting_for_answers, researching, complete
            "query": None,
        }
    
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
            state["phase"] = "researching"
            async for chunk in run_research(
                state["query"],
                history,
                require_clarifications=True,
            ):
                yield "", chunk, state
            
            state["phase"] = "complete"
            yield "", history, state
        except ClarificationNeeded as clar:
            state["phase"] = "waiting_for_answers"
            yield "", history, state
    
    # PHASE: User is providing answers to clarifying questions
    elif state["phase"] == "waiting_for_answers":
        answers = message
        
        history.append([message, ""])
        history[-1][1] = "**[System]**: Thank you for the clarifications! Starting research...\n\n"
        yield "", history, state
        
        await asyncio.sleep(0.5)
        
        try:
            state["phase"] = "researching"
            async for chunk in run_research(
                state["query"],
                history,
                require_clarifications=True,
                clarification_answers=answers,
            ):
                yield "", chunk, state
            
            state["phase"] = "complete"
            yield "", history, state
        except ClarificationNeeded:
            # Still unclear – ask additional questions
            state["phase"] = "waiting_for_answers"
            yield "", history, state
        
    # PHASE: Research complete - acknowledge messages
    else:
        history.append([message, ""])
        history[-1][1] = "**[System]**: Research already completed! Clear the chat to start a new research."
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
    
    try:
        async for status in manager.run(
            query,
            clarification_answers=clarification_answers,
            require_clarifications=require_clarifications,
        ):
            # Manager needs clarification – format and propagate
            if isinstance(status, dict) and status.get("type") == "clarification_needed":
                questions = status.get("questions", [])
                questions_text = "\n**[Planner]**: I need some clarification to better understand your research needs:\n\n"
                for i, q in enumerate(questions, 1):
                    questions_text += f"**{i}.** {q}\n\n"
                questions_text += "_Please answer these questions in your next message. You can answer in free form._"
                
                history[-1][1] += questions_text
                yield history
                raise ClarificationNeeded(questions)

            # Update status in the last message
            if isinstance(status, str) and status.startswith("View trace:"):
                history[-1][1] += f"\n_{status}_\n\n"
            elif isinstance(status, str) and status.startswith("#"):
                # Final report - replace the message with the report
                history[-1][1] = status
            else:
                history[-1][1] += f"**[Status]**: {status}\n\n"
            
            yield history
            await asyncio.sleep(0.2)
    except ClarificationNeeded:
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
    
    This implementation uses a **two-phase approach**:
    
    1. **Phase 1 - Clarification Check**: 
       - Run planner agent to evaluate query clarity
       - If unclear: Ask questions and wait for user response
       - If clear: Proceed directly to research
    
    2. **Phase 2 - Research Execution**:
       - Run full research workflow with clarified/original query
       - Stream status updates to the chat interface
       - Display final report
    
    **Key Benefits:**
    - Clean separation of concerns
    - Easy to debug and maintain
    - Works seamlessly with Gradio's async event model
    - Planner agent makes autonomous decisions about when clarification is needed
    
    See `deep_research.py` for a simpler non-interactive version.
    """)


if __name__ == "__main__":
    demo.launch(inbrowser=True)

