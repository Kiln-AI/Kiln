from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.claim_type import ClaimType

if TYPE_CHECKING:
    from ..models.citation import Citation


T = TypeVar("T", bound="Claim")


@_attrs_define
class Claim:
    """
    Attributes:
        claim (str): Atomic: a SINGLE inclusion, exclusion, or property. Inclusions affirmative; exclusions negative.
        claim_type (ClaimType):
        evidence (str): ONE sentence. States the decisive fact with [n] markers; fold any real counter-point into a
            single 'though …' clause. Do NOT quote long spans.
        citations (list[Citation]): Resolves the inline [n] markers. Each is a start+end anchor; the parser highlights
            the span from `from` to `to`.
    """

    claim: str
    claim_type: ClaimType
    evidence: str
    citations: list[Citation]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        claim = self.claim

        claim_type = self.claim_type.value

        evidence = self.evidence

        citations = []
        for citations_item_data in self.citations:
            citations_item = citations_item_data.to_dict()
            citations.append(citations_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "claim": claim,
                "claim_type": claim_type,
                "evidence": evidence,
                "citations": citations,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.citation import Citation

        d = dict(src_dict)
        claim = d.pop("claim")

        claim_type = ClaimType(d.pop("claim_type"))

        evidence = d.pop("evidence")

        citations = []
        _citations = d.pop("citations")
        for citations_item_data in _citations:
            citations_item = Citation.from_dict(citations_item_data)

            citations.append(citations_item)

        claim = cls(
            claim=claim,
            claim_type=claim_type,
            evidence=evidence,
            citations=citations,
        )

        claim.additional_properties = d
        return claim

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
