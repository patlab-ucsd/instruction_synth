from pydub import AudioSegment
import os
import ffmpeg
import mido

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

def ticks_to_seconds(ticks, ticks_per_beat, microseconds_per_beat):
    # Calculate seconds from ticks based on tempo
    return ticks / ticks_per_beat * microseconds_per_beat / 1000000

def get_time_change_times_in_seconds(mid):
    ticks_per_beat = mid.ticks_per_beat
    measure_number = 1
    measure_start_times = {}

    current_microseconds_per_beat = 500000  # Default tempo (microseconds per beat), often 120 BPM

    # check for time signature change
    for track in mid.tracks:
        current_time = 0
        for msg in track:
            current_time += msg.time
            if msg.type == 'set_tempo':
                # Update tempo if there's a tempo change
                current_microseconds_per_beat = msg.tempo

            if msg.type == 'time_signature':
                # Calculate the duration of one measure in ticks
                beats_per_measure = msg.numerator
                ticks_per_measure = beats_per_measure * ticks_per_beat * 4 // msg.denominator
                # Convert measure start time from ticks to seconds
                measure_start_time_sec = ticks_to_seconds(current_time, ticks_per_beat, current_microseconds_per_beat)
                measure_start_times[measure_number] = measure_start_time_sec
                measure_number += 1

    return measure_start_times

mid = mido.MidiFile("./midi/Yankee_doodle_Saloon_style_120.mid")
print(get_time_change_times_in_seconds(mid))