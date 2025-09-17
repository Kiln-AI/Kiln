export function default_extractor_document_prompts(output_format: string) {
  return `Transcribe the document into ${output_format}.

- Accurately transcribe all text content.
- If the document contains images or figures, describe them in the output.
- If the document contains tables, reproduce them in the output using the correct format, and also add a brief descriptive sentence summarizing the table as a whole.
- Preserve the structure and order of the document.
- Format the output as valid ${output_format}.
- Do NOT include any prefatory or explanatory text outside of the transcription itself.
`
}

export function default_extractor_image_prompts(output_format: string) {
  return `Describe the image in ${output_format}.

- Provide a clear description of the visual content.
- If the image contains text, transcribe it exactly.
- Mention notable visual details (e.g., people, objects, actions, setting, style, colors) when relevant.
- Do NOT include any prefatory or explanatory text outside of the description itself.
`
}

export function default_extractor_video_prompts(output_format: string) {
  return `Describe the video in ${output_format}.

- Provide a chronological description of what happens in the video, covering both visual and audio content.
- Accurately transcribe all spoken words.
- When the audio does not contain speech (e.g., music, laughter, background sounds, silence, noise), describe these sounds in brackets.
- When relevant, describe notable visual details (e.g., actions, gestures, scene changes, on-screen text).
- Do NOT include any prefatory or explanatory text outside of the transcription itself.
`
}

export function default_extractor_audio_prompts(output_format: string) {
  return `Transcribe the audio into ${output_format}.

- Accurately transcribe all spoken words.
- When the audio does not contain speech (e.g., music, laughter, background sounds, silence, noise), describe these sounds in brackets.
- Maintain the natural order of events in the audio.
- Do NOT include any prefatory or explanatory text outside of the transcription itself.
`
}
