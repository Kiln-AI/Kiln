import json

from kiln_ai.adapters.ollama_tools import (
    OllamaConnection,
    ollama_model_installed,
    parse_ollama_tags,
)


def test_parse_ollama_tags_no_models():
    json_response = '{"models":[{"name":"scosman_net","model":"scosman_net:latest"},{"name":"phi3.5:latest","model":"phi3.5:latest","modified_at":"2024-10-02T12:04:35.191519822-04:00","size":2176178843,"digest":"61819fb370a3c1a9be6694869331e5f85f867a079e9271d66cb223acb81d04ba","details":{"parent_model":"","format":"gguf","family":"phi3","families":["phi3"],"parameter_size":"3.8B","quantization_level":"Q4_0"}},{"name":"gemma2:2b","model":"gemma2:2b","modified_at":"2024-09-09T16:46:38.64348929-04:00","size":1629518495,"digest":"8ccf136fdd5298f3ffe2d69862750ea7fb56555fa4d5b18c04e3fa4d82ee09d7","details":{"parent_model":"","format":"gguf","family":"gemma2","families":["gemma2"],"parameter_size":"2.6B","quantization_level":"Q4_0"}},{"name":"llama3.1:latest","model":"llama3.1:latest","modified_at":"2024-09-01T17:19:43.481523695-04:00","size":4661230720,"digest":"f66fc8dc39ea206e03ff6764fcc696b1b4dfb693f0b6ef751731dd4e6269046e","details":{"parent_model":"","format":"gguf","family":"llama","families":["llama"],"parameter_size":"8.0B","quantization_level":"Q4_0"}}]}'
    tags = json.loads(json_response)
    conn = parse_ollama_tags(tags)
    assert "phi3.5:latest" in conn.supported_models
    assert "gemma2:2b" in conn.supported_models
    assert "llama3.1:latest" in conn.supported_models
    assert "scosman_net:latest" in conn.untested_models


def test_parse_ollama_tags_only_untested_models():
    json_response = '{"models":[{"name":"scosman_net","model":"scosman_net:latest"}]}'
    tags = json.loads(json_response)
    conn = parse_ollama_tags(tags)
    assert conn.supported_models == []
    assert conn.untested_models == ["scosman_net:latest"]


def test_ollama_model_installed():
    conn = OllamaConnection(
        supported_models=["phi3.5:latest", "gemma2:2b", "llama3.1:latest"],
        message="Connected",
        untested_models=["scosman_net:latest"],
    )
    assert ollama_model_installed(conn, "phi3.5:latest")
    assert ollama_model_installed(conn, "phi3.5")
    assert ollama_model_installed(conn, "gemma2:2b")
    assert ollama_model_installed(conn, "llama3.1:latest")
    assert ollama_model_installed(conn, "llama3.1")
    assert ollama_model_installed(conn, "scosman_net:latest")
    assert ollama_model_installed(conn, "scosman_net")
    assert not ollama_model_installed(conn, "unknown_model")
