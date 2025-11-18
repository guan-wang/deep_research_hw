"""
Simple Gradio Chatbot Demo
This file demonstrates the basic usage of gr.Chatbot() component
"""

import gradio as gr
import asyncio

# ============================================================================
# UNDERSTANDING CHATBOT MESSAGE FORMAT
# ============================================================================
# Gradio Chatbot uses a list of tuples/lists to represent chat history:
# Each message is: [user_message, assistant_message]
# Example: [["Hello", "Hi there!"], ["How are you?", "I'm doing great!"]]
#
# - user_message: What the user said (left side of chat bubble)
# - assistant_message: What the assistant replied (right side of chat bubble)
# - You can use None for assistant_message if the assistant hasn't responded yet


# ============================================================================
# BASIC SYNCHRONOUS CHATBOT
# ============================================================================

def simple_respond(message, history):
    """
    Simple synchronous response function.
    
    Args:
        message (str): The new message the user just sent
        history (list): The conversation history up to this point
                       Format: [[user_msg1, bot_msg1], [user_msg2, bot_msg2], ...]
    
    Returns:
        tuple: (empty_string, updated_history)
               - First element: clears the input textbox
               - Second element: updated chat history to display
    """
    # Create a simple echo response
    bot_response = f"You said: '{message}'. I understand!"
    
    # Append the new exchange to history
    history.append([message, bot_response])
    
    # Return empty string (clears input box) and updated history
    return "", history


# ============================================================================
# ASYNC CHATBOT WITH STREAMING
# ============================================================================

async def streaming_respond(message, history):
    """
    Async response function that streams the response word-by-word.
    This is useful for showing progressive output from LLMs or long-running tasks.
    
    Args:
        message (str): The new message the user just sent
        history (list): The conversation history
    
    Yields:
        tuple: (empty_string, updated_history) at each step
    """
    # Start with the user's message and empty bot response
    history.append([message, ""])
    
    # Simulate streaming by adding words one at a time
    bot_response = f"You said: '{message}'. Let me think about this..."
    words = bot_response.split()
    
    for i, word in enumerate(words):
        # Build up the response progressively
        partial_response = " ".join(words[:i+1])
        
        # Update the last message in history (the bot's response)
        history[-1][1] = partial_response
        
        # Yield the updated history (this updates the UI)
        yield "", history
        
        # Small delay to simulate thinking/streaming
        await asyncio.sleep(0.1)


# ============================================================================
# MULTI-AGENT CHATBOT (Your Use Case)
# ============================================================================

async def multi_agent_respond(message, history):
    """
    Example showing how multiple "agents" can contribute to the conversation.
    This demonstrates how you could have different agents asking clarifying questions.
    
    Args:
        message (str): User's input
        history (list): Chat history
    
    Yields:
        tuple: Updated history after each agent responds
    """
    # Agent 1: Planner responds
    history.append([message, ""])
    planner_msg = "**[Planner]**: I'm analyzing your request..."
    history[-1][1] = planner_msg
    yield "", history
    await asyncio.sleep(1)
    
    # Agent 2: Planner asks for clarification
    planner_msg += "\n\n**[Planner]**: Before I proceed, could you clarify if you want a detailed or brief analysis?"
    history[-1][1] = planner_msg
    yield "", history
    await asyncio.sleep(1)
    
    # In a real implementation, you would:
    # 1. Wait for user's next message (this happens automatically - Gradio will call this function again)
    # 2. Check the user's response
    # 3. Continue the workflow based on their answer
    
    # For this demo, we'll just acknowledge
    final_msg = planner_msg + "\n\n**[System]**: (Waiting for your response...)"
    history[-1][1] = final_msg
    yield "", history


# ============================================================================
# CHATBOT WITH USER INPUT HANDLING
# ============================================================================

async def clarifying_chatbot(message, history):
    """
    Example showing how to detect and handle user responses to agent questions.
    This is closer to what you'll need for your vetting agents.
    """
    # Check if this is the first message or a follow-up
    if len(history) == 0:
        # First interaction - agent asks a question
        history.append([message, ""])
        response = "**[Planner Agent]**: Got your research topic, let me try to plan the research... /n"
        # calls the planner agent with planner_agent(message) runner.run(). And then get planner response 
        response += "We need to ask some clarifying questions to better understand your research topic. What would you like to research? /n Do you want business or academic sources?"
        history[-1][1] = response
        yield "", history
    else:
        # User is responding to our question
        user_response = message.lower()
        
        history.append([message, ""])
        
        if "recent" in user_response:
            response = "**[Vetting Agent]**: Got it! I'll focus on recent sources from 2023-2025."
        elif "historical" in user_response:
            response = "**[Vetting Agent]**: Understood! I'll include historical context in my search."
        else:
            response = "**[Vetting Agent]**: I'll proceed with a balanced approach including both recent and historical sources."
        
        history[-1][1] = response
        yield "", history
        
        await asyncio.sleep(1)
        
        # Continue with next step
        history[-1][1] += "\n\n**[System]**: Proceeding with research..."
        yield "", history


# ============================================================================
# SEQUENTIAL CLARIFICATION WITH STATE (YOUR USE CASE!)
# ============================================================================

async def sequential_clarification(message, history, state):
    """
    Example showing how to ask 3 clarifying questions sequentially using gr.State().
    This is the RECOMMENDED approach for your multi-agent vetting workflow.
    
    Args:
        message (str): User's current message
        history (list): Chat history
        state (dict): Persistent state across function calls
    
    Yields:
        tuple: (cleared_input, updated_history, updated_state)
    """
    # Initialize state on first call (state comes in as None initially)
    if state is None or len(state) == 0:
        state = {
            "phase": 0,           # Which question we're on
            "topic": None,        # The research topic
            "answers": {}         # Collected answers
        }
    
    # PHASE 0: Initial topic submission
    if state["phase"] == 0:
        state["topic"] = message
        state["phase"] = 1
        
        history.append([message, ""])
        response = f"**[Clarification Agent]**: Great! I'll help you research: '{message}'\n\n"
        response += "**Question 1/3:** What time period should I focus on?\n"
        response += "- Type 'recent' for last 2 years\n"
        response += "- Type 'historical' for comprehensive timeline"
        history[-1][1] = response
        yield "", history, state
    
    # PHASE 1: Answer to Question 1 received
    elif state["phase"] == 1:
        state["answers"]["time_period"] = message
        state["phase"] = 2
        
        history.append([message, ""])
        response = f"**[Clarification Agent]**: Perfect! Time period set to: '{message}'\n\n"
        response += "**Question 2/3:** How detailed should the report be?\n"
        response += "- Type 'brief' for executive summary\n"
        response += "- Type 'detailed' for comprehensive analysis"
        history[-1][1] = response
        yield "", history, state
    
    # PHASE 2: Answer to Question 2 received
    elif state["phase"] == 2:
        state["answers"]["depth"] = message
        state["phase"] = 3
        
        history.append([message, ""])
        response = f"**[Clarification Agent]**: Excellent! Depth set to: '{message}'\n\n"
        response += "**Question 3/3:** Should I include source citations?\n"
        response += "- Type 'yes' to include citations\n"
        response += "- Type 'no' for plain report"
        history[-1][1] = response
        yield "", history, state
    
    # PHASE 3: Answer to Question 3 received - ALL QUESTIONS ANSWERED!
    elif state["phase"] == 3:
        state["answers"]["include_sources"] = message
        state["phase"] = 4  # Move to research phase
        
        history.append([message, ""])
        
        # Show summary of collected information
        response = "**[System]**: All clarifications received! ✅\n\n"
        response += "**Summary:**\n"
        response += f"- **Topic:** {state['topic']}\n"
        response += f"- **Time Period:** {state['answers']['time_period']}\n"
        response += f"- **Depth:** {state['answers']['depth']}\n"
        response += f"- **Include Sources:** {state['answers']['include_sources']}\n\n"
        
        history[-1][1] = response
        yield "", history, state
        
        await asyncio.sleep(1)
        
        # Simulate starting the research workflow
        history[-1][1] += "**[Planner Agent]**: Planning searches based on your preferences...\n"
        yield "", history, state
        
        await asyncio.sleep(1)
        
        history[-1][1] += "**[Search Agent]**: Executing 3 targeted searches...\n"
        yield "", history, state
        
        await asyncio.sleep(1)
        
        history[-1][1] += "**[Writer Agent]**: Compiling report...\n"
        yield "", history, state
        
        await asyncio.sleep(1)
        
        # Final result
        history[-1][1] += "\n**[System]**: ✨ Research complete! In your real implementation, "
        history[-1][1] += "this is where you'd call:\n"
        history[-1][1] += f"```\nresult = await Runner.run(planner_agent, state['topic'])\n```\n"
        history[-1][1] += f"\nYou have access to all answers in `state['answers']`!"
        yield "", history, state
    
    # PHASE 4: Research complete - just acknowledge any further messages
    else:
        history.append([message, ""])
        history[-1][1] = "**[System]**: Research already completed! Refresh to start a new research."
        yield "", history, state


# ============================================================================
# CREATE THE GRADIO INTERFACES
# ============================================================================

# Demo 1: Simple chatbot
with gr.Blocks() as demo1:
    gr.Markdown("# Demo 1: Simple Chatbot (Synchronous)")
    gr.Markdown("This chatbot echoes your message back. Notice the message format.")
    
    # The Chatbot component displays the conversation
    chatbot1 = gr.Chatbot(label="Simple Chat", height=300)
    
    # Textbox for user input
    msg1 = gr.Textbox(label="Your message", placeholder="Type something...")
    
    # Button to send (optional - can also use textbox.submit)
    send1 = gr.Button("Send")
    
    # Clear button to reset conversation
    clear1 = gr.Button("Clear")
    
    # Wire up the events
    # When user clicks send or presses enter, call simple_respond
    send1.click(simple_respond, inputs=[msg1, chatbot1], outputs=[msg1, chatbot1])
    msg1.submit(simple_respond, inputs=[msg1, chatbot1], outputs=[msg1, chatbot1])
    
    # Clear button resets chatbot to empty list
    clear1.click(lambda: ([], ""), outputs=[chatbot1, msg1])


# Demo 2: Streaming chatbot
with gr.Blocks() as demo2:
    gr.Markdown("# Demo 2: Streaming Chatbot (Async)")
    gr.Markdown("This chatbot streams the response word-by-word. Watch how it builds up!")
    
    chatbot2 = gr.Chatbot(label="Streaming Chat", height=300)
    msg2 = gr.Textbox(label="Your message", placeholder="Type something...")
    send2 = gr.Button("Send")
    clear2 = gr.Button("Clear")
    
    # Note: async functions work the same way in Gradio
    send2.click(streaming_respond, inputs=[msg2, chatbot2], outputs=[msg2, chatbot2])
    msg2.submit(streaming_respond, inputs=[msg2, chatbot2], outputs=[msg2, chatbot2])
    clear2.click(lambda: ([], ""), outputs=[chatbot2, msg2])


# Demo 3: Multi-agent chatbot
with gr.Blocks() as demo3:
    gr.Markdown("# Demo 3: Multi-Agent Chatbot")
    gr.Markdown("This shows how different agents can contribute. Notice the **[Agent Name]** prefixes.")
    
    chatbot3 = gr.Chatbot(label="Multi-Agent Chat", height=300)
    msg3 = gr.Textbox(label="Your message", placeholder="What would you like to research?")
    send3 = gr.Button("Send")
    clear3 = gr.Button("Clear")
    
    send3.click(multi_agent_respond, inputs=[msg3, chatbot3], outputs=[msg3, chatbot3])
    msg3.submit(multi_agent_respond, inputs=[msg3, chatbot3], outputs=[msg3, chatbot3])
    clear3.click(lambda: ([], ""), outputs=[chatbot3, msg3])


# Demo 4: Clarifying chatbot (closest to your use case)
with gr.Blocks() as demo4:
    gr.Markdown("# Demo 4: Clarifying Chatbot (Your Use Case)")
    gr.Markdown("This chatbot asks questions and processes your responses. Try it!")
    
    chatbot4 = gr.Chatbot(label="Research Assistant", height=400)
    msg4 = gr.Textbox(label="Your message", placeholder="Start by saying what you want to research...")
    send4 = gr.Button("Send")
    clear4 = gr.Button("Clear")
    
    send4.click(clarifying_chatbot, inputs=[msg4, chatbot4], outputs=[msg4, chatbot4])
    msg4.submit(clarifying_chatbot, inputs=[msg4, chatbot4], outputs=[msg4, chatbot4])
    clear4.click(lambda: ([], ""), outputs=[chatbot4, msg4])


# Demo 5: Sequential Clarification with State (RECOMMENDED for your use case!)
with gr.Blocks() as demo5:
    gr.Markdown("# Demo 5: Sequential Clarification with State ⭐")
    gr.Markdown("""
    This demo shows how to ask **3 sequential clarifying questions** using `gr.State()`.
    
    **This is the pattern you should use for your research workflow!**
    
    **Try it:**
    1. Type a research topic (e.g., "quantum computing")
    2. Answer the 3 clarifying questions one by one
    3. Watch how the state tracks your progress
    4. Notice how all agents can access the collected information
    
    **Key concepts:**
    - `gr.State()` persists data between function calls
    - State must be in both `inputs` and `outputs`
    - You can store any Python data structure in state
    """)
    
    chatbot5 = gr.Chatbot(label="Sequential Clarification Demo", height=500)
    msg5 = gr.Textbox(label="Your message", placeholder="Enter your research topic to begin...")
    send5 = gr.Button("Send")
    clear5 = gr.Button("Clear Chat")
    
    # The gr.State() component - this persists across function calls!
    state5 = gr.State()
    
    # IMPORTANT: Note that state5 is in BOTH inputs AND outputs
    send5.click(
        sequential_clarification, 
        inputs=[msg5, chatbot5, state5],      # ← state as input
        outputs=[msg5, chatbot5, state5]      # ← state as output
    )
    msg5.submit(
        sequential_clarification, 
        inputs=[msg5, chatbot5, state5],      # ← state as input
        outputs=[msg5, chatbot5, state5]      # ← state as output
    )
    
    # Clear button resets everything including state
    clear5.click(
        lambda: ([], "", None),               # ← Reset chat, textbox, AND state
        outputs=[chatbot5, msg5, state5]
    )


# ============================================================================
# LAUNCH THE DEMOS
# ============================================================================

# You can launch individual demos or combine them with tabs
with gr.Blocks(theme=gr.themes.Default(primary_hue="sky")) as demo:
    gr.Markdown("# Gradio Chatbot Learning Demos")
    gr.Markdown("Explore different chatbot patterns. Each tab shows a different approach.")
    
    with gr.Tabs():
        with gr.Tab("Simple"):
            demo1.render()
        with gr.Tab("Streaming"):
            demo2.render()
        with gr.Tab("Multi-Agent"):
            demo3.render()
        with gr.Tab("Clarifying"):
            demo4.render()
        with gr.Tab("⭐ Sequential Questions (BEST)"):
            demo5.render()


if __name__ == "__main__":
    demo.launch(inbrowser=True)

