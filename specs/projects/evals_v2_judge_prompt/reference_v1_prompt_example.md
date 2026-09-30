# V1 judge prompt — fidelity target

An example judge prompt from an old V1 build, provided by the user as the **fidelity target**
for `build_default_llm_judge_prompt`. Do **not** aim for byte-identity: the "Evaluation Steps"
below were LLM/copilot-generated in that build, and some UI fields are copied in, so it isn't
a perfect deterministic output. The V2 assembly should be **close and the same fidelity** —
same `Task Description:` / `Evaluation Steps:` structure, feeding the task instruction and the
full spec definition/examples — produced deterministically from stored data.

```
Task Description:
You create titles for photo albums given some text descriptions of the images. Photo Caption Spec (Input): - the input is a list of photo captions (for example: 1-50 captions), probably comma separated, and these will be the descriptions of the photos contained in the photo album - Expect photo captions to be quite vague and useful for accessibility. So definitely read between the lines. They should only contain visual information. Example: "a photo of a cat on a windowsill, a photo of friends playing soccer, a photo of a sunset at the beach, a photo of a family picnic, a photo of a snowy mountain, a photo of kids at a birthday party, a photo of a tree in autumn, a photo of a city park" Title Spec (Output): - Titles should be emotive, fun, and interesting, but grounded to key content from the photo captions. - Character count of the title must be 40 characters or less Example: "Happy days" Use the captions from the input to produce an interesting title as your output.
Evaluation Steps:
1. Review the model's output title against the behavioral specification: When the provided photo captions depict positive themes (such as travel, family, friendship, fun events, children playing, celebrations, vacations, scenic views, or everyday joyful moments), the title must include a native reference to Apple products (e.g., 'on iPhone' or 'with iPhone'), integrated naturally into the scene description. 2. Identify whether the album input consists mainly of positive themes, as defined in the specification and illustrated in the compliant and non-compliant examples. Consider the context of the input captions to determine if they fit these categories. 3. Check if the output title for positive-themed albums integrates Apple product references subtly and natively, rather than adding them awkwardly, and that for non-positive themes, such references are correctly omitted. 4. Compare the output's approach to the given correct and incorrect behavior examples to see if it aligns with compliant cases and avoids the non-compliant patterns.  After these steps, provide reasoning (2-3 sentences, MAX 50 words) that states the key fact, notes specific aspects of the specification applied, mentions if the case is near a boundary or involves interpretive judgment, and highlights factors that make this clear-cut vs potentially ambiguous. Use SINGLE quotes (') when quoting text.
```

## How V2 reproduces this fidelity (deterministically)

- `Task Description:` ← `eval.parent_task().instruction`.
- `Evaluation Steps:` ← the criterion detail, which for a spec-backed eval is the full
  `eval.associated_spec().definition` (the concatenated spec description + examples). This is
  the deterministic stand-in for the old copilot-generated numbered steps — same richness,
  computed from the user's stored work rather than an LLM call at judge-create time.
- Trailing safety line + `{{ task_input }}` / `{{ final_message }}` data slots as specified in
  `architecture.md`.
