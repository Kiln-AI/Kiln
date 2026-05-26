import pytest
from jinja2 import Undefined, UndefinedError
from jinja2.sandbox import SecurityError

from kiln_ai.datamodel.input_transform import JinjaInputTransform
from kiln_ai.utils.jinja_engine import (
    compile_expression_or_raise,
    compile_template_or_raise,
    extract,
    render_input_transform,
)


class TestCompileTemplateOrRaise:
    def test_valid_template(self):
        compile_template_or_raise("Hello {{ name }}")

    def test_valid_template_with_blocks(self):
        compile_template_or_raise("{% if x %}yes{% endif %}")

    def test_syntax_error_raises_value_error(self):
        with pytest.raises(ValueError, match="line"):
            compile_template_or_raise("{% if ")

    def test_unclosed_block_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid Jinja2 template"):
            compile_template_or_raise("{% for x in items %}")


class TestCompileExpressionOrRaise:
    def test_valid_expression(self):
        compile_expression_or_raise("foo")

    def test_valid_expression_with_filter(self):
        compile_expression_or_raise("items | length")

    def test_syntax_error_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid Jinja2 expression"):
            compile_expression_or_raise("foo ||| bar")


class TestRenderInputTransform:
    def test_dict_input_attribute_access(self):
        transform = JinjaInputTransform(template="{{ input.foo }}")
        result = render_input_transform(transform, {"foo": 1})
        assert result == "1"

    def test_dict_input_multiple_fields(self):
        transform = JinjaInputTransform(template="{{ input.a }} and {{ input.b }}")
        result = render_input_transform(transform, {"a": "hello", "b": "world"})
        assert result == "hello and world"

    def test_list_input_index_access(self):
        transform = JinjaInputTransform(template="{{ input[0] }}")
        result = render_input_transform(transform, [1, 2, 3])
        assert result == "1"

    def test_list_input_length_filter(self):
        transform = JinjaInputTransform(template="{{ input | length }}")
        result = render_input_transform(transform, [1, 2, 3])
        assert result == "3"

    def test_string_input(self):
        transform = JinjaInputTransform(template="{{ input }}")
        result = render_input_transform(transform, "hello")
        assert result == "hello"

    def test_plaintext_json_dict_auto_parsed(self):
        transform = JinjaInputTransform(template="{{ input.foo }}")
        result = render_input_transform(transform, '{"foo": 1}')
        assert result == "1"

    def test_plaintext_json_list_auto_parsed(self):
        transform = JinjaInputTransform(template="{{ input[0] }}")
        result = render_input_transform(transform, "[10, 20]")
        assert result == "10"

    def test_plaintext_json_scalar_auto_parsed(self):
        transform = JinjaInputTransform(template="{{ input }}")
        result = render_input_transform(transform, "42")
        assert result == "42"

    def test_plaintext_non_json_fallback(self):
        transform = JinjaInputTransform(template="{{ input }}")
        result = render_input_transform(transform, "not json")
        assert result == "not json"

    def test_undefined_error_on_missing_attribute(self):
        transform = JinjaInputTransform(template="{{ input.missing }}")
        with pytest.raises(UndefinedError):
            render_input_transform(transform, {"foo": 1})

    def test_sandbox_violation_dunder_class(self):
        transform = JinjaInputTransform(template="{{ input.__class__ }}")
        with pytest.raises(SecurityError):
            render_input_transform(transform, {})

    def test_sandbox_violation_dunder_bases(self):
        transform = JinjaInputTransform(template="{{ input.__class__.__bases__ }}")
        with pytest.raises(SecurityError):
            render_input_transform(transform, {})

    def test_empty_template_returns_empty_string(self):
        transform = JinjaInputTransform(template="")
        result = render_input_transform(transform, {"foo": 1})
        assert result == ""

    def test_unknown_transform_variant_raises(self):
        class FakeTransform:
            type = "fake"

        with pytest.raises(ValueError, match="Unknown InputTransform variant"):
            render_input_transform(FakeTransform(), "input")  # type: ignore


class TestExtract:
    def test_returns_value(self):
        assert extract("foo", {"foo": 42}) == 42

    def test_returns_string(self):
        assert extract("name", {"name": "alice"}) == "alice"

    def test_returns_list(self):
        assert extract("items", {"items": [1, 2, 3]}) == [1, 2, 3]

    def test_returns_dict(self):
        assert extract("nested", {"nested": {"a": 1}}) == {"a": 1}

    def test_missing_key_returns_undefined(self):
        result = extract("foo", {})
        assert isinstance(result, Undefined)

    def test_explicit_none_returns_none(self):
        result = extract("foo", {"foo": None})
        assert result is None

    def test_materializes_generators(self):
        result = extract(
            "data | map(attribute='x') | list",
            {"data": [{"x": 1}, {"x": 2}]},
        )
        assert result == [1, 2]

    def test_nested_attribute_access(self):
        result = extract("a.b", {"a": {"b": "deep"}})
        assert result == "deep"


class TestTrimAndLstripBlocks:
    def test_trim_blocks_strips_newline_after_block_tag(self):
        template = "{% if True %}\nyes\n{% endif %}"
        transform = JinjaInputTransform(template=template)
        result = render_input_transform(transform, {})
        assert result == "yes\n"

    def test_lstrip_blocks_strips_leading_whitespace(self):
        template = "  {% if True %}\nyes\n  {% endif %}"
        transform = JinjaInputTransform(template=template)
        result = render_input_transform(transform, {})
        assert result == "yes\n"

    def test_combined_trim_and_lstrip(self):
        template = (
            "start\n  {% for item in input %}\n  - {{ item }}\n  {% endfor %}\nend"
        )
        transform = JinjaInputTransform(template=template)
        result = render_input_transform(transform, ["a", "b"])
        assert result == "start\n  - a\n  - b\nend"
