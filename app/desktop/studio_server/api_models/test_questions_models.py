import pytest
from app.desktop.studio_server.api_models.questions_models import (
    AnswerOption,
    AnswerOptionWithSelection,
    Question,
    QuestionSet,
    QuestionWithAnswer,
    SpecificationInput,
    SpecQuestionerInput,
    SubmitAnswersRequest,
)
from pydantic import ValidationError


# Fixtures for reusable test data
@pytest.fixture
def sample_answer_options():
    return [
        AnswerOption(answer_title="Option A", answer_description="Description A"),
        AnswerOption(answer_title="Option B", answer_description="Description B"),
        AnswerOption(answer_title="Option C", answer_description="Description C"),
    ]


@pytest.fixture
def sample_answer_options_with_selection():
    return [
        AnswerOptionWithSelection(
            answer_title="Option A", answer_description="Description A", selected=False
        ),
        AnswerOptionWithSelection(
            answer_title="Option B", answer_description="Description B", selected=True
        ),
        AnswerOptionWithSelection(
            answer_title="Option C", answer_description="Description C", selected=False
        ),
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
        input_model = SpecQuestionerInput(
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
        input_model = SpecQuestionerInput(
            task_prompt="Summarize the text",
            specification="The output should be concise.",
        )
        assert input_model.task_prompt == "Summarize the text"
        assert input_model.task_input_schema is None
        assert input_model.task_output_schema is None
        assert input_model.specification == "The output should be concise."

    def test_missing_required_field_task_prompt(self):
        with pytest.raises(ValidationError) as exc_info:
            SpecQuestionerInput(specification="Some spec")
        assert "task_prompt" in str(exc_info.value)

    def test_missing_required_field_specification(self):
        with pytest.raises(ValidationError) as exc_info:
            SpecQuestionerInput(task_prompt="Some prompt")
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


# Tests for AnswerOptionWithSelection
class TestAnswerOptionWithSelection:
    def test_valid_answer_option_selected(self):
        option = AnswerOptionWithSelection(
            answer_title="Yes",
            answer_description="Affirmative response",
            selected=True,
        )
        assert option.answer_title == "Yes"
        assert option.answer_description == "Affirmative response"
        assert option.selected is True

    def test_valid_answer_option_not_selected(self):
        option = AnswerOptionWithSelection(
            answer_title="No",
            answer_description="Negative response",
            selected=False,
        )
        assert option.answer_title == "No"
        assert option.answer_description == "Negative response"
        assert option.selected is False

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            AnswerOptionWithSelection(answer_title="Yes", answer_description="Desc")

        with pytest.raises(ValidationError):
            AnswerOptionWithSelection(answer_title="Yes", selected=True)

        with pytest.raises(ValidationError):
            AnswerOptionWithSelection(answer_description="Description", selected=True)

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            AnswerOptionWithSelection(
                answer_title="Yes",
                answer_description="Desc",
                selected=True,
                extra_field="not allowed",
            )


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


# Tests for QuestionWithAnswer
class TestQuestionWithAnswer:
    def test_valid_with_selected_option(self, sample_answer_options_with_selection):
        qa = QuestionWithAnswer(
            question_title="Test Question",
            question_body="What do you think?",
            answer_options=sample_answer_options_with_selection,
        )
        assert qa.question_title == "Test Question"
        assert qa.question_body == "What do you think?"
        assert len(qa.answer_options) == 3
        assert qa.answer_options[1].selected is True
        assert qa.custom_answer is None

    def test_valid_with_custom_answer(self):
        qa = QuestionWithAnswer(
            question_title="Test Question",
            question_body="What do you think?",
            answer_options=[
                AnswerOptionWithSelection(
                    answer_title="A", answer_description="Desc A", selected=False
                ),
                AnswerOptionWithSelection(
                    answer_title="B", answer_description="Desc B", selected=False
                ),
            ],
            custom_answer="My custom feedback here",
        )
        assert qa.custom_answer == "My custom feedback here"
        assert all(not opt.selected for opt in qa.answer_options)

    def test_invalid_multiple_selected_options(self):
        with pytest.raises(ValidationError) as exc_info:
            QuestionWithAnswer(
                question_title="Test",
                question_body="Body",
                answer_options=[
                    AnswerOptionWithSelection(
                        answer_title="A", answer_description="Desc A", selected=True
                    ),
                    AnswerOptionWithSelection(
                        answer_title="B", answer_description="Desc B", selected=True
                    ),
                ],
            )
        assert "Only one answer option can be selected" in str(exc_info.value)

    def test_invalid_both_selected_and_custom_answer(self):
        with pytest.raises(ValidationError) as exc_info:
            QuestionWithAnswer(
                question_title="Test",
                question_body="Body",
                answer_options=[
                    AnswerOptionWithSelection(
                        answer_title="A", answer_description="Desc A", selected=True
                    ),
                    AnswerOptionWithSelection(
                        answer_title="B", answer_description="Desc B", selected=False
                    ),
                ],
                custom_answer="Custom feedback",
            )
        assert "Cannot have both a selected option and custom_answer" in str(
            exc_info.value
        )

    def test_invalid_no_answer_provided(self):
        with pytest.raises(ValidationError) as exc_info:
            QuestionWithAnswer(
                question_title="Test",
                question_body="Body",
                answer_options=[
                    AnswerOptionWithSelection(
                        answer_title="A", answer_description="Desc A", selected=False
                    ),
                    AnswerOptionWithSelection(
                        answer_title="B", answer_description="Desc B", selected=False
                    ),
                ],
            )
        assert "Must either select an answer option or provide custom_answer" in str(
            exc_info.value
        )

    def test_invalid_empty_custom_answer(self):
        with pytest.raises(ValidationError) as exc_info:
            QuestionWithAnswer(
                question_title="Test",
                question_body="Body",
                answer_options=[
                    AnswerOptionWithSelection(
                        answer_title="A", answer_description="Desc A", selected=False
                    ),
                ],
                custom_answer="",
            )
        assert "custom_answer cannot be empty" in str(exc_info.value)

    def test_invalid_whitespace_only_custom_answer(self):
        with pytest.raises(ValidationError) as exc_info:
            QuestionWithAnswer(
                question_title="Test",
                question_body="Body",
                answer_options=[
                    AnswerOptionWithSelection(
                        answer_title="A", answer_description="Desc A", selected=False
                    ),
                ],
                custom_answer="   ",
            )
        assert "custom_answer cannot be empty" in str(exc_info.value)

    def test_valid_custom_answer_with_whitespace(self):
        qa = QuestionWithAnswer(
            question_title="Test",
            question_body="Body",
            answer_options=[
                AnswerOptionWithSelection(
                    answer_title="A", answer_description="Desc A", selected=False
                ),
            ],
            custom_answer="  Valid feedback with spaces  ",
        )
        assert qa.custom_answer == "  Valid feedback with spaces  "

    def test_empty_answer_options_with_custom_answer(self):
        qa = QuestionWithAnswer(
            question_title="Test",
            question_body="Body",
            answer_options=[],
            custom_answer="My custom answer",
        )
        assert len(qa.answer_options) == 0
        assert qa.custom_answer == "My custom answer"

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            QuestionWithAnswer(
                question_title="Test",
                question_body="Body",
                answer_options=[
                    AnswerOptionWithSelection(
                        answer_title="A", answer_description="Desc A", selected=True
                    ),
                ],
                extra_field="not allowed",
            )


# Tests for SubmitAnswersRequest
class TestSubmitAnswersRequest:
    def test_valid_request_single_question(self):
        request = SubmitAnswersRequest(
            task_prompt="Test task prompt",
            specification=SpecificationInput(
                spec_fields={"field1": "Description of field1"},
                spec_field_current_values={"field1": "Current value"},
            ),
            questions_and_answers=[
                QuestionWithAnswer(
                    question_title="Question 1",
                    question_body="First question body",
                    answer_options=[
                        AnswerOptionWithSelection(
                            answer_title="A",
                            answer_description="Desc A",
                            selected=True,
                        ),
                        AnswerOptionWithSelection(
                            answer_title="B",
                            answer_description="Desc B",
                            selected=False,
                        ),
                    ],
                ),
            ],
        )
        assert len(request.questions_and_answers) == 1
        assert request.questions_and_answers[0].answer_options[0].selected is True
        assert request.task_prompt == "Test task prompt"
        assert request.specification.spec_fields == {"field1": "Description of field1"}

    def test_valid_request_multiple_questions(self):
        request = SubmitAnswersRequest(
            task_prompt="Test task prompt",
            specification=SpecificationInput(
                spec_fields={"field1": "Description"},
                spec_field_current_values={"field1": "Value"},
            ),
            questions_and_answers=[
                QuestionWithAnswer(
                    question_title="Question 1",
                    question_body="First question body",
                    answer_options=[
                        AnswerOptionWithSelection(
                            answer_title="A",
                            answer_description="Desc A",
                            selected=False,
                        ),
                        AnswerOptionWithSelection(
                            answer_title="B",
                            answer_description="Desc B",
                            selected=True,
                        ),
                    ],
                ),
                QuestionWithAnswer(
                    question_title="Question 2",
                    question_body="Second question body",
                    answer_options=[
                        AnswerOptionWithSelection(
                            answer_title="X",
                            answer_description="Desc X",
                            selected=True,
                        ),
                        AnswerOptionWithSelection(
                            answer_title="Y",
                            answer_description="Desc Y",
                            selected=False,
                        ),
                    ],
                ),
            ],
        )
        assert len(request.questions_and_answers) == 2

    def test_valid_request_with_custom_answer(self):
        request = SubmitAnswersRequest(
            task_prompt="Test task prompt",
            specification=SpecificationInput(
                spec_fields={"field1": "Description"},
                spec_field_current_values={"field1": "Value"},
            ),
            questions_and_answers=[
                QuestionWithAnswer(
                    question_title="Question 1",
                    question_body="First question body",
                    answer_options=[
                        AnswerOptionWithSelection(
                            answer_title="A",
                            answer_description="Desc A",
                            selected=False,
                        ),
                    ],
                    custom_answer="My custom feedback",
                ),
            ],
        )
        assert request.questions_and_answers[0].custom_answer == "My custom feedback"

    def test_valid_request_mixed_answers(self):
        request = SubmitAnswersRequest(
            task_prompt="Test task prompt",
            specification=SpecificationInput(
                spec_fields={"field1": "Description"},
                spec_field_current_values={"field1": "Value"},
            ),
            questions_and_answers=[
                QuestionWithAnswer(
                    question_title="Question 1",
                    question_body="First question body",
                    answer_options=[
                        AnswerOptionWithSelection(
                            answer_title="A",
                            answer_description="Desc A",
                            selected=True,
                        ),
                    ],
                ),
                QuestionWithAnswer(
                    question_title="Question 2",
                    question_body="Second question body",
                    answer_options=[
                        AnswerOptionWithSelection(
                            answer_title="X",
                            answer_description="Desc X",
                            selected=False,
                        ),
                    ],
                    custom_answer="Custom answer for question 2",
                ),
            ],
        )
        assert request.questions_and_answers[0].custom_answer is None
        assert (
            request.questions_and_answers[1].custom_answer
            == "Custom answer for question 2"
        )

    def test_empty_questions_and_answers(self):
        request = SubmitAnswersRequest(
            task_prompt="Test task prompt",
            specification=SpecificationInput(
                spec_fields={"field1": "Description"},
                spec_field_current_values={"field1": "Value"},
            ),
            questions_and_answers=[],
        )
        assert len(request.questions_and_answers) == 0

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            SubmitAnswersRequest(
                task_prompt="Test task prompt",
                specification=SpecificationInput(
                    spec_fields={"field1": "Description"},
                    spec_field_current_values={"field1": "Value"},
                ),
                questions_and_answers=[
                    QuestionWithAnswer(
                        question_title="Q",
                        question_body="B",
                        answer_options=[
                            AnswerOptionWithSelection(
                                answer_title="A",
                                answer_description="Desc",
                                selected=True,
                            ),
                        ],
                    ),
                ],
                extra_field="not allowed",
            )

    def test_invalid_question_propagates_error(self):
        with pytest.raises(ValidationError) as exc_info:
            SubmitAnswersRequest(
                task_prompt="Test task prompt",
                specification=SpecificationInput(
                    spec_fields={"field1": "Description"},
                    spec_field_current_values={"field1": "Value"},
                ),
                questions_and_answers=[
                    QuestionWithAnswer(
                        question_title="Q",
                        question_body="B",
                        answer_options=[
                            AnswerOptionWithSelection(
                                answer_title="A",
                                answer_description="Desc",
                                selected=False,
                            ),
                        ],
                        # No answer provided - should fail validation
                    ),
                ],
            )
        assert "Must either select an answer option or provide custom_answer" in str(
            exc_info.value
        )


# Tests for SpecificationInput
class TestSpecificationInput:
    def test_valid_specification_input(self):
        spec = SpecificationInput(
            spec_fields={"field1": "Description of field1", "field2": "Description 2"},
            spec_field_current_values={"field1": "Value 1", "field2": "Value 2"},
        )
        assert spec.spec_fields == {
            "field1": "Description of field1",
            "field2": "Description 2",
        }
        assert spec.spec_field_current_values == {
            "field1": "Value 1",
            "field2": "Value 2",
        }

    def test_empty_dictionaries(self):
        spec = SpecificationInput(
            spec_fields={},
            spec_field_current_values={},
        )
        assert spec.spec_fields == {}
        assert spec.spec_field_current_values == {}

    def test_missing_spec_fields(self):
        with pytest.raises(ValidationError):
            SpecificationInput(
                spec_field_current_values={"field1": "Value"},
            )

    def test_missing_spec_field_current_values(self):
        with pytest.raises(ValidationError):
            SpecificationInput(
                spec_fields={"field1": "Description"},
            )

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            SpecificationInput(
                spec_fields={"field1": "Description"},
                spec_field_current_values={"field1": "Value"},
                extra_field="not allowed",
            )
