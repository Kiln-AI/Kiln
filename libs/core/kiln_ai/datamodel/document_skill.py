from typing import TYPE_CHECKING, Union

from pydantic import Field, model_validator

from kiln_ai.datamodel.basemodel import ID_TYPE, FilenameString, KilnParentedModel
from kiln_ai.utils.validation import SkillNameString

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project


class DocumentSkill(KilnParentedModel):
    """Configuration for generating a Skill from project documents.

    A DocumentSkill bridges the document infrastructure (upload, extract, chunk)
    with the skill system (SKILL.md + references). It stores the configuration
    used to generate a Skill, and after pipeline completion, references the
    generated Skill via skill_id.

    DocumentSkills are immutable after successful pipeline completion (skill_id is set).
    """

    name: FilenameString = Field(
        description="Display name for this doc skill configuration.",
    )

    is_archived: bool = Field(
        default=False,
        description="Whether this doc skill is archived. Archived doc skills are hidden from the UI.",
    )

    description: str | None = Field(
        default=None,
        description="User-facing description of this configuration. Not used in prompts.",
    )

    skill_name: SkillNameString = Field(
        description="Name of the generated skill (kebab-case).",
    )

    skill_content_header: str = Field(
        min_length=1,
        max_length=16384,
        description="User-authored text placed at the top of the SKILL.md body, describing what the documents contain and when to use them.",
    )

    extractor_config_id: ID_TYPE = Field(
        description="ID of the extractor config used for document extraction.",
    )

    chunker_config_id: ID_TYPE = Field(
        description="ID of the chunker config used for chunking.",
    )

    document_tags: list[str] | None = Field(
        default=None,
        description="Document tag filter. None means all project documents are included.",
    )

    skill_id: ID_TYPE | None = Field(
        default=None,
        description="ID of the generated Skill. None before pipeline completes.",
    )

    strip_file_extensions: bool = Field(
        default=True,
        description="Whether to strip file extensions from document names in skill output.",
    )

    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore

    @model_validator(mode="after")
    def validate_document_skill(self):
        if self.document_tags is not None:
            if len(self.document_tags) == 0:
                raise ValueError("Document tags cannot be an empty list.")
            for tag in self.document_tags:
                if not tag:
                    raise ValueError("Document tags cannot be empty.")
                if " " in tag:
                    raise ValueError(
                        "Document tags cannot contain spaces. Try underscores."
                    )

        if self.skill_content_header.strip() == "":
            raise ValueError("Skill content header cannot be empty.")

        return self
