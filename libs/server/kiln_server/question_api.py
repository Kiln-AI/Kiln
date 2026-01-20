from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, model_validator


# Input schema for specification analysis
class SpecificationAnalysisInput(BaseModel):
    task_prompt: str
    task_input_schema: Optional[str] = None
    task_output_schema: Optional[str] = None
    specification: str


# Output schema for specification questions
class AnswerOption(BaseModel):
    answer_title: str
    answer_description: str


class Question(BaseModel):
    question_title: str
    question_body: str
    answer_options: List[AnswerOption]


class QuestionSet(BaseModel):
    questions: List[Question]


# Answer submission models
class QuestionAnswer(BaseModel):
    """
    An answer to a single question. Must provide exactly one of:
    - selected_option_index: index of the chosen AnswerOption (0-indexed)
    - other_feedback: plaintext feedback when none of the predefined options fit
    """

    question_index: int  # 0-indexed position in the QuestionSet
    selected_option_index: Optional[int] = None
    other_feedback: Optional[str] = None

    @model_validator(mode="after")
    def validate_answer_type(self) -> "QuestionAnswer":
        has_selection = self.selected_option_index is not None
        has_feedback = self.other_feedback is not None

        if has_selection and has_feedback:
            raise ValueError(
                "Cannot provide both selected_option_index and other_feedback - choose one"
            )
        if not has_selection and not has_feedback:
            raise ValueError(
                "Must provide either selected_option_index or other_feedback"
            )
        if self.other_feedback is not None and not self.other_feedback.strip():
            raise ValueError("other_feedback cannot be empty")
        return self


class SubmitAnswersRequest(BaseModel):
    """Request to submit answers to a question set."""

    questions: List[Question]
    answers: List[QuestionAnswer]

    @model_validator(mode="after")
    def validate_answers(self) -> "SubmitAnswersRequest":
        num_questions = len(self.questions)
        answered_indices = set()

        for answer in self.answers:
            # Validate question_index is in range
            if answer.question_index < 0 or answer.question_index >= num_questions:
                raise ValueError(
                    f"question_index {answer.question_index} is out of range (0-{num_questions - 1})"
                )

            # Check for duplicate answers to same question
            if answer.question_index in answered_indices:
                raise ValueError(
                    f"Duplicate answer for question_index {answer.question_index}"
                )
            answered_indices.add(answer.question_index)

            # Validate selected_option_index is in range for the question
            if answer.selected_option_index is not None:
                question = self.questions[answer.question_index]
                num_options = len(question.answer_options)
                if (
                    answer.selected_option_index < 0
                    or answer.selected_option_index >= num_options
                ):
                    raise ValueError(
                        f"selected_option_index {answer.selected_option_index} is out of range "
                        f"for question {answer.question_index} (0-{num_options - 1})"
                    )

        # Ensure all questions are answered
        if len(self.answers) != num_questions:
            raise ValueError(
                f"Expected {num_questions} answers, got {len(self.answers)}"
            )

        return self


# TODO P0 - this should be removed.
def connect_question_api(app: FastAPI):
    @app.get("/api/demo_question_set")
    async def get_demo_question_set() -> QuestionSet:
        demo_questions = [
            Question(
                question_title="Output Format",
                question_body="What format should the output be in when the task is completed?",
                answer_options=[
                    AnswerOption(
                        answer_title="Plain Text",
                        answer_description="Return the output as unformatted plain text",
                    ),
                    AnswerOption(
                        answer_title="Markdown",
                        answer_description="Return the output formatted with Markdown syntax",
                    ),
                    AnswerOption(
                        answer_title="JSON",
                        answer_description="Return the output as structured JSON data",
                    ),
                ],
            ),
            Question(
                question_title="Error Handling",
                question_body="How should the system handle invalid or malformed input?",
                answer_options=[
                    AnswerOption(
                        answer_title="Strict Validation",
                        answer_description="Reject invalid input with a detailed error message",
                    ),
                    AnswerOption(
                        answer_title="Best Effort",
                        answer_description="Attempt to process the input and return partial results if possible",
                    ),
                    AnswerOption(
                        answer_title="Silent Fallback",
                        answer_description="Use default values when input is invalid without explicit notification",
                    ),
                ],
            ),
            Question(
                question_title="Response Length",
                question_body="What level of detail should be included in the response?",
                answer_options=[
                    AnswerOption(
                        answer_title="Concise",
                        answer_description="Provide brief, to-the-point responses",
                    ),
                    AnswerOption(
                        answer_title="Detailed",
                        answer_description="Include comprehensive explanations and context",
                    ),
                    AnswerOption(
                        answer_title="Adaptive",
                        answer_description="Adjust response length based on the complexity of the input",
                    ),
                ],
            ),
        ]
        return QuestionSet(questions=demo_questions)

    # TODO P0 - this should be implemented.
    @app.post("/api/submit_spec_question_answers")
    async def submit_question_answers(
        request: SubmitAnswersRequest,
    ):
        # Validation is handled by Pydantic model validators
        # Here you would process the answers (e.g., update spec, store responses, etc.)

        # TODO: implement answer processing logic
        return
