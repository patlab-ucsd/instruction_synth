from pydub import AudioSegment
from utils import *
import mido

def overlay_countdown(music, start_measure=None, bpm=None, count_from=None, offset_in_ms=0, midifile=None):
    """
    add countdown starting from specified measure
    """
    mid = mido.MidiFile(midifile)

    initial_overlay_position_ms = get_measure_starts(mid)[start_measure][1]*1000
    interval = 60000/bpm
    for i in range(count_from, 0, -1):
        overlay_position_ms = initial_overlay_position_ms + interval*(count_from-i)+offset_in_ms
        print(f"overlay {i} at:",overlay_position_ms/1000)
        voice = AudioSegment.from_mp3(f"./tts/{i}_trimmed.mp3")
        music = music.overlay(voice, position=overlay_position_ms)
    return music

def overlay_at_measure(music, voice, measure_numbers=None,midifile=None,offset_in_ms=0):
    mid = mido.MidiFile(midifile)
    for measure_number in measure_numbers:
        overlay_position_ms = get_measure_starts(mid)[measure_number][1]*1000+offset_in_ms
        music = music.overlay(voice, position=overlay_position_ms)
    return music