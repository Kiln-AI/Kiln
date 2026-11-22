from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from kiln_server.utils.agent_checks.policy import ALLOW_AGENT
from pydantic import StringConstraints

from app.desktop.studio_server.api_models.model_info_models import (
    ModelInfoDetails,
    ModelInfoList,
    ModelInfoProviderList,
)
from app.desktop.studio_server.services.model_info.models_dev import ModelsDevSource
from app.desktop.studio_server.services.model_info.service import (
    AvailableModelsFn,
    ModelInfoService,
)
from app.desktop.studio_server.services.model_info.view import (
    InvalidModelQueryError,
    ListModelsQuery,
    ModelNotFoundError,
)

_TAG = Annotated[str, StringConstraints(min_length=1, max_length=40)]
_PROVIDER_DESC = "Kiln provider id, for example openrouter or gemini_api."


def connect_model_info_api(
    app: FastAPI,
    *,
    available_models: AvailableModelsFn,
    models_dev: ModelsDevSource,
) -> None:
    service = ModelInfoService(available_models=available_models, models_dev=models_dev)

    @app.get(
        "/api/model_info/models",
        summary="List Model Info",
        tags=["Providers & Models"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_model_info(
        search: Annotated[
            str | None,
            Query(
                min_length=1,
                max_length=100,
                description="Name search on the model id and display name. Forgives"
                " case, spaces and punctuation; with no match, returns close names"
                " (fuzzy_match is true). Runs after the other filters.",
            ),
        ] = None,
        featured: Annotated[
            bool | None,
            Query(
                description="true: only models Kiln ranks as featured. false: only"
                " models without a featured rank."
            ),
        ] = None,
        provider: Annotated[
            str | None,
            Query(
                min_length=1,
                max_length=200,
                description=f"{_PROVIDER_DESC} Keeps only that provider's entries.",
            ),
        ] = None,
        family: Annotated[
            str | None,
            Query(
                min_length=1,
                max_length=100,
                description="Exact match on Kiln's model family.",
            ),
        ] = None,
        tags: Annotated[
            list[_TAG] | None,
            Query(
                max_length=12,
                description="A model passes when it has ANY of these tags, on the"
                " model or on a listed provider entry. Repeat the parameter for"
                " several tags.",
            ),
        ] = None,
        supports_tools: Annotated[
            bool | None, Query(description="Filter provider entries on tool calls.")
        ] = None,
        supports_vision: Annotated[
            bool | None, Query(description="Filter provider entries on image input.")
        ] = None,
        has_thinking_levels: Annotated[
            bool | None,
            Query(
                description="Filter provider entries on thinking levels a run config"
                " can set."
            ),
        ] = None,
        reasoning_model: Annotated[
            bool | None,
            Query(
                description="Filter models that reason before they answer (models.dev)."
                " An unknown value does not pass."
            ),
        ] = None,
        open_weights: Annotated[
            bool | None,
            Query(
                description="Filter models on open weights (models.dev). An unknown"
                " value does not pass."
            ),
        ] = None,
        include_not_available: Annotated[
            bool,
            Query(
                description="Also list provider entries the user cannot run now"
                " (status not_offered or not_connected). Use it to look up a model id."
            ),
        ] = False,
        include_deprecated: Annotated[
            bool, Query(description="Also list deprecated provider entries.")
        ] = False,
        include_notes: Annotated[
            bool,
            Query(description="Fill editorial_notes and agent_notes in each row."),
        ] = False,
        sort: Annotated[
            Literal["featured", "price", "newest"] | None,
            Query(
                description="featured: Kiln's ranking. price: cheapest first, by median"
                " input + output price. newest: latest release first. Default: the"
                " featured order, or best match first with search."
            ),
        ] = None,
        limit: Annotated[int, Query(ge=1, le=200, description="Page size.")] = 25,
        offset: Annotated[int, Query(ge=0, description="Rows to skip.")] = 0,
    ) -> ModelInfoList:
        """List Kiln's models with prices, limits and release dates from
        models.dev, and for each provider entry whether the user can run it
        now (status). By default only entries the user can run now (status
        ready, not deprecated) are listed. Rows with no listed entry are left
        out. `total` counts the rows after all filters; page with `offset`."""
        query = ListModelsQuery(
            search=search,
            featured=featured,
            provider=provider,
            family=family,
            tags=tuple(tags) if tags is not None else None,
            supports_tools=supports_tools,
            supports_vision=supports_vision,
            has_thinking_levels=has_thinking_levels,
            reasoning_model=reasoning_model,
            open_weights=open_weights,
            include_not_available=include_not_available,
            include_deprecated=include_deprecated,
            include_notes=include_notes,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        try:
            return await service.list_models(query)
        except InvalidModelQueryError as e:
            raise HTTPException(status_code=422, detail=str(e))

    @app.get(
        "/api/model_info/model_details",
        summary="Get Model Info Details",
        tags=["Providers & Models"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_model_info_details(
        model_id: Annotated[
            str,
            Query(
                min_length=1,
                max_length=200,
                description="Kiln model id, as GET /api/model_info/models lists it."
                " A query parameter, because ids of custom and fine-tuned models"
                " hold '/' and '::'.",
            ),
        ],
        provider: Annotated[
            str | None,
            Query(
                min_length=1,
                max_length=200,
                description=f"{_PROVIDER_DESC} Keeps only that provider's entry.",
            ),
        ] = None,
    ) -> ModelInfoDetails:
        """The full record of one model: every provider entry with its status,
        prices, limits, capabilities, thinking levels, default output mode and
        what Kiln suggests the model for. Read the entry of the provider you
        will use before you write a run config. 404 when the model, or its entry
        for `provider`, does not exist."""
        try:
            return await service.model_details(model_id, provider)
        except ModelNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get(
        "/api/model_info/providers",
        summary="List Model Info Providers",
        tags=["Providers & Models"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_model_info_providers() -> ModelInfoProviderList:
        """Every model provider Kiln knows, each marked connected or
        not_connected, with the number of models ready to run on it, and
        Kiln's notes on data retention, rate limits and gotchas. Connected
        providers with models come first."""
        return await service.list_providers()
