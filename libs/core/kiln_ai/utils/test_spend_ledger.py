import json
import time

import pytest

from kiln_ai.utils import spend_ledger

CONVERSATION_ID = "1f2e3d4c-5b6a-4789-8abc-def012345678"
OTHER_CONVERSATION_ID = "9e8d7c6b-5a49-4321-9fed-cba987654321"


@pytest.fixture(autouse=True)
def tmp_settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        spend_ledger.Config,
        "settings_dir",
        classmethod(lambda cls, create=True: str(tmp_path)),
    )
    return tmp_path


@pytest.fixture(autouse=True)
def clear_contextvar():
    token = spend_ledger.current_conversation_id.set(None)
    yield
    spend_ledger.current_conversation_id.reset(token)


class TestValidation:
    def test_valid_uuid4(self):
        assert spend_ledger.is_valid_conversation_id(CONVERSATION_ID)

    @pytest.mark.parametrize(
        "bad_id",
        ["", "not-a-uuid", CONVERSATION_ID.upper(), CONVERSATION_ID + "\n"],
    )
    def test_invalid_ids(self, bad_id):
        assert not spend_ledger.is_valid_conversation_id(bad_id)

    def test_set_budget_rejects_invalid_id(self):
        with pytest.raises(ValueError, match="conversation id"):
            spend_ledger.set_budget("junk", 5.0)

    @pytest.mark.parametrize("bad_budget", [-1.0, float("nan")])
    def test_set_budget_rejects_bad_amounts(self, bad_budget):
        with pytest.raises(ValueError, match="non-negative"):
            spend_ledger.set_budget(CONVERSATION_ID, bad_budget)


class TestBudgetLifecycle:
    def test_status_none_when_never_seen(self):
        assert spend_ledger.get_status(CONVERSATION_ID) is None

    def test_set_and_get_budget(self):
        status = spend_ledger.set_budget(CONVERSATION_ID, 5.0)
        assert status.budget_usd == 5.0
        assert status.spent_usd == 0.0
        assert status.remaining_usd == 5.0
        assert not status.exhausted

        loaded = spend_ledger.get_status(CONVERSATION_ID)
        assert loaded is not None
        assert loaded.budget_usd == 5.0

    def test_extend_budget_preserves_spend(self):
        spend_ledger.set_budget(CONVERSATION_ID, 1.0)
        spend_ledger.record_spend(CONVERSATION_ID, 0.75, 1000)
        spend_ledger.set_budget(CONVERSATION_ID, 2.0)
        status = spend_ledger.get_status(CONVERSATION_ID)
        assert status is not None
        assert status.budget_usd == 2.0
        assert status.spent_usd == 0.75
        assert status.remaining_usd == 1.25

    def test_clear_budget_with_none(self):
        spend_ledger.set_budget(CONVERSATION_ID, 1.0)
        spend_ledger.set_budget(CONVERSATION_ID, None)
        status = spend_ledger.get_status(CONVERSATION_ID)
        assert status is not None
        assert status.budget_usd is None
        assert not spend_ledger.is_exhausted(CONVERSATION_ID)


class TestRecordSpend:
    def test_record_before_budget_set_is_tracked(self):
        spend_ledger.record_spend(CONVERSATION_ID, 0.10, 500)
        status = spend_ledger.get_status(CONVERSATION_ID)
        assert status is not None
        assert status.spent_usd == pytest.approx(0.10)
        assert status.budget_usd is None

    def test_spend_accumulates(self):
        spend_ledger.record_spend(CONVERSATION_ID, 0.10, 100)
        spend_ledger.record_spend(CONVERSATION_ID, 0.25, 100)
        status = spend_ledger.get_status(CONVERSATION_ID)
        assert status is not None
        assert status.spent_usd == pytest.approx(0.35)

    def test_unpriced_runs_counted_not_debited(self):
        spend_ledger.set_budget(CONVERSATION_ID, 1.0)
        spend_ledger.record_spend(CONVERSATION_ID, None, 12345)
        status = spend_ledger.get_status(CONVERSATION_ID)
        assert status is not None
        assert status.spent_usd == 0.0
        assert status.unpriced_runs == 1
        assert status.unpriced_tokens == 12345
        assert not status.exhausted

    def test_spend_isolated_per_conversation(self):
        spend_ledger.record_spend(CONVERSATION_ID, 0.10, 100)
        spend_ledger.record_spend(OTHER_CONVERSATION_ID, 0.99, 100)
        status = spend_ledger.get_status(CONVERSATION_ID)
        assert status is not None
        assert status.spent_usd == pytest.approx(0.10)

    def test_record_invalid_id_is_noop(self):
        spend_ledger.record_spend("junk", 0.10, 100)
        assert spend_ledger.get_status(CONVERSATION_ID) is None


class TestExhaustion:
    def test_exhausted_when_spend_reaches_budget(self):
        spend_ledger.set_budget(CONVERSATION_ID, 0.5)
        assert not spend_ledger.is_exhausted(CONVERSATION_ID)
        spend_ledger.record_spend(CONVERSATION_ID, 0.5, 100)
        assert spend_ledger.is_exhausted(CONVERSATION_ID)
        status = spend_ledger.get_status(CONVERSATION_ID)
        assert status is not None
        assert status.remaining_usd == 0.0

    def test_no_budget_never_exhausted(self):
        spend_ledger.record_spend(CONVERSATION_ID, 100.0, 100)
        assert not spend_ledger.is_exhausted(CONVERSATION_ID)

    def test_none_conversation_never_exhausted(self):
        assert not spend_ledger.is_exhausted(None)

    def test_zero_budget_immediately_exhausted(self):
        spend_ledger.set_budget(CONVERSATION_ID, 0.0)
        assert spend_ledger.is_exhausted(CONVERSATION_ID)


class TestPersistence:
    def test_ledger_survives_reload(self, tmp_settings_dir):
        spend_ledger.set_budget(CONVERSATION_ID, 3.0)
        spend_ledger.record_spend(CONVERSATION_ID, 1.0, 100)
        # Read straight from disk to prove persistence, not caching.
        with open(tmp_settings_dir / "conversation_budgets.json") as f:
            raw = json.load(f)
        assert raw[CONVERSATION_ID]["budget_usd"] == 3.0
        assert raw[CONVERSATION_ID]["spent_usd"] == 1.0

    def test_corrupt_ledger_degrades_gracefully(self, tmp_settings_dir):
        (tmp_settings_dir / "conversation_budgets.json").write_text("{not json")
        assert spend_ledger.get_status(CONVERSATION_ID) is None
        # Writes still work (corrupt state is discarded).
        spend_ledger.set_budget(CONVERSATION_ID, 1.0)
        status = spend_ledger.get_status(CONVERSATION_ID)
        assert status is not None

    def test_old_entries_pruned_on_write(self, tmp_settings_dir):
        stale = {
            OTHER_CONVERSATION_ID: {
                "budget_usd": 1.0,
                "spent_usd": 0.0,
                "updated_at": time.time() - spend_ledger._PRUNE_AFTER_SECONDS - 1,
            }
        }
        (tmp_settings_dir / "conversation_budgets.json").write_text(json.dumps(stale))
        spend_ledger.set_budget(CONVERSATION_ID, 1.0)
        with open(tmp_settings_dir / "conversation_budgets.json") as f:
            raw = json.load(f)
        assert OTHER_CONVERSATION_ID not in raw
        assert CONVERSATION_ID in raw


class TestContextvarCredit:
    def test_records_when_contextvar_set(self):
        token = spend_ledger.current_conversation_id.set(CONVERSATION_ID)
        try:
            spend_ledger.record_spend_for_current_conversation(0.2, 100)
        finally:
            spend_ledger.current_conversation_id.reset(token)
        status = spend_ledger.get_status(CONVERSATION_ID)
        assert status is not None
        assert status.spent_usd == pytest.approx(0.2)

    def test_noop_when_contextvar_unset(self):
        spend_ledger.record_spend_for_current_conversation(0.2, 100)
        assert spend_ledger.get_status(CONVERSATION_ID) is None

    def test_never_raises_on_ledger_errors(self, monkeypatch):
        token = spend_ledger.current_conversation_id.set(CONVERSATION_ID)
        monkeypatch.setattr(
            spend_ledger, "record_spend", lambda *a, **k: (_ for _ in ()).throw(OSError)
        )
        try:
            spend_ledger.record_spend_for_current_conversation(0.2, 100)
        finally:
            spend_ledger.current_conversation_id.reset(token)
