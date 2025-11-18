from pydantic import BaseModel, Field
from agents import Agent

HOW_MANY_SEARCHES = 5

INSTRUCTIONS = f"""You are a helpful research assistant. Your job is to analyze a research query and decide on the best course of action.

**First, analyze if the query is clear enough to research:**
- If the query is UNCLEAR, AMBIGUOUS, or would benefit from clarification: Return type='follow_up' with 2-3 clarifying questions
- If the query is CLEAR and specific enough: Return type='answer' with {HOW_MANY_SEARCHES} web search terms

**What makes a query unclear?**
- Missing time period (e.g., "recent developments" vs "since 2020")
- Ambiguous scope (e.g., "AI impact" - impact on what? business? society? education?)
- Unclear depth (e.g., should it be technical deep-dive or high-level overview?)
- Multiple possible interpretations
- Missing context about target audience or purpose

**When generating clarifying questions:**
- Ask about the most important ambiguities first
- Keep questions focused and actionable
- Limit to 2-3 questions maximum
- Questions should help you create better, more targeted searches

**When generating search queries:**
- Each search should have a clear reason tied to answering the original query
- Searches should cover different aspects/angles of the query
- Make searches specific enough to get quality results
"""


class WebSearchItem(BaseModel):
    reason: str = Field(description="Your reasoning for why this search is important to the query.")
    query: str = Field(description="The search term to use for the web search.")


class ResearchResponse(BaseModel):
    type: str = Field(description="The type of response: 'follow_up' if clarification needed, 'answer' if ready to search")
    questions: list[str] | None = Field(default=None, description="List of 2-3 clarifying questions (only if type='follow_up')")
    searches: list[WebSearchItem] | None = Field(default=None, description="List of web searches to perform (only if type='answer')")

   
planner_agent = Agent(
    name="PlannerAgent",
    instructions=INSTRUCTIONS,
    model="gpt-4o-mini",
    output_type=ResearchResponse
)