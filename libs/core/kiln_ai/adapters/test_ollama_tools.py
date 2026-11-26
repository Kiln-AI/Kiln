import asyncio
import json
from unittest.mock import patch

import httpx
import pytest
import respx

from kiln_ai.adapters.conftest import OLLAMA_TEST_URL
from kiln_ai.adapters.ml_embedding_model_list import (
    KilnEmbeddingModel,
    KilnEmbeddingModelProvider,
)

# Mock data for testing - using proper Pydantic model instances
from kiln_ai.adapters.ml_model_list import KilnModel, KilnModelProvider
from kiln_ai.adapters.ollama_tools import (
    OllamaConnection,
    OllamaTagCache,
    ensure_ollama_tags_fresh,
    get_ollama_connection,
    ollama_embedding_model_installed,
    ollama_model_installed,
    ollama_online,
    parse_ollama_tags,
    record_ollama_tags,
    resolve_ollama_model_variant,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName

MOCK_BUILT_IN_MODELS = [
    KilnModel(
        family="phi",
        name="phi3.5",
        friendly_name="phi3.5",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="phi3.5",
                ollama_model_aliases=None,
            )
        ],
    ),
    KilnModel(
        family="gemma",
        name="gemma2",
        friendly_name="gemma2",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="gemma2:2b",
                ollama_model_aliases=None,
            )
        ],
    ),
    KilnModel(
        family="llama",
        name="llama3.1",
        friendly_name="llama3.1",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="llama3.1",
                ollama_model_aliases=None,
            )
        ],
    ),
]

MOCK_BUILT_IN_EMBEDDING_MODELS = [
    KilnEmbeddingModel(
        family="gemma",
        name="embeddinggemma",
        friendly_name="embeddinggemma",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.ollama,
                model_id="embeddinggemma:300m",
                n_dimensions=768,
                ollama_model_aliases=["embeddinggemma"],
            )
        ],
    ),
]


@patch("kiln_ai.adapters.ollama_tools.built_in_models", MOCK_BUILT_IN_MODELS)
@patch(
    "kiln_ai.adapters.ollama_tools.built_in_embedding_models",
    MOCK_BUILT_IN_EMBEDDING_MODELS,
)
def test_parse_ollama_tags_models():
    json_response = '{"models":[{"name":"scosman_net","model":"scosman_net:latest"},{"name":"phi3.5:latest","model":"phi3.5:latest","modified_at":"2024-10-02T12:04:35.191519822-04:00","size":2176178843,"digest":"61819fb370a3c1a9be6694869331e5f85f867a079e9271d66cb223acb81d04ba","details":{"parent_model":"","format":"gguf","family":"phi3","families":["phi3"],"parameter_size":"3.8B","quantization_level":"Q4_0"}},{"name":"gemma2:2b","model":"gemma2:2b","modified_at":"2024-09-09T16:46:38.64348929-04:00","size":1629518495,"digest":"8ccf136fdd5298f3ffe2d69862750ea7fb56555fa4d5b18c04e3fa4d82ee09d7","details":{"parent_model":"","format":"gguf","family":"gemma2","families":["gemma2"],"parameter_size":"2.6B","quantization_level":"Q4_0"}},{"name":"llama3.1:latest","model":"llama3.1:latest","modified_at":"2024-09-01T17:19:43.481523695-04:00","size":4661230720,"digest":"f66fc8dc39ea206e03ff6764fcc696b1b4dfb693f0b6ef751731dd4e6269046e","details":{"parent_model":"","format":"gguf","family":"llama","families":["llama"],"parameter_size":"8.0B","quantization_level":"Q4_0"}}]}'
    tags = json.loads(json_response)
    conn = parse_ollama_tags(tags)
    assert "phi3.5:latest" in conn.supported_models
    assert "gemma2:2b" in conn.supported_models
    assert "llama3.1:latest" in conn.supported_models
    assert "scosman_net:latest" in conn.untested_models

    # there should be no embedding models because the tags response does not include any embedding models
    # that are in the built-in embedding models list
    assert len(conn.supported_embedding_models) == 0


@patch("kiln_ai.adapters.ollama_tools.built_in_models", MOCK_BUILT_IN_MODELS)
@patch(
    "kiln_ai.adapters.ollama_tools.built_in_embedding_models",
    MOCK_BUILT_IN_EMBEDDING_MODELS,
)
@pytest.mark.parametrize("json_response", ["{}", '{"models": []}'])
def test_parse_ollama_tags_no_models(json_response):
    tags = json.loads(json_response)
    conn = parse_ollama_tags(tags)
    assert (
        conn.message
        == "Ollama is running, but no supported models are installed. Install one or more supported model, like 'ollama pull phi3.5'."
    )
    assert len(conn.supported_models) == 0
    assert len(conn.untested_models) == 0
    assert len(conn.supported_embedding_models) == 0


@patch("kiln_ai.adapters.ollama_tools.built_in_models", MOCK_BUILT_IN_MODELS)
@patch(
    "kiln_ai.adapters.ollama_tools.built_in_embedding_models",
    MOCK_BUILT_IN_EMBEDDING_MODELS,
)
def test_parse_ollama_tags_empty_models():
    """Test parsing Ollama tags response with empty models list"""
    json_response = '{"models": []}'
    tags = json.loads(json_response)
    conn = parse_ollama_tags(tags)

    # Check that connection indicates no supported models
    assert conn.supported_models == []
    assert conn.untested_models == []
    assert conn.supported_embedding_models == []
    assert "no supported models are installed" in conn.message


@patch("kiln_ai.adapters.ollama_tools.built_in_models", MOCK_BUILT_IN_MODELS)
@patch(
    "kiln_ai.adapters.ollama_tools.built_in_embedding_models",
    MOCK_BUILT_IN_EMBEDDING_MODELS,
)
def test_parse_ollama_tags_only_untested_models():
    json_response = '{"models":[{"name":"scosman_net","model":"scosman_net:latest"}]}'
    tags = json.loads(json_response)
    conn = parse_ollama_tags(tags)
    assert conn.supported_models == []
    assert conn.untested_models == ["scosman_net:latest"]

    # there should be no embedding models because the tags response does not include any embedding models
    # that are in the built-in embedding models list
    assert len(conn.supported_embedding_models) == 0


def test_ollama_model_installed():
    conn = OllamaConnection(
        supported_models=["phi3.5:latest", "gemma2:2b", "llama3.1:latest"],
        message="Connected",
        untested_models=["scosman_net:latest"],
        supported_embedding_models=["embeddinggemma:300m"],
    )
    assert ollama_model_installed(conn, "phi3.5:latest")
    assert ollama_model_installed(conn, "phi3.5")
    assert ollama_model_installed(conn, "gemma2:2b")
    assert ollama_model_installed(conn, "llama3.1:latest")
    assert ollama_model_installed(conn, "llama3.1")
    assert ollama_model_installed(conn, "scosman_net:latest")
    assert ollama_model_installed(conn, "scosman_net")
    assert not ollama_model_installed(conn, "unknown_model")

    # use the ollama_embedding_model_installed for testing embedding models installed, not ollama_model_installed
    assert not ollama_model_installed(conn, "embeddinggemma:300m")
    assert not ollama_model_installed(conn, "embeddinggemma")


def test_ollama_model_installed_embedding_models():
    conn = OllamaConnection(
        message="Connected",
        supported_models=["phi3.5:latest", "gemma2:2b", "llama3.1:latest"],
        untested_models=["scosman_net:latest"],
        supported_embedding_models=["embeddinggemma:300m", "embeddinggemma:latest"],
    )

    assert ollama_embedding_model_installed(conn, "embeddinggemma:300m")
    assert ollama_embedding_model_installed(conn, "embeddinggemma:latest")
    assert not ollama_embedding_model_installed(conn, "unknown_embedding")

    # use the ollama_model_installed for testing regular models installed, not ollama_embedding_model_installed
    assert not ollama_embedding_model_installed(conn, "phi3.5:latest")
    assert not ollama_embedding_model_installed(conn, "gemma2:2b")
    assert not ollama_embedding_model_installed(conn, "llama3.1:latest")
    assert not ollama_embedding_model_installed(conn, "scosman_net:latest")


@patch("kiln_ai.adapters.ollama_tools.built_in_models", MOCK_BUILT_IN_MODELS)
@patch(
    "kiln_ai.adapters.ollama_tools.built_in_embedding_models",
    MOCK_BUILT_IN_EMBEDDING_MODELS,
)
def test_parse_ollama_tags_with_embedding_models():
    """Test parsing Ollama tags response that includes embedding models"""
    json_response = """{
        "models": [
            {
                "name": "phi3.5:latest",
                "model": "phi3.5:latest"
            },
            {
                "name": "embeddinggemma:300m",
                "model": "embeddinggemma:300m"
            },
            {
                "name": "embeddinggemma:latest",
                "model": "embeddinggemma:latest"
            },
            {
                "name": "unknown_embedding:latest",
                "model": "unknown_embedding:latest"
            }
        ]
    }"""
    tags = json.loads(json_response)
    conn = parse_ollama_tags(tags)

    # Check that embedding models are properly categorized
    assert "embeddinggemma:300m" in conn.supported_embedding_models
    assert "embeddinggemma:latest" in conn.supported_embedding_models

    # Check that regular models are still parsed correctly
    assert "phi3.5:latest" in conn.supported_models

    # Check that embedding models are NOT in the main model lists
    assert "embeddinggemma:300m" not in conn.supported_models
    assert "embeddinggemma:latest" not in conn.supported_models
    assert "embeddinggemma:300m" not in conn.untested_models
    assert "embeddinggemma:latest" not in conn.untested_models

    # we assume the unknown models are normal models, not embedding models - because
    # we don't support untested embedding models currently
    assert "unknown_embedding:latest" not in conn.supported_embedding_models
    assert "unknown_embedding:latest" in conn.untested_models


@patch("kiln_ai.adapters.ollama_tools.built_in_models", MOCK_BUILT_IN_MODELS)
@patch(
    "kiln_ai.adapters.ollama_tools.built_in_embedding_models",
    MOCK_BUILT_IN_EMBEDDING_MODELS,
)
def test_parse_ollama_tags_embedding_model_aliases():
    """Test parsing Ollama tags response with embedding model aliases"""
    json_response = """{
        "models": [
            {
                "name": "embeddinggemma",
                "model": "embeddinggemma"
            }
        ]
    }"""
    tags = json.loads(json_response)
    conn = parse_ollama_tags(tags)

    # Check that embedding model aliases are recognized
    assert "embeddinggemma" in conn.supported_embedding_models

    # Check that embedding model aliases are NOT in the main model lists
    assert "embeddinggemma" not in conn.supported_models
    assert "embeddinggemma" not in conn.untested_models

    assert len(conn.supported_models) == 0
    assert len(conn.untested_models) == 0
    assert len(conn.supported_embedding_models) == 1


@patch("kiln_ai.adapters.ollama_tools.built_in_models", MOCK_BUILT_IN_MODELS)
@patch(
    "kiln_ai.adapters.ollama_tools.built_in_embedding_models",
    MOCK_BUILT_IN_EMBEDDING_MODELS,
)
def test_parse_ollama_tags_only_embedding_models():
    """Test parsing Ollama tags response with only embedding models"""
    json_response = """{
        "models": [
            {
                "name": "embeddinggemma:300m",
                "model": "embeddinggemma:300m"
            }
        ]
    }"""
    tags = json.loads(json_response)
    conn = parse_ollama_tags(tags)

    # Check that embedding models are found but no regular models
    assert "embeddinggemma:300m" in conn.supported_embedding_models
    assert conn.supported_models == []
    assert conn.untested_models == []

    # Check that embedding models are NOT in the main model lists
    assert "embeddinggemma:300m" not in conn.supported_models
    assert "embeddinggemma:300m" not in conn.untested_models


def test_ollama_connection_all_embedding_models():
    """Test OllamaConnection.all_embedding_models() method"""
    conn = OllamaConnection(
        message="Connected",
        supported_models=["phi3.5:latest"],
        untested_models=["unknown:latest"],
        supported_embedding_models=["embeddinggemma:300m", "embeddinggemma:latest"],
    )

    embedding_models = conn.all_embedding_models()
    assert embedding_models == ["embeddinggemma:300m", "embeddinggemma:latest"]


def test_ollama_connection_empty_embedding_models():
    """Test OllamaConnection.all_embedding_models() with empty list"""
    conn = OllamaConnection(
        message="Connected",
        supported_models=["phi3.5:latest"],
        untested_models=["unknown:latest"],
        supported_embedding_models=[],
    )

    embedding_models = conn.all_embedding_models()
    assert embedding_models == []


@patch("kiln_ai.adapters.ollama_tools.built_in_models", MOCK_BUILT_IN_MODELS)
@patch(
    "kiln_ai.adapters.ollama_tools.built_in_embedding_models",
    MOCK_BUILT_IN_EMBEDDING_MODELS,
)
def test_parse_ollama_tags_mixed_models_and_embeddings():
    """Test parsing response with mix of regular models, embedding models, and unknown models"""
    json_response = """{
        "models": [
            {
                "name": "phi3.5:latest",
                "model": "phi3.5:latest"
            },
            {
                "name": "gemma2:2b",
                "model": "gemma2:2b"
            },
            {
                "name": "embeddinggemma:300m",
                "model": "embeddinggemma:300m"
            },
            {
                "name": "embeddinggemma",
                "model": "embeddinggemma"
            },
            {
                "name": "unknown_model:latest",
                "model": "unknown_model:latest"
            },
            {
                "name": "unknown_embedding:latest",
                "model": "unknown_embedding:latest"
            }
        ]
    }"""
    tags = json.loads(json_response)
    conn = parse_ollama_tags(tags)

    # Check regular models
    assert "phi3.5:latest" in conn.supported_models
    assert "gemma2:2b" in conn.supported_models
    assert "unknown_model:latest" in conn.untested_models

    # Check embedding models
    assert "embeddinggemma:300m" in conn.supported_embedding_models
    assert "embeddinggemma" in conn.supported_embedding_models

    # Check that embedding models are NOT in the main model lists
    assert "embeddinggemma:300m" not in conn.supported_models
    assert "embeddinggemma" not in conn.supported_models
    assert "embeddinggemma:300m" not in conn.untested_models
    assert "embeddinggemma" not in conn.untested_models

    # Unknown embedding models should not appear in supported_embedding_models
    assert "unknown_embedding:latest" not in conn.supported_embedding_models

    # Unknown embedding models should appear in untested_models (since they're not recognized as embeddings)
    assert "unknown_embedding:latest" not in conn.supported_models
    assert "unknown_embedding:latest" in conn.untested_models


OTHER_OLLAMA_URL = "http://other-ollama.test:11434"


def installed_tags(*model_names: str) -> httpx.Response:
    return httpx.Response(
        200, json={"models": [{"model": name} for name in model_names]}
    )


def tags_body(*model_names: str) -> dict:
    return {"models": [{"model": name} for name in model_names]}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def tag_cache(clock):
    return OllamaTagCache(ttl_seconds=60, clock=clock)


@pytest.mark.parametrize(
    "installed,model_id,aliases,expected",
    [
        (
            ["nemotron-3-nano", "phi3.5:latest"],
            "nemotron-3-nano",
            ["nemotron-3-nano:30b"],
            "nemotron-3-nano",
        ),
        (
            ["nemotron-3-nano:30b", "phi3.5:latest"],
            "nemotron-3-nano",
            ["nemotron-3-nano:30b"],
            "nemotron-3-nano:30b",
        ),
        (
            ["nemotron-3-nano:latest", "phi3.5:latest"],
            "nemotron-3-nano",
            ["nemotron-3-nano:30b"],
            "nemotron-3-nano",
        ),
        (
            ["phi3.5:latest", "llama3.1:latest"],
            "nemotron-3-nano",
            ["nemotron-3-nano:30b", "nemotron-3-nano:70b"],
            "nemotron-3-nano",
        ),
        (["phi3.5:latest"], "nemotron-3-nano", None, "nemotron-3-nano"),
        (
            ["model:alias1", "model:alias2"],
            "model:primary",
            ["model:alias1", "model:alias2"],
            "model:alias1",
        ),
    ],
)
async def test_resolve_ollama_model_variant(
    ollama_api, installed, model_id, aliases, expected
):
    ollama_api.get("/api/tags").mock(return_value=installed_tags(*installed))

    await ensure_ollama_tags_fresh(ModelProviderName.ollama)

    assert resolve_ollama_model_variant(model_id, aliases) == expected


def test_resolve_ollama_model_variant_cache_miss_returns_model_id(ollama_api):
    assert (
        resolve_ollama_model_variant("nemotron-3-nano", ["nemotron-3-nano:30b"])
        == "nemotron-3-nano"
    )
    assert not ollama_api.calls


def test_resolve_ollama_model_variant_ignores_tags_from_another_url(ollama_api):
    record_ollama_tags(OTHER_OLLAMA_URL, tags_body("nemotron-3-nano:30b"))

    assert (
        resolve_ollama_model_variant("nemotron-3-nano", ["nemotron-3-nano:30b"])
        == "nemotron-3-nano"
    )


@pytest.mark.parametrize(
    "response",
    [
        httpx.ConnectError("Connection refused"),
        httpx.ReadTimeout(""),
        httpx.Response(500),
        httpx.Response(200, json={"error": "no models key"}),
        httpx.Response(200, text="not json"),
    ],
)
async def test_resolve_ollama_model_variant_falls_back_to_model_id(
    ollama_api, response
):
    route = ollama_api.get("/api/tags")
    if isinstance(response, Exception):
        route.mock(side_effect=response)
    else:
        route.mock(return_value=response)

    await ensure_ollama_tags_fresh(ModelProviderName.ollama)

    result = resolve_ollama_model_variant("nemotron-3-nano", ["nemotron-3-nano:30b"])
    assert result == "nemotron-3-nano"


async def test_ensure_ollama_tags_fresh_skips_other_providers(ollama_api):
    await ensure_ollama_tags_fresh(ModelProviderName.openai)

    assert not ollama_api.calls


async def test_ensure_ollama_tags_fresh_follows_redirects(ollama_api):
    ollama_api.get("/api/tags").mock(
        return_value=httpx.Response(
            307, headers={"Location": f"{OLLAMA_TEST_URL}/v2/api/tags"}
        )
    )
    ollama_api.get("/v2/api/tags").mock(
        return_value=installed_tags("nemotron-3-nano:30b")
    )

    await ensure_ollama_tags_fresh(ModelProviderName.ollama)

    assert (
        resolve_ollama_model_variant("nemotron-3-nano", ["nemotron-3-nano:30b"])
        == "nemotron-3-nano:30b"
    )


async def test_tag_cache_hit_skips_request(ollama_api, tag_cache, clock):
    route = ollama_api.get("/api/tags").mock(return_value=installed_tags("phi3.5"))

    await tag_cache.refresh(OLLAMA_TEST_URL)
    clock.now += 59
    await tag_cache.refresh(OLLAMA_TEST_URL)

    assert route.call_count == 1
    assert tag_cache.installed_models(OLLAMA_TEST_URL) == frozenset({"phi3.5"})


async def test_tag_cache_refetches_after_ttl(ollama_api, tag_cache, clock):
    route = ollama_api.get("/api/tags").mock(
        side_effect=[installed_tags("phi3.5"), installed_tags("phi3.5", "qwen3")]
    )

    await tag_cache.refresh(OLLAMA_TEST_URL)
    clock.now += 60
    await tag_cache.refresh(OLLAMA_TEST_URL)

    assert route.call_count == 2
    assert tag_cache.installed_models(OLLAMA_TEST_URL) == frozenset({"phi3.5", "qwen3"})


async def test_tag_cache_is_keyed_by_url(tag_cache):
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{OLLAMA_TEST_URL}/api/tags").mock(
            return_value=installed_tags("phi3.5")
        )
        other = router.get(f"{OTHER_OLLAMA_URL}/api/tags").mock(
            return_value=installed_tags("qwen3")
        )

        await tag_cache.refresh(OLLAMA_TEST_URL)
        assert tag_cache.installed_models(OTHER_OLLAMA_URL) is None

        await tag_cache.refresh(OTHER_OLLAMA_URL)

    assert other.call_count == 1
    assert tag_cache.installed_models(OTHER_OLLAMA_URL) == frozenset({"qwen3"})
    assert tag_cache.installed_models(OLLAMA_TEST_URL) is None


async def test_tag_cache_remembers_failures_for_ttl(ollama_api, tag_cache, clock):
    route = ollama_api.get("/api/tags").mock(
        side_effect=httpx.ConnectTimeout("timed out")
    )

    await tag_cache.refresh(OLLAMA_TEST_URL)
    clock.now += 59
    await tag_cache.refresh(OLLAMA_TEST_URL)
    assert route.call_count == 1

    clock.now += 1
    await tag_cache.refresh(OLLAMA_TEST_URL)
    assert route.call_count == 2


async def test_tag_cache_keeps_last_known_tags_after_failure(
    ollama_api, tag_cache, clock
):
    ollama_api.get("/api/tags").mock(
        side_effect=[installed_tags("phi3.5"), httpx.ConnectError("refused")]
    )

    await tag_cache.refresh(OLLAMA_TEST_URL)
    clock.now += 60
    await tag_cache.refresh(OLLAMA_TEST_URL)

    assert tag_cache.installed_models(OLLAMA_TEST_URL) == frozenset({"phi3.5"})
    assert tag_cache.is_fresh(OLLAMA_TEST_URL)


async def test_tag_cache_concurrent_refreshes_share_one_request(ollama_api, tag_cache):
    release = asyncio.Event()

    async def slow_tags(request):
        await release.wait()
        return installed_tags("phi3.5")

    route = ollama_api.get("/api/tags").mock(side_effect=slow_tags)

    refreshes = [
        asyncio.create_task(tag_cache.refresh(OLLAMA_TEST_URL)) for _ in range(5)
    ]
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(*refreshes)

    assert route.call_count == 1
    assert tag_cache.installed_models(OLLAMA_TEST_URL) == frozenset({"phi3.5"})


async def test_tag_cache_cancelled_caller_does_not_cancel_shared_fetch(
    ollama_api, tag_cache
):
    release = asyncio.Event()

    async def slow_tags(request):
        await release.wait()
        return installed_tags("phi3.5")

    ollama_api.get("/api/tags").mock(side_effect=slow_tags)

    cancelled = asyncio.create_task(tag_cache.refresh(OLLAMA_TEST_URL))
    waiting = asyncio.create_task(tag_cache.refresh(OLLAMA_TEST_URL))
    await asyncio.sleep(0)
    cancelled.cancel()
    release.set()
    await waiting

    assert cancelled.cancelled()
    assert tag_cache.installed_models(OLLAMA_TEST_URL) == frozenset({"phi3.5"})


def test_tag_cache_works_across_event_loops():
    tag_cache = OllamaTagCache(ttl_seconds=0)
    with respx.mock() as router:
        route = router.get(f"{OLLAMA_TEST_URL}/api/tags").mock(
            return_value=installed_tags("phi3.5")
        )

        asyncio.run(tag_cache.refresh(OLLAMA_TEST_URL))
        asyncio.run(tag_cache.refresh(OLLAMA_TEST_URL))

    assert route.call_count == 2


@patch("kiln_ai.adapters.ollama_tools.built_in_models", MOCK_BUILT_IN_MODELS)
@patch(
    "kiln_ai.adapters.ollama_tools.built_in_embedding_models",
    MOCK_BUILT_IN_EMBEDDING_MODELS,
)
async def test_get_ollama_connection_success(ollama_api):
    ollama_api.get("/api/tags").mock(
        return_value=installed_tags("phi3.5:latest", "my-custom-model")
    )

    conn = await get_ollama_connection()

    assert conn is not None
    assert conn.supported_models == ["phi3.5:latest"]
    assert conn.untested_models == ["my-custom-model"]


async def test_get_ollama_connection_fills_tag_cache(ollama_api):
    route = ollama_api.get("/api/tags").mock(
        return_value=installed_tags("nemotron-3-nano:30b")
    )

    await get_ollama_connection()
    await ensure_ollama_tags_fresh(ModelProviderName.ollama)

    assert route.call_count == 1
    assert (
        resolve_ollama_model_variant("nemotron-3-nano", ["nemotron-3-nano:30b"])
        == "nemotron-3-nano:30b"
    )


async def test_get_ollama_connection_unreachable(ollama_api):
    route = ollama_api.get("/api/tags").mock(side_effect=httpx.ConnectError("refused"))

    assert await get_ollama_connection() is None
    await ensure_ollama_tags_fresh(ModelProviderName.ollama)

    assert route.call_count == 1


async def test_get_ollama_connection_follows_redirects(ollama_api):
    ollama_api.get("/api/tags").mock(
        return_value=httpx.Response(
            307, headers={"Location": f"{OLLAMA_TEST_URL}/v2/api/tags"}
        )
    )
    ollama_api.get("/v2/api/tags").mock(return_value=installed_tags("phi3.5:latest"))

    conn = await get_ollama_connection()

    assert conn is not None
    assert "phi3.5:latest" in conn.all_models()


@pytest.mark.parametrize(
    "side_effect,expected",
    [
        (installed_tags(), True),
        (httpx.ConnectError("refused"), False),
    ],
)
async def test_ollama_online(ollama_api, side_effect, expected):
    ollama_api.get("/api/tags").mock(side_effect=[side_effect])

    assert await ollama_online() is expected


async def test_ollama_online_follows_redirects(ollama_api):
    ollama_api.get("/api/tags").mock(
        return_value=httpx.Response(
            307, headers={"Location": f"{OLLAMA_TEST_URL}/v2/api/tags"}
        )
    )
    redirected = ollama_api.get("/v2/api/tags").mock(return_value=installed_tags())

    assert await ollama_online() is True
    assert redirected.call_count == 1


async def test_ollama_tag_refresh_does_not_block_event_loop(ollama_api):
    other_work_done = asyncio.Event()

    async def ollama_waits_for_other_work(request):
        await asyncio.wait_for(other_work_done.wait(), timeout=5)
        return installed_tags("nemotron-3-nano:30b")

    ollama_api.get("/api/tags").mock(side_effect=ollama_waits_for_other_work)

    async def other_work():
        other_work_done.set()

    await asyncio.gather(
        ensure_ollama_tags_fresh(ModelProviderName.ollama), other_work()
    )

    assert (
        resolve_ollama_model_variant("nemotron-3-nano", ["nemotron-3-nano:30b"])
        == "nemotron-3-nano:30b"
    )
