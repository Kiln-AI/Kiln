---
status: draft
---

# Component: Pipeline Runner

## File Locations

- `app/desktop/studio_server/doc_skill_pipeline.py` — Workflow runner and progress model
- `app/desktop/studio_server/doc_skill_skill_builder.py` — Skill building logic (step 3)

## DocSkillProgress Model

```python
class DocSkillProgress(BaseModel):
    """Progress for a DocSkill pipeline run. Simpler than RagProgress — no embedding/indexing."""
    total_document_count: int = 0
    total_document_extracted_count: int = 0
    total_document_extracted_error_count: int = 0
    total_document_chunked_count: int = 0
    total_document_chunked_error_count: int = 0
    skill_created: bool = False
    logs: list[LogMessage] | None = None
```

Uses existing `LogMessage` from `kiln_ai.adapters.rag.progress`.

## DocSkillWorkflowRunner

Orchestrates the three-step pipeline. Follows `RagWorkflowRunner` patterns but is simpler (no embedding/indexing steps).

### Configuration

```python
@dataclass
class DocSkillWorkflowRunnerConfig:
    doc_skill: DocumentSkill
    project: Project
    extractor_config: ExtractorConfig
    chunker_config: ChunkerConfig
```

### Class Structure

```python
class DocSkillWorkflowRunner:
    def __init__(self, config: DocSkillWorkflowRunnerConfig, initial_progress: DocSkillProgress):
        self.config = config
        self.progress = initial_progress
        self._lock_key = f"doc_skill:run:{config.doc_skill.id}"

    async def run(self) -> AsyncGenerator[DocSkillProgress, None]:
        # 1. Yield initial progress
        yield self.progress

        # 2. Acquire pipeline lock
        async with shared_async_lock_manager.acquire(self._lock_key, timeout=LOCK_TIMEOUT_SECONDS):

            # 3. Pre-validate: check for documents, check max parts won't be exceeded
            documents = self._get_filtered_documents()
            if not documents:
                raise ValueError("No documents found with the selected tags.")

            # 4. Run extraction step (reuse RagExtractionStepRunner)
            extraction_runner = RagExtractionStepRunner(
                project=self.config.project,
                extractor_config=self.config.extractor_config,
                rag_config=None,  # No RagConfig — use doc_skill.document_tags directly
                # Need to pass tags for filtering — see Design Note below
            )
            async for step_progress in extraction_runner.run():
                self._update_extraction_progress(step_progress)
                yield self.progress

            # 5. Run chunking step (reuse RagChunkingStepRunner)
            chunking_runner = RagChunkingStepRunner(
                project=self.config.project,
                extractor_config=self.config.extractor_config,
                chunker_config=self.config.chunker_config,
            )
            async for step_progress in chunking_runner.run():
                self._update_chunking_progress(step_progress)
                yield self.progress

            # 6. Set total_document_count from filtered docs
            self.progress.total_document_count = len(documents)

            # 7. Build skill (new step)
            skill_builder = SkillBuilder(self.config, documents)
            skill_id = await skill_builder.build()  # Atomic with rollback

            # Save DocumentSkill first (resumable if subsequent save fails)
            self.config.doc_skill.skill_id = skill_id
            self.config.doc_skill.save_to_file()

            self.progress.skill_created = True
            yield self.progress
```

### Design Note: Tag Filtering for Extraction/Chunking

`RagExtractionStepRunner` currently accepts an optional `rag_config` to read tags from. For Doc Skills, we need to pass tags without a `RagConfig`. Two approaches:

**Option A (preferred):** Add an optional `tags: list[str] | None` parameter to the step runner constructors. If provided, use it for filtering. If `rag_config` is also provided, `rag_config.tags` takes precedence. Minimal change to existing code.

**Option B:** Create a thin adapter that exposes `document_tags` as if it were `rag_config.tags`. More hacky.

The architecture recommends **Option A** — a small, clean change to the existing step runners.

### Progress Update Methods

```python
def _update_extraction_progress(self, step_progress: RagStepRunnerProgress):
    self.progress.total_document_extracted_count = max(
        self.progress.total_document_extracted_count,
        step_progress.success_count,
    )
    self.progress.total_document_extracted_error_count = step_progress.error_count
    self.progress.logs = step_progress.logs

def _update_chunking_progress(self, step_progress: RagStepRunnerProgress):
    self.progress.total_document_chunked_count = max(
        self.progress.total_document_chunked_count,
        step_progress.success_count,
    )
    self.progress.total_document_chunked_error_count = step_progress.error_count
    self.progress.logs = step_progress.logs
```

### Document Filtering

```python
def _get_filtered_documents(self) -> list[Document]:
    """Get documents filtered by document_tags. Returns all if tags is None."""
    all_docs = self.config.project.documents(readonly=True)
    tags = self.config.doc_skill.document_tags
    if tags is None:
        return all_docs
    return [d for d in all_docs if d.tags and any(t in tags for t in d.tags)]
```

## SkillBuilder

Handles step 3 of the pipeline: building the Skill from extracted/chunked documents.

### Class Structure

```python
class SkillBuilder:
    def __init__(self, config: DocSkillWorkflowRunnerConfig, documents: list[Document]):
        self.config = config
        self.project = config.project
        self.doc_skill = config.doc_skill
        self.documents = documents  # Pre-filtered documents from the runner

    async def build(self) -> ID_TYPE:
        """Build the skill atomically. Returns skill_id. Raises on failure after rollback."""
        # 1. Collect documents and their chunks
        doc_chunks = await self._collect_document_chunks()

        # 2. Validate max parts
        for doc_name, chunks in doc_chunks.items():
            if len(chunks) > 999:
                raise ValueError(f"Document '{doc_name}' has {len(chunks)} parts, exceeding the 999 limit.")

        # 3. Determine sanitized document names
        doc_names = self._resolve_document_names(doc_chunks)

        # 4. Build SKILL.md body
        skill_md_body = self._build_skill_md(doc_names, doc_chunks)

        # 5. Generate auto-description for Skill.description
        auto_description = self._generate_skill_description(len(doc_chunks))

        # 6. Create and save Skill + reference files atomically
        skill = Skill(
            name=self.doc_skill.skill_name,
            description=auto_description,
        )
        skill.parent = self.project

        try:
            # Save skill model + SKILL.md
            skill.save_to_file()
            skill.save_skill_md(skill_md_body)

            # Write reference files
            self._write_reference_files(skill, doc_names, doc_chunks)

            return skill.id

        except Exception:
            # Rollback: delete entire skill folder
            self._rollback_skill(skill)
            raise
```

### Name Sanitization

```python
def _sanitize_name(self, name: str) -> str:
    """Sanitize a document name for filesystem safety.
    - Lowercase
    - Replace non-alphanumeric chars (except hyphens) with hyphens
    - Collapse consecutive hyphens
    - Strip leading/trailing hyphens
    """
    import re
    sanitized = name.lower()
    sanitized = re.sub(r'[^a-z0-9-]', '-', sanitized)
    sanitized = re.sub(r'-+', '-', sanitized)
    sanitized = sanitized.strip('-')
    return sanitized or 'unnamed'

def _strip_all_extensions(self, name: str) -> str:
    """Strip all file extensions: 'archive.tar.gz' -> 'archive'."""
    # Find first dot that's not at position 0 (hidden files)
    dot_idx = name.find('.', 1) if name.startswith('.') else name.find('.')
    if dot_idx > 0:
        return name[:dot_idx]
    return name

def _resolve_document_names(self, doc_chunks: dict) -> dict[str, str]:
    """Map document ID -> sanitized filesystem name, handling collisions."""
    raw_names: dict[str, str] = {}
    for doc_id, (doc, _chunks) in doc_chunks.items():
        name = doc.name_override or doc.name
        if self.doc_skill.strip_file_extensions:
            name = self._strip_all_extensions(name)
        raw_names[doc_id] = self._sanitize_name(name)

    # Handle collisions: append -2, -3, etc.
    # Sort by sanitized name for consistent ordering within a single run.
    # Cross-run determinism is not required — DocumentSkills are immutable,
    # and cloning creates a new Skill with independent naming.
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
```

### SKILL.md Generation

```python
def _build_skill_md(self, doc_names: dict[str, str], doc_chunks: dict) -> str:
    """Build the SKILL.md body content."""
    lines = []

    # 1. Header
    lines.append(f"# Skill: {self.doc_skill.skill_name}")
    lines.append("")

    # 2. Content header
    lines.append(self.doc_skill.skill_content_header)
    lines.append("")

    # 3. Instructions
    lines.append("## How to Use This Skill")
    lines.append("")
    lines.append("This skill contains reference documents split into numbered parts. "
                 "To read a document, load its parts using the skill tool's resource parameter:")
    lines.append("")
    ext = self._get_file_extension()
    lines.append(f'skill(name="{self.doc_skill.skill_name}", '
                 f'resource="references/[doc-name]/part001.{ext}")')
    lines.append("")
    lines.append("Parts are 1-indexed and zero-padded to 3 digits (part001, part002, ... part999). "
                 "Start with part001. Each part ends with a pointer to the next part, "
                 'or `<End of Document>` for the final part.')
    lines.append("")

    # 4. Document index
    lines.append("## Document Index")
    lines.append("")
    lines.append("|Document|Part Count|Location|")
    lines.append("|-|-|-|")

    # Sort alphabetically by sanitized name
    sorted_entries = sorted(
        [(doc_id, doc_names[doc_id]) for doc_id in doc_chunks],
        key=lambda x: x[1],
    )
    for doc_id, sanitized_name in sorted_entries:
        doc, chunks = doc_chunks[doc_id]
        display_name = doc.name_override or doc.name
        if self.doc_skill.strip_file_extensions:
            display_name = self._strip_all_extensions(display_name)
        part_count = len(chunks)
        ext = self._get_file_extension()
        lines.append(f"|{display_name}|{part_count}|"
                     f"`references/{sanitized_name}/part[NNN].{ext}`|")

    return "\n".join(lines)

def _get_file_extension(self) -> str:
    """Determine file extension based on extractor output format enum."""
    if self.config.extractor_config.output_format == OutputFormat.MARKDOWN:
        return "md"
    return "txt"
```

### Reference File Writing

```python
def _write_reference_files(self, skill: Skill, doc_names: dict[str, str], doc_chunks: dict):
    """Write all reference files for all documents."""
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
```

### Auto-Generated Skill Description

```python
def _generate_skill_description(self, doc_count: int) -> str:
    """Generate Skill.description for tool discovery. Must stay under 1024 chars."""
    tags = self.doc_skill.document_tags
    if tags:
        tag_str = ", ".join(tags)
        desc = f"Document skill generated by Kiln from documents tagged {tag_str}"
        if len(desc) > 1024:
            desc = f"Document skill generated by Kiln from documents tagged ({len(tags)} document tags)"
        return desc
    return f"Document skill generated by Kiln from {doc_count} documents"
```

### Rollback

```python
def _rollback_skill(self, skill: Skill):
    """Delete the entire skill folder on failure."""
    if skill.path and skill.path.parent.exists():
        import shutil
        shutil.rmtree(skill.path.parent)
```

### Collecting Document Chunks

```python
async def _collect_document_chunks(self) -> dict[str, tuple[Document, list[str]]]:
    """Collect all documents and their chunk texts.
    Returns: {doc_id: (Document, [chunk_text_1, chunk_text_2, ...])}
    Only includes documents that have extractions and chunks for the configured configs.
    """
    result = {}

    for doc in self.documents:
        # Find extraction for this extractor config
        extraction = None
        for ext in doc.extractions():
            if ext.extractor_config_id == self.config.extractor_config.id:
                extraction = ext
                break  # Use first match (dedup handled by step runner)

        if extraction is None:
            continue  # Skip docs without extraction (may have been skipped/errored)

        # Find chunked document for this chunker config
        chunked_doc = None
        for cd in extraction.chunked_documents():
            if cd.chunker_config_id == self.config.chunker_config.id:
                chunked_doc = cd
                break

        if chunked_doc is None:
            continue

        # Load chunk texts
        chunk_texts = await chunked_doc.load_chunks_text()
        if not chunk_texts:
            continue  # Skip empty

        result[doc.id] = (doc, chunk_texts)

    return result
```

## Tests

File: `app/desktop/studio_server/test_doc_skill_pipeline.py`
File: `app/desktop/studio_server/test_doc_skill_skill_builder.py`

### Pipeline Tests
- Full pipeline run with fixture documents (extraction + chunking + skill creation)
- Pipeline with tag filtering
- Pipeline fails when no documents match tags
- Pipeline fails when all extractions are empty
- Concurrent run locking (second call waits or times out)
- Progress updates during each step

### Skill Builder Tests
- Name sanitization: special characters, unicode, empty result
- Extension stripping: single ext, double ext, no ext, hidden files (`.gitignore`)
- Name collision handling: 2 docs with same name, 3+ collisions
- SKILL.md generation: correct format, sorted entries, correct part counts
- Reference file writing: correct paths, continuation footers, end-of-document marker
- Max parts validation: exactly 999 (ok), 1000 (error)
- Rollback: verify skill folder deleted on failure
- Auto-description: with tags, without tags
- Empty chunk text handling: skipped correctly
