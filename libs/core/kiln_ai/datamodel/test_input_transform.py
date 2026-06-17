import pytest
from pydantic import TypeAdapter, ValidationError

from kiln_ai.datamodel.input_transform import (
    InputTransform,
    JinjaInputTransform,
)

input_transform_adapter = TypeAdapter(InputTransform)


class TestJinjaInputTransform:
    def test_valid_template(self):
        t = JinjaInputTransform(template="{{ input }}")
        assert t.type == "jinja"
        assert t.template == "{{ input }}"

    def test_valid_template_with_blocks(self):
        t = JinjaInputTransform(template="{% if input %}yes{% endif %}")
        assert t.template == "{% if input %}yes{% endif %}"

    def test_malformed_template_raises_validation_error(self):
        with pytest.raises(ValidationError, match="Invalid Jinja2 template"):
            JinjaInputTransform(template="{% if ")

    def test_unclosed_block_raises_validation_error(self):
        with pytest.raises(ValidationError, match="Invalid Jinja2 template"):
            JinjaInputTransform(template="{% for x in items %}")

    def test_roundtrip_model_dump_and_reconstruct(self):
        original = JinjaInputTransform(template="{{ input.field }}")
        dumped = original.model_dump()
        restored = JinjaInputTransform.model_validate(dumped)
        assert restored == original
        assert restored.type == "jinja"
        assert restored.template == "{{ input.field }}"

    def test_json_serialization_roundtrip(self):
        original = JinjaInputTransform(template="{{ input }}")
        json_str = original.model_dump_json()
        restored = JinjaInputTransform.model_validate_json(json_str)
        assert restored == original


class TestInputTransformDiscriminatedUnion:
    def test_dispatch_jinja_from_dict(self):
        result = input_transform_adapter.validate_python(
            {"type": "jinja", "template": "{{ input }}"}
        )
        assert isinstance(result, JinjaInputTransform)
        assert result.type == "jinja"
        assert result.template == "{{ input }}"

    def test_dispatch_missing_type_raises_validation_error(self):
        with pytest.raises(ValidationError):
            input_transform_adapter.validate_python({"template": "{{ input }}"})

    def test_dispatch_unknown_type_raises_validation_error(self):
        with pytest.raises(ValidationError):
            input_transform_adapter.validate_python(
                {"type": "unknown", "template": "{{ x }}"}
            )

    def test_dispatch_from_model_instance(self):
        instance = JinjaInputTransform(template="{{ input }}")
        result = input_transform_adapter.validate_python(instance)
        assert isinstance(result, JinjaInputTransform)
        assert result == instance

    def test_roundtrip_through_type_adapter(self):
        original = JinjaInputTransform(template="{{ input.name }}")
        dumped = input_transform_adapter.dump_python(original)
        restored = input_transform_adapter.validate_python(dumped)
        assert isinstance(restored, JinjaInputTransform)
        assert restored == original
