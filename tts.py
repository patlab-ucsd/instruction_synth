from gtts import gTTS
import os
import ffmpeg
from utils import *
import sys
from pydub import AudioSegment

def synth_sentence(text):
    os.makedirs("./tts", exist_ok=True)
    tts = gTTS(text=text, lang='en',slow=False)
    filename = f"./tts/{'_'.join(text.split())}.mp3"
    tts.save(filename)
    duration_seconds = get_duration(filename)
    print(f"the duration of: {filename}\nis {duration_seconds} seconds")

def synth_rhythmic_speech(text, bpm = 100):
    """
    create rhythmic utterance given the text containing more than one words
    """
    os.makedirs("./tts", exist_ok=True)
    words = text.split()
    # generate individual sounds
    audios = []
    for word in words:
        tts = gTTS(text=word, lang='en',slow=False)
        tts.save(f"./tts/{word}.mp3")
        audio = AudioSegment.from_mp3(f"./tts/{word}.mp3")
        audio = trim_silence(audio)
        audios.append(audio)
    num_of_beats = len(words)
    rhythmic_speech_duration = 60*1000.0/bpm*num_of_beats
    # create empty sound
    empty_audio = AudioSegment.silent(duration=rhythmic_speech_duration)
    # overlay
    for i, audio in enumerate(audios):
        overlay_position_ms = 60*1000.0/bpm * i
        empty_audio = empty_audio.overlay(audio, position=overlay_position_ms)
    underscored_name = "_".join(words)
    empty_audio.export(f"./tts/{underscored_name}_rhythmic_{bpm}.mp3", format="mp3")

if __name__ == "__main__":
    """
    Example:
    python3.10 tts.py "standing still"
    """
    text = sys.argv[1]
    synth_sentence(text)