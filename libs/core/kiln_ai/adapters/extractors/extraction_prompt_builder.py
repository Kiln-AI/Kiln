from kiln_ai.datamodel.extraction import Kind, OutputFormat


class ExtractionPromptBuilder:
    @classmethod
    def prompt_document(cls, output_format: OutputFormat) -> str:
        return f"""Transcribe the document into {output_format.value}.

If the document contains images and figures, describe them in the output. For example, if the
document contains an image, describe it in the output. If the document contains a table, format it 
appropriately and add a sentence describing it as a whole.

Format the output as valid {output_format.value}.

Do NOT include any prefatory text such as 'Here is the transcription of the document:'.
"""

    @classmethod
    def prompt_image(cls, output_format: OutputFormat) -> str:
        return f"""Describe the image in {output_format.value}.

If the image contains text, transcribe it into {output_format.value}.

Do NOT include any prefatory text such as 'Here is the description of the image:'.
"""

    @classmethod
    def prompt_video(cls, output_format: OutputFormat) -> str:
        return f"""Describe what happens in the video in {output_format.value}.

Take into account the audio as well as the visual content. Your transcription must chronologically
describe the events in the video and transcribe any speech.

Do NOT include any prefatory text such as 'Here is the transcription of the video:'.
"""

    @classmethod
    def prompt_audio(cls, output_format: OutputFormat) -> str:
        return f"""Transcribe the audio into {output_format.value}.
If the audio contains speech, transcribe it into {output_format.value}.

Do NOT include any prefatory text such as 'Here is the transcription of the audio:'.
"""

    @classmethod
    def prompt_for_kind(cls, kind: Kind, output_format: OutputFormat) -> str:
        match kind:
            case Kind.DOCUMENT:
                return cls.prompt_document(output_format)
            case Kind.IMAGE:
                return cls.prompt_image(output_format)
            case Kind.VIDEO:
                return cls.prompt_video(output_format)
            case Kind.AUDIO:
                return cls.prompt_audio(output_format)
            case _:
                raise ValueError(f"Cannot build prompt for unknown kind: '{kind}'")
