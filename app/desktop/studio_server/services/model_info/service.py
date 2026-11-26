"""The model info service: gathers the inputs of each request (Kiln's model
list, the models.dev data, what Kiln offers now) and calls the view."""

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime

from kiln_ai.adapters import remote_config
from kiln_ai.adapters.ml_model_list import KilnModel, built_in_models
from kiln_ai.adapters.ml_provider_list import built_in_providers
from pydantic import BaseModel

from app.desktop.studio_server.api_models.model_info_models import (
    ModelInfoDetails,
    ModelInfoKilnSource,
    ModelInfoList,
    ModelInfoModelsDevSource,
    ModelInfoProviderList,
    ModelInfoSources,
)
from app.desktop.studio_server.services.model_info import view
from app.desktop.studio_server.services.model_info.catalog_build import (
    KilnModelList,
    ModelsDevData,
    build_catalog,
)
from app.desktop.studio_server.services.model_info.catalog_schema import Catalog
from app.desktop.studio_server.services.model_info.models_dev import (
    ModelsDevSnapshot,
    ModelsDevSource,
    utc_now,
)
from app.desktop.studio_server.services.model_info.view import ListModelsQuery

AvailableModelsFn = Callable[[], Awaitable[Sequence[BaseModel]]]


def read_kiln_model_list() -> KilnModelList:
    """Kiln's model list as the process holds it now. The remote list load
    replaces `built_in_models` in place under `refresh_lock`."""
    with remote_config.refresh_lock:
        models = tuple(built_in_models)
        loaded_at = remote_config.remote_model_list_loaded_at()
    return KilnModelList(
        models=models, providers=tuple(built_in_providers), loaded_at=loaded_at
    )


def _age_seconds(now: datetime, then: datetime | None) -> int | None:
    return None if then is None else int((now - then).total_seconds())


class ModelInfoService:
    """One per app. Keeps the last built catalogue, and builds a new one only
    when the models.dev data or Kiln's model list has changed."""

    def __init__(
        self,
        *,
        available_models: AvailableModelsFn,
        models_dev: ModelsDevSource,
        kiln_model_list: Callable[[], KilnModelList] = read_kiln_model_list,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._available_models = available_models
        self._models_dev = models_dev
        self._kiln_model_list = kiln_model_list
        self._now = now
        # The last catalogue, with the Kiln models and the models.dev data it
        # was built from.
        self._built: (
            tuple[tuple[KilnModel, ...], ModelsDevData | None, Catalog] | None
        ) = None

    async def list_models(self, query: ListModelsQuery) -> ModelInfoList:
        catalog, offered, sources = await self._inputs()
        return view.list_models(catalog, offered, sources, query)

    async def model_details(
        self, model_id: str, provider: str | None
    ) -> ModelInfoDetails:
        catalog, offered, sources = await self._inputs()
        return view.model_details(catalog, offered, sources, model_id, provider)

    async def list_providers(self) -> ModelInfoProviderList:
        catalog, offered, sources = await self._inputs()
        return view.list_providers(catalog, offered, sources)

    async def _inputs(self) -> tuple[Catalog, view.Offered, ModelInfoSources]:
        kiln = self._kiln_model_list()
        snapshot = await self._models_dev.current()
        payload = [p.model_dump(mode="json") for p in await self._available_models()]
        offered = view.Offered.from_payload(payload)
        catalog = self._catalog(kiln, snapshot.data)
        return catalog, offered, self._sources(kiln, snapshot)

    def _catalog(
        self, kiln: KilnModelList, models_dev: ModelsDevData | None
    ) -> Catalog:
        built = self._built
        if (
            built is not None
            and built[1] is models_dev
            and len(built[0]) == len(kiln.models)
            and all(a is b for a, b in zip(built[0], kiln.models))
        ):
            return built[2]
        catalog = build_catalog(kiln, models_dev)
        self._built = (kiln.models, models_dev, catalog)
        return catalog

    def _sources(
        self, kiln: KilnModelList, snapshot: ModelsDevSnapshot
    ) -> ModelInfoSources:
        now = self._now()
        return ModelInfoSources(
            kiln_model_list=ModelInfoKilnSource(
                origin="built_in" if kiln.loaded_at is None else "remote_config",
                loaded_at=kiln.loaded_at,
                age_seconds=_age_seconds(now, kiln.loaded_at),
            ),
            models_dev=ModelInfoModelsDevSource(
                state=snapshot.state,
                loaded_at=snapshot.loaded_at,
                age_seconds=_age_seconds(now, snapshot.loaded_at),
                detail=snapshot.detail,
            ),
        )
