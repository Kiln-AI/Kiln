from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from kiln_ai.adapters import remote_config
from kiln_ai.adapters.ml_model_list import built_in_models
from kiln_ai.adapters.ml_provider_list import built_in_providers
from pydantic import BaseModel

from app.desktop.studio_server.services.model_info.catalog_build import (
    KilnModelList,
)
from app.desktop.studio_server.services.model_info.models_dev import (
    ModelsDevSnapshot,
)
from app.desktop.studio_server.services.model_info.service import (
    ModelInfoService,
    read_kiln_model_list,
)
from app.desktop.studio_server.services.model_info.test_catalog_build import (
    kiln_list,
    models_dev,
    models_dev_file,
)
from app.desktop.studio_server.services.model_info.view import ListModelsQuery

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)


class Offered(BaseModel):
    provider_id: str
    provider_name: str
    models: list[dict]


async def offered_by_openrouter() -> list[BaseModel]:
    return [
        Offered(
            provider_id="openrouter",
            provider_name="OpenRouter",
            models=[{"id": "gpt_6_1_sol", "name": "GPT"}],
        )
    ]


class FakeSource:
    def __init__(self, snapshot: ModelsDevSnapshot) -> None:
        self.snapshot = snapshot

    async def current(self) -> ModelsDevSnapshot:
        return self.snapshot


def snapshot_with_data(loaded_at: datetime | None = NOW) -> ModelsDevSnapshot:
    return ModelsDevSnapshot(
        data=models_dev(models_dev_file()), state="ok", loaded_at=loaded_at, detail=None
    )


class Lists:
    """A Kiln model list source a test can swap."""

    def __init__(self, current: KilnModelList) -> None:
        self.current = current

    def __call__(self) -> KilnModelList:
        return self.current


def make_service(source: FakeSource, lists: Lists) -> ModelInfoService:
    return ModelInfoService(
        available_models=offered_by_openrouter,
        models_dev=source,
        kiln_model_list=lists,
        now=lambda: NOW,
    )


def test_the_catalogue_is_rebuilt_only_when_a_source_changes():
    service = make_service(FakeSource(snapshot_with_data()), Lists(kiln_list()))
    kiln = kiln_list()
    data = models_dev(models_dev_file())
    first = service._catalog(kiln, data)
    assert service._catalog(kiln, data) is first
    # The same model objects in a new tuple: the same catalogue.
    same_models = KilnModelList(tuple(kiln.models), kiln.providers, loaded_at=NOW)
    assert service._catalog(same_models, data) is first
    # New models.dev data, an equal but new Kiln list, one model fewer.
    new_data = models_dev(models_dev_file())
    second = service._catalog(kiln, new_data)
    assert second is not first and second == first
    third = service._catalog(kiln_list(), new_data)
    assert third is not second
    shorter = KilnModelList(kiln.models[:-1], kiln.providers, loaded_at=None)
    assert len(service._catalog(shorter, new_data).models) == 6
    assert service._catalog(shorter, None) is not service._catalog(shorter, new_data)


async def test_the_answers_use_the_offered_models_and_the_catalogue():
    service = make_service(FakeSource(snapshot_with_data()), Lists(kiln_list()))
    answer = await service.list_models(ListModelsQuery())
    assert [(row.model, row.median_input_price) for row in answer.models] == [
        ("gpt_6_1_sol", None)
    ]
    assert answer.models[0].providers[0].input_price == 2.0
    details = await service.model_details("gpt_6_1_sol", "openrouter")
    assert details.providers[0].status == "ready"
    providers = await service.list_providers()
    assert providers.providers[0].provider == "openrouter"


async def test_sources_for_the_built_in_list_and_no_models_dev():
    source = FakeSource(
        ModelsDevSnapshot(
            data=None, state="unavailable", loaded_at=None, detail="turned off"
        )
    )
    answer = await make_service(source, Lists(kiln_list())).list_providers()
    kiln, md = answer.sources.kiln_model_list, answer.sources.models_dev
    assert (kiln.origin, kiln.loaded_at, kiln.age_seconds) == ("built_in", None, None)
    assert (md.state, md.loaded_at, md.age_seconds, md.detail) == (
        "unavailable",
        None,
        None,
        "turned off",
    )


async def test_sources_for_the_remote_list_with_ages():
    kiln_loaded = NOW - timedelta(days=2)
    md_loaded = NOW - timedelta(hours=7, seconds=0.5)
    base = kiln_list()
    lists = Lists(KilnModelList(base.models, base.providers, loaded_at=kiln_loaded))
    source = FakeSource(
        ModelsDevSnapshot(
            data=models_dev(models_dev_file()),
            state="stale",
            loaded_at=md_loaded,
            detail="HTTP 503",
        )
    )
    answer = await make_service(source, lists).model_details("gpt_6_1_sol", None)
    kiln, md = answer.sources.kiln_model_list, answer.sources.models_dev
    assert (kiln.origin, kiln.loaded_at, kiln.age_seconds) == (
        "remote_config",
        kiln_loaded,
        2 * 24 * 3600,
    )
    assert (md.state, md.loaded_at, md.age_seconds, md.detail) == (
        "stale",
        md_loaded,
        7 * 3600,
        "HTTP 503",
    )


def test_read_kiln_model_list_takes_the_process_list_and_its_load_time():
    with patch.object(remote_config.remote_model_list_state, "loaded_at", None):
        loaded = read_kiln_model_list()
    assert loaded.models == tuple(built_in_models)
    assert all(a is b for a, b in zip(loaded.models, built_in_models))
    assert loaded.providers == tuple(built_in_providers)
    assert loaded.loaded_at is None
    with patch.object(remote_config.remote_model_list_state, "loaded_at", NOW):
        assert read_kiln_model_list().loaded_at == NOW
