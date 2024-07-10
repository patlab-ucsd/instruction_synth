from pydub import AudioSegment
import os
import ffmpeg

def load_audio(filename):
    """
    load the audio file based on its extension
    """
    file_name, file_extension = os.path.splitext(filename)

    if file_extension.lower() == ".mp3":
        audio = AudioSegment.from_mp3(filename)
    elif file_extension.lower() == ".wav":
        audio = AudioSegment.from_wav(filename)
    elif file_extension.lower() == ".ogg":
        audio = AudioSegment.from_ogg(filename)
    else:
        print(f"Unsupported file format: {file_extension}")
        return
    return audio

def get_duration(filename):
    """
    returns the duration of the audio in seconds
    """
    duration_seconds = ffmpeg.probe(filename)['format']['duration']
    return duration_seconds