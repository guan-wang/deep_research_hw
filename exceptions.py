"""
Custom exceptions for the deep research system
"""


class ClarificationNeeded(Exception):
    """
    Raised when the research manager needs user clarification.
    
    This exception stops agent execution and should NOT be caught/handled by the agent itself.
    The exception message is intentionally minimal to prevent the agent from trying to answer
    the questions itself.
    """
    
    def __init__(self, questions: list[str]):
        # Use a minimal message that doesn't include the questions
        # This prevents the agent from seeing the questions and trying to answer them
        super().__init__("USER_CLARIFICATION_REQUIRED")
        self.questions = questions

