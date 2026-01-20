import pytest
from pydantic import ValidationError

from kiln_server.question_api import (
    AnswerOption,
    Question,
    QuestionAnswer,
    QuestionSet,
    SpecificationAnalysisInput,
    SubmitAnswersRequest,
)


# Fixtures for reusable test data
@pytest.fixture
def sample_answer_options():
    return [
        AnswerOption(answer_title="Option A", answer_description="Description A"),
        AnswerOption(answer_title="Option B", answer_description="Description B"),
        AnswerOption(answer_title="Option C", answer_description="Description C"),
    ]


@pytest.fixture
def sample_question(sample_answer_options):
    return Question(
        question_title="Sample Question",
        question_body="What is your choice?",
        answer_options=sample_answer_options,
    )


@pytest.fixture
def sample_questions(sample_answer_options):
    return [
        Question(
            question_title="Question 1",
            question_body="First question body",
            answer_options=sample_answer_options,
        ),
        Question(
            question_title="Question 2",
            question_body="Second question body",
            answer_options=sample_answer_options[:2],  # Only 2 options
        ),
    ]


# Tests for SpecificationAnalysisInput
class TestSpecificationAnalysisInput:
    def test_with_all_fields(self):
        input_model = SpecificationAnalysisInput(
            task_prompt="Summarize the text",
            task_input_schema='{"type": "string"}',
            task_output_schema='{"type": "string"}',
            specification="The output should be concise.",
        )
        assert input_model.task_prompt == "Summarize the text"
        assert input_model.task_input_schema == '{"type": "string"}'
        assert input_model.task_output_schema == '{"type": "string"}'
        assert input_model.specification == "The output should be concise."

    def test_with_required_fields_only(self):
        input_model = SpecificationAnalysisInput(
            task_prompt="Summarize the text",
            specification="The output should be concise.",
        )
        assert input_model.task_prompt == "Summarize the text"
        assert input_model.task_input_schema is None
        assert input_model.task_output_schema is None
        assert input_model.specification == "The output should be concise."

    def test_missing_required_field_task_prompt(self):
        with pytest.raises(ValidationError) as exc_info:
            SpecificationAnalysisInput(specification="Some spec")
        assert "task_prompt" in str(exc_info.value)

    def test_missing_required_field_specification(self):
        with pytest.raises(ValidationError) as exc_info:
            SpecificationAnalysisInput(task_prompt="Some prompt")
        assert "specification" in str(exc_info.value)


# Tests for AnswerOption
class TestAnswerOption:
    def test_valid_answer_option(self):
        option = AnswerOption(
            answer_title="Yes",
            answer_description="Affirmative response",
        )
        assert option.answer_title == "Yes"
        assert option.answer_description == "Affirmative response"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            AnswerOption(answer_title="Yes")

        with pytest.raises(ValidationError):
            AnswerOption(answer_description="Description")


# Tests for Question
class TestQuestion:
    def test_valid_question(self, sample_answer_options):
        question = Question(
            question_title="Test Title",
            question_body="Test Body",
            answer_options=sample_answer_options,
        )
        assert question.question_title == "Test Title"
        assert question.question_body == "Test Body"
        assert len(question.answer_options) == 3

    def test_empty_answer_options(self):
        question = Question(
            question_title="Test",
            question_body="Body",
            answer_options=[],
        )
        assert len(question.answer_options) == 0


# Tests for QuestionSet
class TestQuestionSet:
    def test_valid_question_set(self, sample_questions):
        question_set = QuestionSet(questions=sample_questions)
        assert len(question_set.questions) == 2

    def test_empty_question_set(self):
        question_set = QuestionSet(questions=[])
        assert len(question_set.questions) == 0


# Tests for QuestionAnswer
class TestQuestionAnswer:
    def test_valid_with_selected_option(self):
        answer = QuestionAnswer(
            question_index=0,
            selected_option_index=1,
        )
        assert answer.question_index == 0
        assert answer.selected_option_index == 1
        assert answer.other_feedback is None

    def test_valid_with_other_feedback(self):
        answer = QuestionAnswer(
            question_index=0,
            other_feedback="Custom feedback here",
        )
        assert answer.question_index == 0
        assert answer.selected_option_index is None
        assert answer.other_feedback == "Custom feedback here"

    def test_invalid_both_selected_and_feedback(self):
        with pytest.raises(ValidationError) as exc_info:
            QuestionAnswer(
                question_index=0,
                selected_option_index=1,
                other_feedback="Some feedback",
            )
        assert "Cannot provide both selected_option_index and other_feedback" in str(
            exc_info.value
        )

    def test_invalid_neither_selected_nor_feedback(self):
        with pytest.raises(ValidationError) as exc_info:
            QuestionAnswer(question_index=0)
        assert "Must provide either selected_option_index or other_feedback" in str(
            exc_info.value
        )

    def test_invalid_empty_feedback(self):
        with pytest.raises(ValidationError) as exc_info:
            QuestionAnswer(
                question_index=0,
                other_feedback="",
            )
        assert "other_feedback cannot be empty" in str(exc_info.value)

    def test_invalid_whitespace_only_feedback(self):
        with pytest.raises(ValidationError) as exc_info:
            QuestionAnswer(
                question_index=0,
                other_feedback="   ",
            )
        assert "other_feedback cannot be empty" in str(exc_info.value)

    def test_valid_feedback_with_whitespace(self):
        answer = QuestionAnswer(
            question_index=0,
            other_feedback="  Valid feedback with spaces  ",
        )
        assert answer.other_feedback == "  Valid feedback with spaces  "


# Tests for SubmitAnswersRequest
class TestSubmitAnswersRequest:
    def test_valid_request_all_selected_options(self, sample_questions):
        request = SubmitAnswersRequest(
            questions=sample_questions,
            answers=[
                QuestionAnswer(question_index=0, selected_option_index=0),
                QuestionAnswer(question_index=1, selected_option_index=1),
            ],
        )
        assert len(request.answers) == 2

    def test_valid_request_with_feedback(self, sample_questions):
        request = SubmitAnswersRequest(
            questions=sample_questions,
            answers=[
                QuestionAnswer(question_index=0, other_feedback="Custom answer"),
                QuestionAnswer(question_index=1, selected_option_index=0),
            ],
        )
        assert request.answers[0].other_feedback == "Custom answer"
        assert request.answers[1].selected_option_index == 0

    def test_invalid_question_index_negative(self, sample_questions):
        with pytest.raises(ValidationError) as exc_info:
            SubmitAnswersRequest(
                questions=sample_questions,
                answers=[
                    QuestionAnswer(question_index=-1, selected_option_index=0),
                    QuestionAnswer(question_index=1, selected_option_index=0),
                ],
            )
        assert "question_index -1 is out of range" in str(exc_info.value)

    def test_invalid_question_index_too_high(self, sample_questions):
        with pytest.raises(ValidationError) as exc_info:
            SubmitAnswersRequest(
                questions=sample_questions,
                answers=[
                    QuestionAnswer(question_index=0, selected_option_index=0),
                    QuestionAnswer(question_index=5, selected_option_index=0),
                ],
            )
        assert "question_index 5 is out of range" in str(exc_info.value)

    def test_invalid_duplicate_answers(self, sample_questions):
        with pytest.raises(ValidationError) as exc_info:
            SubmitAnswersRequest(
                questions=sample_questions,
                answers=[
                    QuestionAnswer(question_index=0, selected_option_index=0),
                    QuestionAnswer(question_index=0, selected_option_index=1),
                ],
            )
        assert "Duplicate answer for question_index 0" in str(exc_info.value)

    def test_invalid_selected_option_index_negative(self, sample_questions):
        with pytest.raises(ValidationError) as exc_info:
            SubmitAnswersRequest(
                questions=sample_questions,
                answers=[
                    QuestionAnswer(question_index=0, selected_option_index=-1),
                    QuestionAnswer(question_index=1, selected_option_index=0),
                ],
            )
        assert "selected_option_index -1 is out of range" in str(exc_info.value)

    def test_invalid_selected_option_index_too_high(self, sample_questions):
        with pytest.raises(ValidationError) as exc_info:
            SubmitAnswersRequest(
                questions=sample_questions,
                answers=[
                    QuestionAnswer(question_index=0, selected_option_index=0),
                    QuestionAnswer(
                        question_index=1, selected_option_index=5
                    ),  # Question 1 has only 2 options
                ],
            )
        assert "selected_option_index 5 is out of range for question 1" in str(
            exc_info.value
        )

    def test_invalid_wrong_answer_count_too_few(self, sample_questions):
        with pytest.raises(ValidationError) as exc_info:
            SubmitAnswersRequest(
                questions=sample_questions,
                answers=[
                    QuestionAnswer(question_index=0, selected_option_index=0),
                    # Missing answer for question 1
                ],
            )
        assert "Expected 2 answers, got 1" in str(exc_info.value)

    def test_invalid_wrong_answer_count_too_many(self, sample_questions):
        with pytest.raises(ValidationError) as exc_info:
            SubmitAnswersRequest(
                questions=sample_questions,
                answers=[
                    QuestionAnswer(question_index=0, selected_option_index=0),
                    QuestionAnswer(question_index=1, selected_option_index=0),
                    QuestionAnswer(
                        question_index=0, other_feedback="Extra"
                    ),  # Extra answer
                ],
            )
        # This will fail on duplicate before count check
        assert "Duplicate answer for question_index 0" in str(exc_info.value)

    def test_empty_questions_and_answers(self):
        request = SubmitAnswersRequest(
            questions=[],
            answers=[],
        )
        assert len(request.questions) == 0
        assert len(request.answers) == 0

    def test_single_question_single_answer(self, sample_answer_options):
        questions = [
            Question(
                question_title="Only Question",
                question_body="Body",
                answer_options=sample_answer_options,
            )
        ]
        request = SubmitAnswersRequest(
            questions=questions,
            answers=[QuestionAnswer(question_index=0, selected_option_index=2)],
        )
        assert len(request.answers) == 1
        assert request.answers[0].selected_option_index == 2

    def test_boundary_option_indices(self, sample_answer_options):
        questions = [
            Question(
                question_title="Q",
                question_body="B",
                answer_options=sample_answer_options,  # 3 options: indices 0, 1, 2
            )
        ]
        # Test first valid index
        request = SubmitAnswersRequest(
            questions=questions,
            answers=[QuestionAnswer(question_index=0, selected_option_index=0)],
        )
        assert request.answers[0].selected_option_index == 0

        # Test last valid index
        request = SubmitAnswersRequest(
            questions=questions,
            answers=[QuestionAnswer(question_index=0, selected_option_index=2)],
        )
        assert request.answers[0].selected_option_index == 2

        # Test just past last valid index
        with pytest.raises(ValidationError) as exc_info:
            SubmitAnswersRequest(
                questions=questions,
                answers=[QuestionAnswer(question_index=0, selected_option_index=3)],
            )
        assert "selected_option_index 3 is out of range for question 0 (0-2)" in str(
            exc_info.value
        )
