from kiln_ai.utils.mime_type import guess_mime_type


def test_mov_files():
    assert guess_mime_type("video.mov") == "video/quicktime"
    assert guess_mime_type("my_video.mov") == "video/quicktime"
    assert guess_mime_type("path/to/video.mov") == "video/quicktime"


def test_mp3_files():
    assert guess_mime_type("song.mp3") == "audio/mpeg"
    assert guess_mime_type("music_file.mp3") == "audio/mpeg"
    assert guess_mime_type("audio/track.mp3") == "audio/mpeg"


def test_wav_files():
    assert guess_mime_type("sound.wav") == "audio/wav"
    assert guess_mime_type("audio_file.wav") == "audio/wav"
    assert guess_mime_type("sounds/effect.wav") == "audio/wav"


def test_mp4_files():
    assert guess_mime_type("movie.mp4") == "video/mp4"
    assert guess_mime_type("video_file.mp4") == "video/mp4"
    assert guess_mime_type("videos/clip.mp4") == "video/mp4"


def test_case_insensitive_extensions():
    assert guess_mime_type("video.MOV") == "video/quicktime"
    assert guess_mime_type("song.MP3") == "audio/mpeg"
    assert guess_mime_type("sound.WAV") == "audio/wav"
    assert guess_mime_type("movie.MP4") == "video/mp4"


def test_standard_mimetypes_fallback():
    assert guess_mime_type("document.pdf") == "application/pdf"
    assert guess_mime_type("image.jpg") == "image/jpeg"
    assert guess_mime_type("image.png") == "image/png"
    assert guess_mime_type("text.txt") == "text/plain"
    assert guess_mime_type("data.json") == "application/json"


def test_unknown_extensions():
    assert guess_mime_type("file.invalidmime") is None
    assert guess_mime_type("no_extension") is None


def test_edge_cases():
    # Files with multiple dots
    assert guess_mime_type("video.backup.mov") == "video/quicktime"
    assert guess_mime_type("song.remix.mp3") == "audio/mpeg"

    # Files with dots in the middle
    assert guess_mime_type("my.video.mov") == "video/quicktime"
    assert guess_mime_type("track.1.mp3") == "audio/mpeg"

    # Empty filename
    assert guess_mime_type("") is None

    # Just extension
    assert guess_mime_type(".mov") == "video/quicktime"
    assert guess_mime_type(".mp3") == "audio/mpeg"


def test_priority_order():
    assert guess_mime_type("file.mov.mp3") == "audio/mpeg"
