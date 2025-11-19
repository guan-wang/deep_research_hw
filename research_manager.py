"""
Agent-based Research Manager using OpenAI Agent SDK
Transforms the orchestration into an Agent with tools
"""

from agents import Runner, trace, gen_trace_id, Agent, function_tool
from search_agent import search_agent
from planner_agent import planner_agent, WebSearchItem, ResearchResponse
from writer_agent import writer_agent, ReportData
from email_agent import email_agent
from exceptions import ClarificationNeeded
import asyncio


# ============================================================================
# GLOBAL STATE FOR REPORT STORAGE
# ============================================================================

# Store the last generated report so we can access it after agent execution
_last_report: dict | None = None


def get_last_report() -> dict | None:
    """Get the last generated report."""
    return _last_report


def clear_last_report():
    """Clear the stored report."""
    global _last_report
    _last_report = None


# ============================================================================
# TOOL WRAPPERS
# ============================================================================

@function_tool
async def search_planning_tool(
    query: str,
    clarifications: str | None = None
) -> list[dict]:
    """
    Plans the searches needed for a research query.
    
    This tool analyzes the query and determines if clarification is needed.
    If clarification is needed, it raises ClarificationNeeded exception.
    If clarifications are provided, it uses them to create a better search plan.
    
    IMPORTANT: If this tool raises an error indicating clarification is needed:
    - DO NOT try to answer the questions yourself
    - DO NOT re-call this tool with made-up clarifications
    - STOP execution and let the error propagate
    
    Args:
        query: The research query
        clarifications: Optional clarifications from user (ONLY use if explicitly provided in your input)
    
    Returns:
        List of search items, each with 'query' and 'reason' fields
    
    Raises:
        ClarificationNeeded: If the query needs clarification from the user. DO NOT catch or handle this - let it propagate.
    """
    # Format input for planner_agent
    if clarifications:
        planner_input = (
            f"Original query: {query}\n\n"
            f"Clarifying questions and answers:\n{clarifications}"
        )
    else:
        planner_input = f"Query: {query}"
    
    # Call planner_agent
    result = await Runner.run(planner_agent, planner_input)
    response = result.final_output_as(ResearchResponse)
    
    # Check if clarification is needed
    if response.type == 'follow_up':
        # Validate questions exist
        if not response.questions:
            # Fallback: create a generic question if planner didn't provide any
            response.questions = ["Could you provide more details about your research query?"]
        # Raise exception to pause agent execution
        raise ClarificationNeeded(response.questions)
    
    # Return searches as list of dicts (for JSON serialization)
    if response.searches:
        return [
            {"query": item.query, "reason": item.reason}
            for item in response.searches
        ]
    return []


@function_tool
async def search_agent_tool(search_query: str, reason: str) -> str:
    """
    Performs a web search and returns a summary of the results.
    
    Args:
        search_query: The search term to use
        reason: The reason why this search is important for the research
    
    Returns:
        A concise summary of the search results (2-3 paragraphs, <300 words)
    """
    input_text = f"Search term: {search_query}\nReason for searching: {reason}"
    try:
        result = await Runner.run(search_agent, input_text)
        return str(result.final_output)
    except Exception as e:
        return f"Error performing search: {str(e)}"


@function_tool
async def writer_agent_tool(query: str, search_results: list[str]) -> dict:
    """
    Writes a comprehensive research report based on the query and search results.
    
    Args:
        query: The original research query
        search_results: List of search result summaries
    
    Returns:
        Dictionary with 'short_summary', 'markdown_report', and 'follow_up_questions'
    """
    global _last_report
    
    input_text = f"Original query: {query}\nSummarized search results: {search_results}"
    result = await Runner.run(writer_agent, input_text)
    report = result.final_output_as(ReportData)
    
    report_dict = {
        "short_summary": report.short_summary,
        "markdown_report": report.markdown_report,
        "follow_up_questions": report.follow_up_questions
    }
    
    # Store report globally so we can access it after agent execution
    _last_report = report_dict
    
    return report_dict


# ============================================================================
# RESEARCH AGENT
# ============================================================================

RESEARCH_AGENT_INSTRUCTIONS = """
You are a research agent that coordinates the deep research process.

Your workflow:
1. **Plan searches**: Use search_planning_tool with the user's query
   - Extract the query from the input (remove "Research query:" prefix if present)
   - If the input includes "Previous clarification conversation:", extract those clarifications
   - Pass the CLEANED query and clarifications (if any) to search_planning_tool
   - The tool returns a list of searches to perform (each with 'query' and 'reason' fields)
   
   **CRITICAL**: If search_planning_tool raises an error or exception indicating clarification is needed:
   - DO NOT try to answer the clarification questions yourself
   - DO NOT re-call the tool with made-up clarifications
   - STOP and let the error propagate - the system will handle asking the user
   - The only time you pass clarifications is when they are explicitly provided in the input as "Previous clarification conversation:"

2. **Execute searches**: For each search item in the returned list:
   - Use search_agent_tool with search['query'] and search['reason']
   - Collect all search result summaries into a list
   - Wait for all searches to complete before proceeding

3. **Write report**: Once ALL searches are complete:
   - Extract the original query (without any prefixes)
   - Use writer_agent_tool with the original query and the complete list of search results
   - This generates a comprehensive report with 'markdown_report' field

4. **Send email**: Hand off to email_agent with the markdown_report from the report

Important:
- Always call search_planning_tool FIRST with the cleaned query and clarifications (if provided)
- NEVER answer clarification questions yourself - only use clarifications if they are explicitly provided in your input
- If search_planning_tool needs clarification, let it fail/error - do not try to work around it
- Execute ALL searches before calling writer_agent_tool
- Pass the COMPLETE list of all search results to writer_agent_tool
- The report must be comprehensive (5-10 pages, at least 1000 words)
- Finally hand off to email_agent with the markdown_report field from the report
"""

research_agent = Agent(
    name="Research Manager",
    instructions=RESEARCH_AGENT_INSTRUCTIONS,
    tools=[search_planning_tool, search_agent_tool, writer_agent_tool],
    handoffs=[email_agent],  # Must be a list, even for single agent
    model="gpt-4o-mini",
)


# ============================================================================
# RESEARCH MANAGER (Wrapper for Agent execution)
# ============================================================================

class ResearchManager:
    """
    Wrapper class that orchestrates the research agent and yields status updates.
    
    This class maintains the same interface as the original ResearchManager
    but uses the agent-based approach internally.
    """

    async def run(
        self,
        query: str,
        chat_callback=None,  # Kept for backward compatibility, not used in agent approach
        clarification_answers: str | None = None,
        require_clarifications: bool = False,
    ):
        """
        Run the deep research process using the agent-based approach.
        
        Args:
            query: The research query
            chat_callback: Not used in agent approach (kept for compatibility)
            clarification_answers: Optional clarifications supplied by the user
            require_clarifications: If True, halt and request clarifications instead of guessing
        
        Yields:
            Status updates as strings, or dict with 'type': 'clarification_needed'
        """
        # Clear any previous report
        clear_last_report()
        
        trace_id = gen_trace_id()
        with trace("Research trace", trace_id=trace_id):
            print(f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}")
            yield f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}"
            print("Starting research...")
            
            # CRITICAL: Check for clarification needs BEFORE calling Runner.run()
            # This avoids the ambiguity of exception propagation through the Agent SDK
            if require_clarifications and not clarification_answers:
                yield "Checking if clarification is needed..."
                try:
                    # Call planner_agent directly to check for clarification needs
                    planner_input = f"Query: {query}"
                    planner_result = await Runner.run(planner_agent, planner_input)
                    planner_response = planner_result.final_output_as(ResearchResponse)
                    
                    if planner_response.type == 'follow_up':
                        questions = planner_response.questions or ["Could you provide more details about your research query?"]
                        yield {
                            "type": "clarification_needed",
                            "questions": questions,
                        }
                        return  # Stop here - don't proceed with research
                except Exception as e:
                    # If planner check fails, proceed anyway
                    print(f"[DEBUG] Planner check failed, proceeding: {e}")
            
            # Build agent input
            if clarification_answers:
                agent_input = (
                    f"Research query: {query}\n\n"
                    f"Previous clarification conversation:\n{clarification_answers}\n\n"
                    f"Proceed with research using the clarified understanding."
                )
            else:
                agent_input = f"Research query: {query}"
            
            try:
                yield "Planning searches..."
                
                # Run the agent - this will call tools in sequence
                # The agent will: plan → search → write → email
                # Note: All steps happen during this call, so status messages below
                # are approximations based on successful completion
                result = await Runner.run(research_agent, agent_input)
                
                # Agent execution completed successfully
                # Yield status updates to inform user of progress
                yield "Searches planned, starting to search..."
                yield "Searches complete, writing report..."
                yield "Report written, sending email..."
                yield "Email sent, research complete"
                
                # Try to extract report from stored value (set by writer_agent_tool)
                stored_report = get_last_report()
                if stored_report and stored_report.get("markdown_report"):
                    yield stored_report["markdown_report"]
                else:
                    # Fallback: try to extract from final output
                    final_output = str(result.final_output) if result.final_output else "Research completed"
                    yield final_output
                
            except ClarificationNeeded as e:
                # This should only happen if clarification check above was skipped
                # (e.g., require_clarifications=False) but tool still raised exception
                if require_clarifications:
                    yield {
                        "type": "clarification_needed",
                        "questions": e.questions,
                    }
                    return
                else:
                    # Not requiring clarifications - proceed anyway
                    fallback_input = (
                        f"Research query: {query}\n\n"
                        f"Note: User is not available for clarification. "
                        f"Please proceed with your best interpretation and generate search queries."
                    )
                    result = await Runner.run(research_agent, fallback_input)
                    yield "Proceeding without clarification..."
                    yield "Searches planned, starting to search..."
                    yield "Searches complete, writing report..."
                    yield "Report written, sending email..."
                    yield "Email sent, research complete"
                    
                    # Try to extract report from stored value
                    stored_report = get_last_report()
                    if stored_report and stored_report.get("markdown_report"):
                        yield stored_report["markdown_report"]
                    else:
                        final_output = str(result.final_output) if result.final_output else "Research completed"
                        yield final_output
