from midi2audio import FluidSynth
from pydub import AudioSegment
import os
import mido
import tempfile

def examine_midi_msg(midi_file):
    """
    look at non-note msgs
    """
    with mido.MidiFile(midi_file) as mid:
        for track in mid.tracks:
            for msg in track:
                if "note" not in msg.type:
                    print(msg)

def generate_mp3_simple(midi_file, soundfont):
    """
    render midi from ./midi folder and save the mp3 file to ./music folder
    """
    mp3_file = f"{midi_file.replace('/midi/', '/music/')[:-4]}.mp3"

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

def midi_adjust_tempo_inst(midi_file, bpm = 100, soundfont = None, inst = "nylon-guitar", save_midi = False):
    """
    modify midi given bpm
    single instrument
    """

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
            new_track.append(mido.Message('program_change', program=inst, time=0))
            # set tempo at the beginning
            new_track.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(bpm), time=0))

            for msg in track:
                if "note" not in msg.type:
                    pass
                if msg.type == 'set_tempo':
                    new_msg = mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(bpm), time=msg.time)
                    new_track.append(new_msg)
                elif msg.type == 'program_change':
                    new_msg = mido.Message('program_change', program=inst, channel=msg.channel, time=msg.time)
                    new_track.append(new_msg)
                else:
                    new_track.append(msg)

        if not save_midi:
            adjusted_midi_file = tempfile.NamedTemporaryFile(suffix='.mid', delete=True).name
        else:
            adjusted_midi_file = f"{os.path.splitext(midi_file)[0]}_{bpm}.mid"
        new_mid.save(adjusted_midi_file)

        return adjusted_midi_file

def midi_add_padding_at_start(midi_file, num_measures = 6, numerator = 2, denominator = 4):
    """
    pad the beginning
    """

    with mido.MidiFile(midi_file) as mid:
        ticks_per_measure = int (numerator * mid.ticks_per_beat * 4 / denominator)
        total_ticks = num_measures * ticks_per_measure

        # look for the beginning
        padding_note = mido.Message("note_off", time = total_ticks)
        for track in mid.tracks:
            first_time_signature_index = 0
            index = 0
            # find the starting of the track
            for msg in track:
                if msg.type == 'time_signature':
                    first_time_signature_index = index
                    break
                index+=1
            print("padding insert position (index of midi msg):", first_time_signature_index+1)
            track.insert(first_time_signature_index+1, padding_note)
        adjusted_midi_file = f"{os.path.splitext(midi_file)[0]}_padded.mid"
        mid.save(adjusted_midi_file)
        return adjusted_midi_file

def midi_add_simple_drum(midi_file, perc_inst = "woodblock"):
    """
    add an additional percussion track
    """
    with mido.MidiFile(midi_file) as mid:
        #Tempo is in microseconds per beat (quarter note) default: 500000  (60 bpm)

        new_mid = mido.MidiFile()
        # copy everything
        for track in mid.tracks:
            new_track = mido.MidiTrack()
            new_mid.tracks.append(new_track)

            for msg in track:
                new_track.append(msg)

        # add a new perc track
        new_track = mido.MidiTrack()
        perc_channel = 15
        # set percussion inst
        new_track.append(mido.MetaMessage("track_name",name="Percussion", time=0))
        new_track.append(mido.Message('program_change', program=insts[perc_inst], channel= perc_channel, time=0))
        # set volume
        new_track.append(mido.Message("control_change",channel= perc_channel, control=7,value=90, time=0))

        # collect time changes
        time_changes = []
        current_tick = 0
        for msg in mid.tracks[0]:
            current_tick += msg.time
            if msg.type == 'time_signature':
                last_numerator, last_denominator = msg.numerator, msg.denominator
                time_changes.append((msg.numerator,msg.denominator,current_tick))
        # mark the ending
        time_changes.append((last_numerator, last_denominator,current_tick))

        # add the percussion
        for i in range(len(time_changes)-1):
            numerator, denominator, current_tick = time_changes[i]
            _, _, next_tick = time_changes[i+1]
            #ticks_per_measure = numerator * mid.ticks_per_beat * 4 // denominator
            ticks_per_note = mid.ticks_per_beat * 4 // denominator
            if numerator == 3 or numerator == 6:
                strong_beat_interval = 3
            elif numerator == 2 or numerator == 4:
                strong_beat_interval = 2
            else:
                strong_beat_interval = denominator
            note_count = 0
            # add percussion at each beat
            for time in range(current_tick, next_tick, ticks_per_note):
                if note_count%strong_beat_interval==0:
                    note_on_vel = 90
                else:
                    note_on_vel = 64
                # note duration: a beat
                # time is the delay from current time
                note_on = mido.Message("note_on", note=60, velocity=note_on_vel, time = 0, channel=perc_channel)
                new_track.append(note_on)
                note_off = mido.Message("note_off", note=60, velocity=64, time = ticks_per_note, channel=perc_channel)
                new_track.append(note_off)
                note_count+=1
        new_mid.tracks.append(new_track)

        adjusted_midi_file = f"{os.path.splitext(midi_file)[0]}_drum_added.mid"
        new_mid.save(adjusted_midi_file)
        return adjusted_midi_file

def midi_to_mp3(adjusted_midi_file, mp3_file):
    # Ensure the directory including the file exists; create if it doesn't
    os.makedirs(os.path.dirname(mp3_file), exist_ok=True)

    temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=True)

    fluidsynth = FluidSynth(soundfont)
    # render in wave
    fluidsynth.midi_to_audio(adjusted_midi_file, temp_wav.name)

    # convert to mp3
    audio = AudioSegment.from_wav(temp_wav.name)
    audio.export(mp3_file, format="mp3")

def generate_mp3(midi_file, bpm = 100, soundfont = None, inst = "nylon-guitar", perc_inst="woodblock",save_midi = False, num_measures_padded = 6, numerator_padded=4, denominator_padded=4):
    """
    1. padding at the beginning
    2. change the tempo and instrument
    3. add a drum track
    4. render to mp3
    """
    #adjusted_midi_file = midi_file
    adjusted_midi_file = midi_add_padding_at_start(midi_file, num_measures = num_measures_padded, numerator = numerator_padded, denominator = denominator_padded)
    adjusted_midi_file =  midi_adjust_tempo_inst(adjusted_midi_file, bpm = bpm, soundfont = soundfont, inst = inst, save_midi = save_midi)
    adjusted_midi_file = midi_add_simple_drum(adjusted_midi_file, perc_inst = perc_inst)
    generate_mp3_simple(adjusted_midi_file,soundfont)


# Define paths and filenames
#midi_file = "./midi/Mary_had_a_Little_Lamb_-_variations_through_time.mid"
#midi_file = "./midi/London_Bridge_Is_Falling_Down.mid"
midi_file = "./midi/Mozart_12_Variations_on_Ah_vous_dirai-je_Maman_K.265.mid"
midi_file = "./midi/My-Favorite-Things-(From-'The-Sound-Of-Music')-1.mid"
midi_file = "./midi/MyFavoriteThings.mid"
midi_file = "./midi/K265_cut.mid"
midi_file = "./midi/Yankee_doodle_Saloon_style.mid"
soundfont = "~/Music/FluidR3_GM/FluidR3_GM.sf2"

# Convert MIDI to WAV
#wav_file = midi_to_mp3(midi_file, mp3_file, soundfont)

# https://en.wikipedia.org/wiki/General_MIDI
insts = {"e-piano1":4,
         "e-piano2":5,
         "harpsichord":6,
         "marimba":12,
         "accordion":21,
         "nylon-guitar":24,
         "steel-guitar":25,
         "flute":73,
         "recorder":74,
         "cowbell":113,
         "woodblock":115,
         "taiko":116,
         "synthdrum":118}
generate_mp3(midi_file, bpm = 100, soundfont = soundfont, inst="e-piano1", perc_inst="woodblock", save_midi = True)
#examine_midi_msg("./midi/Yankee_doodle_Saloon_style_100_added.mid")