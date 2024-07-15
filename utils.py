from pydub import AudioSegment
import os
import ffmpeg
import mido
from pydub import AudioSegment
from pydub.silence import detect_leading_silence
from bisect import bisect_right
from dataclasses import dataclass, asdict

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
    duration_seconds = float(ffmpeg.probe(filename)['format']['duration'])
    return duration_seconds

def trim_silence(audio_segment,silence_threshold=-30.0):
    trim_leading_silence = lambda x: x[detect_leading_silence(x,silence_threshold=silence_threshold) :]
    trim_trailing_silence = lambda x: trim_leading_silence(x.reverse()).reverse()
    strip_silence = lambda x: trim_trailing_silence(trim_leading_silence(x))

    stripped = strip_silence(audio_segment)
    return stripped

def speedup_audio_file(filename, speedup_factor):
    file_extension = os.path.splitext(filename)[1]
    audio = load_audio(filename)

    audio_speedup = audio.speedup(playback_speed=speedup_factor)

    #save to the same place with new name
    export_filename = f"{os.path.splitext(filename)[0]}_{speedup_factor}{file_extension}"
    audio_speedup.export(export_filename, format=file_extension.lower()[1:])

    print(f"{filename} sped up successfully.")

def ticks_to_seconds(ticks, ticks_per_beat, microseconds_per_beat):
    """
    given the number of ticks, calculate the duration in seconds
    """
    # Calculate seconds from ticks based on tempo
    return ticks / ticks_per_beat * microseconds_per_beat / 1000000


def current_tick_to_seconds(current_tick, tempo_changes, ticks_per_beat=480):
    """
    given the current tick, and a list of tempo changes, calculate the current time in seconds
    """
    #tempo_changes: tick, microseconds_per_beat, current_time_in_seconds
    t = [x[0] for x in tempo_changes]

    def find_le(a, x):
        'Find rightmost value less than or equal to x'
        i = bisect_right(a, x)
        if i:
            return i-1, a[i-1]
        raise ValueError
    index, tick = find_le(t, current_tick)
    return tempo_changes[index][2]+ticks_to_seconds(current_tick - tick, ticks_per_beat, tempo_changes[index][1])


def get_measure_starts(mid):
    """
    get the starting time given measure number
    assumes varying tempo

    returns: a dict of measure start time (indexed by measure number, starting from 1), in ticks and seconds
    """

    time_signature_changes = [] #numerator, denominator, tick, seconds
    tempo_changes = [] #tick, microseconds_per_beat
    current_microseconds_per_beat = 500000 # midi default
    current_tick = 0
    current_time_in_seconds = 0

    for msg in mid.tracks[0]:
        # tick when the event happens
        # MIDI uses delta time: time since last message
        current_tick += msg.time
        current_time_in_seconds+=ticks_to_seconds(msg.time, mid.ticks_per_beat, current_microseconds_per_beat)

        if msg.type == 'set_tempo':
            current_microseconds_per_beat = msg.tempo
            # save the tempo change detail
            tempo_changes.append((current_tick, current_microseconds_per_beat,current_time_in_seconds))

        if msg.type == 'time_signature':
            last_numerator, last_denominator = msg.numerator, msg.denominator
            # save the time signature change detail
            time_signature_changes.append((msg.numerator,msg.denominator,current_tick,current_time_in_seconds))

    # mark the ending
    time_signature_changes.append((last_numerator, last_denominator,current_tick,current_time_in_seconds))

    measure_starts_dict = dict()

    measure_count = 0
    for i in range(len(time_signature_changes)-1):
        numerator, denominator, current_tick, current_time_in_seconds = time_signature_changes[i]
        #print(current_time_in_seconds)
        _, _, next_tick, next_time_in_seconds = time_signature_changes[i+1]
        #ticks_per_measure = numerator * mid.ticks_per_beat * 4 // denominator
        ticks_per_measure = int (numerator * mid.ticks_per_beat * 4 / denominator)

        # for each measure
        for measure_start_tick in range(current_tick, next_tick, ticks_per_measure):
            measure_count+=1
            measure_start_seconds = current_tick_to_seconds(measure_start_tick, tempo_changes, ticks_per_beat = mid.ticks_per_beat)
            measure_starts_dict[measure_count] = (measure_start_tick,measure_start_seconds)
    return measure_starts_dict

if __name__ == "__main__":
    """
    mid = mido.MidiFile("./midi/Yankee_doodle_Saloon_style_100.mid")
    mid = mido.MidiFile("./midi/test.mid")
    print(get_measure_starts(mid))

    # speed up
    speed_up_factor=1.5
    for i in range(1,5):
        speedup_audio_file(f"./tts/{i}.mp3",speed_up_factor)
        audio = AudioSegment.from_mp3(f"./tts/{i}_{speed_up_factor}.mp3")
        audio = trim_silence(audio)
        audio.export(f"./tts/{i}_trimmed.mp3", format="mp3")
    """

    # trim
    tts_word = "stop"
    audio = AudioSegment.from_mp3(f"./tts/{tts_word}.mp3")
    audio = trim_silence(audio)
    audio.export(f"./tts/{tts_word}.mp3", format="mp3")