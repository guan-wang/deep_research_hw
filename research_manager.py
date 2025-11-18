from agents import Runner, trace, gen_trace_id
from search_agent import search_agent
from planner_agent import planner_agent, WebSearchItem, ResearchResponse
from writer_agent import writer_agent, ReportData
from email_agent import email_agent
import asyncio

class ResearchManager:

    async def run(
        self,
        query: str,
        chat_callback=None,
        clarification_answers: str | None = None,
        require_clarifications: bool = False,
    ):
        """ 
        Run the deep research process, yielding status updates and the final report.
        
        Args:
            query: The research query
            chat_callback: Optional callback function for asking clarifying questions.
                          Should be an async function that takes questions list and returns answers string.
            clarification_answers: Optional clarifications supplied by the user
            require_clarifications: If True, halt and request clarifications instead of guessing
        """
        trace_id = gen_trace_id()
        with trace("Research trace", trace_id=trace_id):
            print(f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}")
            yield f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}"
            print("Starting research...")
            #key difference here is the new chat_callback argument to handle user clarification responses
            search_items, pending_questions = await self.plan_searches(
                query,
                chat_callback=chat_callback,
                clarification_answers=clarification_answers,
                require_clarifications=require_clarifications,
            )

            if pending_questions:
                yield {
                    "type": "clarification_needed",
                    "questions": pending_questions,
                }
                return

            yield "Searches planned, starting to search..."     
            search_results = await self.perform_searches(search_items)
            yield "Searches complete, writing report..."
            report = await self.write_report(query, search_results)
            yield "Report written, sending email..."
            await self.send_email(report)
            yield "Email sent, research complete"
            yield report.markdown_report
        

    async def plan_searches(
        self,
        query: str,
        chat_callback=None,
        clarification_answers: str | None = None,
        require_clarifications: bool = False,
    ) -> tuple[list[WebSearchItem] | None, list[str] | None]:
        """ 
        Plan the searches to perform for the query.
        If the query is unclear, may ask for clarification via chat_callback or by
        yielding the questions back to the caller when require_clarifications is True.
        
        Returns:
            Tuple of (searches, pending_questions). When pending_questions is not None,
            the caller should collect clarifications before continuing.
        """
        print("Planning searches...")
        result = await Runner.run(
            planner_agent,
            f"Query: {query}",
        )
        response = result.final_output_as(ResearchResponse)
        
        # Check if planner needs clarification
        if response.type == 'follow_up':
            if clarification_answers:
                clarified_input = (
                    "Original query: {query}\n\nClarifying questions and answers:\n{answers}"
                ).format(query=query, answers=clarification_answers)
                result = await Runner.run(
                    planner_agent,
                    clarified_input,
                )
                response = result.final_output_as(ResearchResponse)
            elif require_clarifications:
                return None, response.questions
            elif chat_callback is None:
                # No chat interface available, proceed without clarification
                print("Clarification needed but no chat interface available. Proceeding anyway...")
                # Re-run planner with instruction to proceed without clarification
                result = await Runner.run(
                    planner_agent,
                    f"Query: {query}\n\nNote: User is not available for clarification. Please proceed with your best interpretation and generate search queries.",
                )
                response = result.final_output_as(ResearchResponse)
            else:
                # Ask clarifying questions via chat callback
                print(f"Asking {len(response.questions)} clarifying questions...")
                answers = await chat_callback(response.questions)
                
                # Re-run planner with clarifications
                clarified_input = f"Original query: {query}\n\nClarifying questions and answers:\n{answers}"
                result = await Runner.run(
                    planner_agent,
                    clarified_input,
                )
                response = result.final_output_as(ResearchResponse)
        
        searches = response.searches
        print(f"Will perform {len(searches)} searches")
        return searches, None

    async def perform_searches(self, search_items: list[WebSearchItem]) -> list[str]:
        """ Perform the searches for the query """
        print("Searching...")
        num_completed = 0
        tasks = [asyncio.create_task(self.search(item)) for item in search_items]
        results = []
        for task in asyncio.as_completed(tasks):
            result = await task
            if result is not None:
                results.append(result)
            num_completed += 1
            print(f"Searching... {num_completed}/{len(tasks)} completed")
        print("Finished searching")
        return results

    async def search(self, item: WebSearchItem) -> str | None:
        """ Perform a search for the query """
        input = f"Search term: {item.query}\nReason for searching: {item.reason}"
        try:
            result = await Runner.run(
                search_agent,
                input,
            )
            return str(result.final_output)
        except Exception:
            return None

    async def write_report(self, query: str, search_results: list[str]) -> ReportData:
        """ Write the report for the query """
        print("Thinking about report...")
        input = f"Original query: {query}\nSummarized search results: {search_results}"
        result = await Runner.run(
            writer_agent,
            input,
        )

        print("Finished writing report")
        return result.final_output_as(ReportData)
    
    async def send_email(self, report: ReportData) -> None:
        print("Writing email...")
        result = await Runner.run(
            email_agent,
            report.markdown_report,
        )
        print("Email sent")
        return report