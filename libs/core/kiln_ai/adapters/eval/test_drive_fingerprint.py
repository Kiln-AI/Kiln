import pytest

from kiln_ai.adapters.eval.drive_fingerprint import compute_drive_fingerprint
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.eval import (
    MultiTurnDriveConfig,
    MultiTurnSyntheticEvalInputData,
    SyntheticUserInfo,
    UserMessage,
)
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    ToolsRunConfig,
)


def make_drive_config(**overrides) -> MultiTurnDriveConfig:
    defaults = dict(
        model_name="claude_4_5_haiku",
        model_provider="openrouter",
        turns=3,
    )
    defaults.update(overrides)
    return MultiTurnDriveConfig(**defaults)


def make_run_config_properties(**overrides) -> KilnAgentRunConfigProperties:
    defaults = dict(
        model_name="gpt-4",
        model_provider_name=ModelProviderName.openai,
        prompt_id="simple_prompt_builder",
        structured_output_mode=StructuredOutputMode.json_schema,
    )
    defaults.update(overrides)
    return KilnAgentRunConfigProperties(**defaults)


def make_data(**overrides) -> MultiTurnSyntheticEvalInputData:
    defaults = dict(
        first_message=UserMessage(text="opening message"),
        synthetic_user_info=SyntheticUserInfo(
            persona="frustrated customer",
            goal="get a refund",
            behavior_guidance="be polite then escalate",
        ),
    )
    defaults.update(overrides)
    return MultiTurnSyntheticEvalInputData(**defaults)


def baseline_fingerprint() -> str:
    return compute_drive_fingerprint(
        make_drive_config(), make_run_config_properties(), make_data()
    )


class TestDeterminism:
    def test_same_inputs_same_fingerprint(self):
        # Fresh model instances each call: the hash must depend on content
        # only, never on object identity or construction order.
        assert baseline_fingerprint() == baseline_fingerprint()

    def test_version_prefix_and_shape(self):
        fingerprint = baseline_fingerprint()
        prefix, _, digest = fingerprint.partition(":")
        assert prefix == "v1"
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)


class TestSensitivity:
    """Every input that shapes the conversation must change the fingerprint."""

    @pytest.mark.parametrize(
        "override",
        [
            {"model_name": "other-su-model"},
            {"model_provider": "other-provider"},
            {"turns": 4},
        ],
    )
    def test_drive_config_changes(self, override):
        changed = compute_drive_fingerprint(
            make_drive_config(**override), make_run_config_properties(), make_data()
        )
        assert changed != baseline_fingerprint()

    @pytest.mark.parametrize(
        "override",
        [
            {"model_name": "gpt-5"},
            {"prompt_id": "few_shot_prompt_builder"},
            {"temperature": 0.2},
            {"top_p": 0.9},
            {"structured_output_mode": StructuredOutputMode.json_mode},
            {"tools_config": ToolsRunConfig(tools=["kiln_task::some_task_tool"])},
        ],
    )
    def test_run_config_property_changes(self, override):
        changed = compute_drive_fingerprint(
            make_drive_config(), make_run_config_properties(**override), make_data()
        )
        assert changed != baseline_fingerprint()

    def test_first_message_change(self):
        changed = compute_drive_fingerprint(
            make_drive_config(),
            make_run_config_properties(),
            make_data(first_message=UserMessage(text="different opener")),
        )
        assert changed != baseline_fingerprint()

    def test_missing_first_message_differs_from_present(self):
        changed = compute_drive_fingerprint(
            make_drive_config(),
            make_run_config_properties(),
            make_data(first_message=None),
        )
        assert changed != baseline_fingerprint()

    @pytest.mark.parametrize(
        "su_info",
        [
            SyntheticUserInfo(
                persona="calm customer",
                goal="get a refund",
                behavior_guidance="be polite then escalate",
            ),
            SyntheticUserInfo(
                persona="frustrated customer",
                goal="cancel the account",
                behavior_guidance="be polite then escalate",
            ),
            SyntheticUserInfo(
                persona="frustrated customer",
                goal="get a refund",
                behavior_guidance=None,
            ),
        ],
    )
    def test_synthetic_user_info_changes(self, su_info):
        changed = compute_drive_fingerprint(
            make_drive_config(),
            make_run_config_properties(),
            make_data(synthetic_user_info=su_info),
        )
        assert changed != baseline_fingerprint()

    def test_synthetic_user_info_extra_fields_change_fingerprint(self):
        # SyntheticUserInfo is extra="allow": unknown generator fields shape
        # the SU prompt at drive time, so they must shape the identity too.
        su_info = SyntheticUserInfo.model_validate(
            {
                "persona": "frustrated customer",
                "goal": "get a refund",
                "behavior_guidance": "be polite then escalate",
                "mood": "impatient",
            }
        )
        changed = compute_drive_fingerprint(
            make_drive_config(),
            make_run_config_properties(),
            make_data(synthetic_user_info=su_info),
        )
        assert changed != baseline_fingerprint()


class TestInsensitivity:
    def test_identical_content_matches_across_separate_authors(self):
        # Two evals minting their own copies of the same scenario (the
        # builder's convention) must converge on one fingerprint: the key is
        # content, never input identity or the eval that owns it. Reference
        # data isn't an input at all — it shapes judgment, not the drive.
        assert compute_drive_fingerprint(
            make_drive_config(), make_run_config_properties(), make_data()
        ) == compute_drive_fingerprint(
            make_drive_config(), make_run_config_properties(), make_data()
        )
