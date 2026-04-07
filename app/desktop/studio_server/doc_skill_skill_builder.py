from __future__ import annotations

import re
import shutil
from typing import TYPE_CHECKING

from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.chunk import ChunkedDocument
from kiln_ai.datamodel.extraction import Document, OutputFormat
from kiln_ai.datamodel.skill import Skill

if TYPE_CHECKING:
    from .doc_skill_pipeline import DocSkillWorkflowRunnerConfig


class SkillBuilder:
    def __init__(
        self,
        config: DocSkillWorkflowRunnerConfig,
        documents: list[Document],
    ):
        self.config = config
        self.project = config.project
        self.doc_skill = config.doc_skill
        self.documents = documents

    async def build(self) -> ID_TYPE:
        doc_chunks = await self._collect_document_chunks()

        if not doc_chunks:
            raise ValueError(
                "No documents with extracted and chunked content were found."
            )

        for doc_id, (doc, chunks) in doc_chunks.items():
            if len(chunks) > 999:
                display_name = doc.name_override or doc.name
                raise ValueError(
                    f"Document '{display_name}' has {len(chunks)} parts, exceeding the 999 limit."
                )

        doc_names = self._resolve_document_names(doc_chunks)
        skill_md_body = self._build_skill_md(doc_names, doc_chunks)
        description = self.doc_skill.description or self._generate_skill_description()

        skill = Skill(
            name=self.doc_skill.skill_name,
            description=description,
        )
        skill.parent = self.project

        try:
            skill.save_to_file()
            skill.save_skill_md(skill_md_body)
            self._write_reference_files(skill, doc_names, doc_chunks)
            return skill.id
        except Exception:
            self._rollback_skill(skill)
            raise

    async def _collect_document_chunks(
        self,
    ) -> dict[str, tuple[Document, list[str]]]:
        result: dict[str, tuple[Document, list[str]]] = {}

        for doc in self.documents:
            extraction = None
            for ext in doc.extractions():
                if ext.extractor_config_id == self.config.extractor_config.id:
                    extraction = ext
                    break

            if extraction is None:
                continue

            chunked_doc: ChunkedDocument | None = None
            for cd in extraction.chunked_documents():
                if cd.chunker_config_id == self.config.chunker_config.id:
                    chunked_doc = cd
                    break

            if chunked_doc is None:
                continue

            chunk_texts = await chunked_doc.load_chunks_text()
            if not chunk_texts:
                continue

            doc_id = str(doc.id)
            result[doc_id] = (doc, chunk_texts)

        return result

    def _sanitize_name(self, name: str) -> str:
        sanitized = name.lower()
        sanitized = re.sub(r"[^a-z0-9-]", "-", sanitized)
        sanitized = re.sub(r"-+", "-", sanitized)
        sanitized = sanitized.strip("-")
        return sanitized or "unnamed"

    def _strip_file_extension(self, name: str) -> str:
        dot_idx = name.rfind(".")
        if dot_idx <= 0:
            return name
        ext = name[dot_idx + 1 :]
        if 2 <= len(ext) <= 4 and ext.isalnum():
            return name[:dot_idx]
        return name

    def _resolve_document_names(
        self, doc_chunks: dict[str, tuple[Document, list[str]]]
    ) -> dict[str, str]:
        raw_names: dict[str, str] = {}
        for doc_id, (doc, _chunks) in doc_chunks.items():
            name = doc.name_override or doc.name
            if self.doc_skill.strip_file_extensions:
                name = self._strip_file_extension(name)
            raw_names[doc_id] = self._sanitize_name(name)

        seen: dict[str, int] = {}
        result: dict[str, str] = {}
        for doc_id, name in sorted(raw_names.items(), key=lambda x: x[1]):
            if name in seen:
                seen[name] += 1
                result[doc_id] = f"{name}-{seen[name]}"
            else:
                seen[name] = 1
                result[doc_id] = name
        return result

    def _get_file_extension(self) -> str:
        if self.config.extractor_config.output_format == OutputFormat.MARKDOWN:
            return "md"
        return "txt"

    def _build_skill_md(
        self,
        doc_names: dict[str, str],
        doc_chunks: dict[str, tuple[Document, list[str]]],
    ) -> str:
        lines: list[str] = []

        lines.append(f"# Skill: {self.doc_skill.skill_name}")
        lines.append("")
        lines.append(self.doc_skill.skill_content_header)
        lines.append("")

        ext = self._get_file_extension()
        lines.append("## How to Use This Skill")
        lines.append("")
        lines.append(
            "This skill contains reference documents split into numbered parts. "
            "To read a document, load its parts using the skill tool's resource parameter:"
        )
        lines.append("")
        lines.append(
            f'skill(name="{self.doc_skill.skill_name}", '
            f'resource="references/[doc-name]/part001.{ext}")'
        )
        lines.append("")
        lines.append(
            "Parts are 1-indexed and zero-padded to 3 digits (part001, part002, ... part999). "
            "Start with part001. Each part ends with a pointer to the next part, "
            "or `<End of Document>` for the final part."
        )
        lines.append("")

        lines.append("## Document Index")
        lines.append("")
        lines.append("|Document|Part Count|Location|")
        lines.append("|-|-|-|")

        sorted_entries = sorted(
            [(doc_id, doc_names[doc_id]) for doc_id in doc_chunks],
            key=lambda x: x[1],
        )
        for doc_id, sanitized_name in sorted_entries:
            doc, chunks = doc_chunks[doc_id]
            display_name = doc.name_override or doc.name
            if self.doc_skill.strip_file_extensions:
                display_name = self._strip_file_extension(display_name)
            part_count = len(chunks)
            lines.append(
                f"|{display_name}|{part_count}|"
                f"`references/{sanitized_name}/part[NNN].{ext}`|"
            )

        return "\n".join(lines)

    def _write_reference_files(
        self,
        skill: Skill,
        doc_names: dict[str, str],
        doc_chunks: dict[str, tuple[Document, list[str]]],
    ) -> None:
        refs_dir = skill.references_dir()
        ext = self._get_file_extension()

        for doc_id, (doc, chunks) in doc_chunks.items():
            sanitized_name = doc_names[doc_id]
            doc_dir = refs_dir / sanitized_name
            doc_dir.mkdir(parents=True, exist_ok=True)

            for i, chunk_text in enumerate(chunks):
                part_num = i + 1
                filename = f"part{part_num:03d}.{ext}"
                filepath = doc_dir / filename

                content = chunk_text
                if part_num < len(chunks):
                    next_filename = f"part{part_num + 1:03d}.{ext}"
                    content += f"\n\n<< Document continues in references/{sanitized_name}/{next_filename} >>"
                else:
                    content += "\n\n<End of Document>"

                filepath.write_text(content, encoding="utf-8")

    def _generate_skill_description(self) -> str:
        tags = self.doc_skill.document_tags
        if tags:
            tag_list = ", ".join(f"'{t}'" for t in tags)
            desc = f"A skill providing access to a set of documents tagged {tag_list}"
            if len(desc) > 1024:
                desc = f"A skill providing access to a set of documents tagged ({len(tags)} document tags)"
            return desc
        return "A skill providing access to a set of documents."

    def _rollback_skill(self, skill: Skill) -> None:
        if skill.path and skill.path.parent.exists():
            shutil.rmtree(skill.path.parent)
