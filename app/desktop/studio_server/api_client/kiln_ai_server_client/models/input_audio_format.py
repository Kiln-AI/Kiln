from enum import Enum


class InputAudioFormat(str, Enum):
    MP3 = "mp3"
    WAV = "wav"

    def __str__(self) -> str:
        return str(self.value)
