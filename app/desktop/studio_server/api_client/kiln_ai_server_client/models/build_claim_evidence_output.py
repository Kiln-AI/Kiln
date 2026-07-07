from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.claim import Claim
    from ..models.final_judgement import FinalJudgement


T = TypeVar("T", bound="BuildClaimEvidenceOutput")


@_attrs_define
class BuildClaimEvidenceOutput:
    """
    Attributes:
        claims (list[Claim]): ALL claims the data supports, ordered most-to-least important. Do NOT target a count or
            cap the list. May be empty for a trivial single-property eval where the final judgement carries it.
        final_judgement (FinalJudgement):
    """

    claims: list[Claim]
    final_judgement: FinalJudgement
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        claims = []
        for claims_item_data in self.claims:
            claims_item = claims_item_data.to_dict()
            claims.append(claims_item)

        final_judgement = self.final_judgement.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "claims": claims,
                "final_judgement": final_judgement,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.claim import Claim
        from ..models.final_judgement import FinalJudgement

        d = dict(src_dict)
        claims = []
        _claims = d.pop("claims")
        for claims_item_data in _claims:
            claims_item = Claim.from_dict(claims_item_data)

            claims.append(claims_item)

        final_judgement = FinalJudgement.from_dict(d.pop("final_judgement"))

        build_claim_evidence_output = cls(
            claims=claims,
            final_judgement=final_judgement,
        )

        build_claim_evidence_output.additional_properties = d
        return build_claim_evidence_output

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
