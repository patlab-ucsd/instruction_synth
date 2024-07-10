from midi2audio import FluidSynth
from pydub import AudioSegment
import os
import mido
import tempfile

def midi_to_mp3(midi_file, mp3_file, soundfont):
    fluidsynth = FluidSynth(soundfont)
    # render in wav
    wav_filename = f"{midi_file[:-4]}.wav"
    fluidsynth.midi_to_audio(midi_file, wav_filename)
    # convert to mp3
    audio = AudioSegment.from_wav(wav_filename)
    audio.export(mp3_file, format="mp3")
    # delete wav
    if os.path.exists(wav_filename):
        os.remove(wav_filename)
        print(f"Deleted intermediate WAV file: {wav_filename}")

def render_midi_to_mp3(midi_file, bpm = 100, soundfont = None, inst = "nylon-guitar"):
    """
    render midi given bpm
    single instrument
    """

    fluidsynth = FluidSynth(soundfont)
    mp3_file = f"./music/{os.path.split(os.path.splitext(midi_file)[0])[-1]}_{bpm}.mp3"
    # Ensure the directory including the file exists; create if it doesn't
    os.makedirs(os.path.dirname(mp3_file), exist_ok=True)

    # https://en.wikipedia.org/wiki/General_MIDI
    insts = {"e-piano1":4,
             "marimba":12,
             "accordion":21,
             "nylon-guitar":24,
             "steel-guitar":25,
             "flute":73,
             "recorder":74,
             "woodblock":115}
    inst = insts[inst]

    # Adjust tempo in memory and render MIDI to WAV
    with mido.MidiFile(midi_file) as mid:
        print("number of tracks:",len(mid.tracks))
        #Tempo is in microseconds per beat (quarter note) default: 500000  (60 bpm)

        new_mid = mido.MidiFile()
        for track in mid.tracks:
            new_track = mido.MidiTrack()
            new_mid.tracks.append(new_track)

            new_mid.ticks_per_beat=mid.ticks_per_beat
            print("tempo:",mido.bpm2tempo(bpm))

            # set instrument at the beginning
            new_msg = mido.Message('program_change', program=inst, time=0)
            new_track.append(new_msg)

            for msg in track:
                if "note" not in msg.type:
                    print(msg)
                if msg.type == 'set_tempo':
                    new_msg = mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(bpm), time=int(msg.time * new_mid.ticks_per_beat))
                    new_track.append(new_msg)
                elif msg.type == 'program_change':
                    new_msg = mido.Message('program_change', program=inst, channel=msg.channel, time=int(msg.time * new_mid.ticks_per_beat))
                    new_track.append(new_msg)
                elif msg.type == "control_change":
                    # https://nickfever.com/music/midi-cc-list
                    #10:Pan Control Change
                    #91:Reverb Send Level Control Change
                    #93:Chorus Send Level Control
                    pass
                else:
                    # Copy other messages unchanged
                    new_track.append(msg)

        # Save adjusted MIDI events to a temporary file
        adjusted_midi_file = tempfile.NamedTemporaryFile(suffix='.mid', delete=True)
        new_mid.save(adjusted_midi_file.name)

    temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=True)

    # render in wave
    fluidsynth.midi_to_audio(adjusted_midi_file.name, temp_wav.name)
    # convert to mp3
    audio = AudioSegment.from_wav(temp_wav.name)
    audio.export(mp3_file, format="mp3")

# Define paths and filenames
midi_file = "./midi/Yankee_doodle_Saloon_style.mid"  
soundfont = "~/Music/FluidR3_GM/FluidR3_GM.sf2" 

# Convert MIDI to WAV
#wav_file = midi_to_mp3(midi_file, mp3_file, soundfont)

render_midi_to_mp3(midi_file, bpm = 120, soundfont = soundfont, inst="e-piano1")