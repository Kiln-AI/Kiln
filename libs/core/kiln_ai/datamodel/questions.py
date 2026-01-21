from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SpecQuestionerInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    task_prompt: str = Field(..., description="The task's prompt", title="task_prompt")
    task_input_schema: str | None = Field(
        None,
        description="If the task's input must conform to a specific input schema, it will be provided here",
        title="task_input_schema",
    )
    task_output_schema: str | None = Field(
        None,
        description="If the task's output must conform to a specific schema, it will be provided here",
        title="task_output_schema",
    )
    specification: str = Field(
        ..., description="The specification to analyze", title="specification"
    )


class AnswerOption(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    answer_title: str = Field(
        ...,
        description="A short title describing this answer option",
        title="answer_title",
    )
    answer_description: str = Field(
        ..., description="A description of this answer", title="answer_description"
    )


class Question(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    question_title: str = Field(
        ..., description="A short title for this question", title="question_title"
    )
    question_body: str = Field(
        ..., description="The full question text", title="question_body"
    )
    answer_options: list[AnswerOption] = Field(
        ...,
        description="A list of possible answers to this question for the user to select from",
        title="answer_options",
    )


class QuestionSet(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    questions: list[Question] = Field(
        ...,
        description="A set of questions to ask about the specification",
        title="questions",
    )


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
