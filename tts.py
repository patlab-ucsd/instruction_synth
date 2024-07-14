from gtts import gTTS
import os
import ffmpeg
from utils import *
import sys


def synth_sentence(text):
    os.makedirs("./tts", exist_ok=True)
    tts = gTTS(text=text, lang='en',slow=False)
    filename = f"./tts/{'_'.join(text.split())}.mp3"
    tts.save(filename)
    duration_seconds = get_duration(filename)
    print(f"the duration of: {filename}\nis {duration_seconds} seconds")


if __name__ == "__main__":
    """
    Example:
    python3.10 tts.py "standing still"
    """
    text = sys.argv[1]
    synth_sentence(text)