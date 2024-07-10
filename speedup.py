from pydub import AudioSegment
from utils import *
import os

def speedup_audio_file(filename, speedup_factor):
    file_extension = os.path.splitext(filename)[1]
    audio = load_audio(filename)

    audio_speedup = audio.speedup(playback_speed=speedup_factor)

    #save to the same place with new name
    export_filename = f"{os.path.splitext(filename)[0]}_{speedup_factor}{file_extension}"
    audio_speedup.export(export_filename, format=file_extension.lower()[1:])

    print(f"{filename} sped up successfully.")

speedup_audio_file("./music/Yankee_doodle_Saloon_style_120.mp3",1.5)