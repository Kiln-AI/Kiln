export function default_extractor_document_prompts(output_format: string) {
  return `Transcribe the document into ${output_format}.

If the document contains images and figures, describe them in the output. For example, if the
document contains an image, describe it in the output. If the document contains a table, format it 
appropriately and add a sentence describing it as a whole.

Format the output as valid ${output_format}.

Do NOT include any prefatory text such as 'Here is the transcription of the document:'.  
`
}

export function default_extractor_image_prompts(output_format: string) {
  return `Describe the image in ${output_format}.

If the image contains text, transcribe it into ${output_format}.

Do NOT include any prefatory text such as 'Here is the description of the image:'.
`
}

export function default_extractor_video_prompts(output_format: string) {
  return `Describe what happens in the video in ${output_format}.

Take into account the audio as well as the visual content. Your transcription must chronologically
describe the events in the video and transcribe any speech.

Do NOT include any prefatory text such as 'Here is the transcription of the video:'.
`
}

export function default_extractor_audio_prompts(output_format: string) {
  return `Transcribe the document into ${output_format}.

If the document contains images and figures, describe them in the output. For example, if the
document contains an image, describe it in the output. If the document contains a table, format it 
appropriately and add a sentence describing it as a whole.

Format the output as valid ${output_format}.

Do NOT include any prefatory text such as 'Here is the transcription of the document:'.
`
}
