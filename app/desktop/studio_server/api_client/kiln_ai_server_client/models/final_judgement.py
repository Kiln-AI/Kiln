from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.expected_result import ExpectedResult

if TYPE_CHECKING:
    from ..models.citation import Citation


T = TypeVar("T", bound="FinalJudgement")


@_attrs_define
class FinalJudgement:
    """
    Attributes:
        claim (str): The substantive one-line reason only — what the agent did, e.g. 'The agent invented an order-
            cancellation deadline and repeated it after the user questioned it.' NEVER restate or reference the verdict — no
            'Eval passes', no 'per the judge's verdict'; direction travels exclusively in expected_result. State the
            decisive fact even when it repeats the top claim. Empty string ONLY for a trivial eval with nothing concrete to
            report.
        evidence (str): ONE sentence. States the decisive fact with [n] markers; fold any real counter-point into a
            single 'though …' clause. Do NOT quote long spans.
        expected_result (ExpectedResult):
        citations (list[Citation]): Resolves the inline [n] markers. Each is a start+end anchor; the parser highlights
            the span from `from` to `to`. Empty when the trace offers nothing to anchor.
    """

    claim: str
    evidence: str
    expected_result: ExpectedResult
    citations: list[Citation]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        claim = self.claim

        evidence = self.evidence

        expected_result = self.expected_result.value

        citations = []
        for citations_item_data in self.citations:
            citations_item = citations_item_data.to_dict()
            citations.append(citations_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "claim": claim,
                "evidence": evidence,
                "expected_result": expected_result,
                "citations": citations,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.citation import Citation

        d = dict(src_dict)
        claim = d.pop("claim")

        evidence = d.pop("evidence")

        expected_result = ExpectedResult(d.pop("expected_result"))

        citations = []
        _citations = d.pop("citations")
        for citations_item_data in _citations:
            citations_item = Citation.from_dict(citations_item_data)

            citations.append(citations_item)

        final_judgement = cls(
            claim=claim,
            evidence=evidence,
            expected_result=expected_result,
            citations=citations,
        )

        final_judgement.additional_properties = d
        return final_judgement

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
