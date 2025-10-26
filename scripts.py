from pydub import AudioSegment
from utils import *
import mido
from overlay import *
from moviepy.editor import *
from tts import *
from midi_rendition import *

def annotate_measure_info(text, starting_measure, ending_measure, measures_info = dict()):
    """
    annotate measure info for each measure [starting_measure, ending_measure] (inclusive)
    """
    for measure in range(starting_measure,ending_measure+1):
        print(starting_measure, ending_measure)
        if measure  < total_measures_count:
            ending_time = measure_starts[measure+1][1]
        else:
            ending_time = total_audio_duration
        measures_info[measure] = {"text":text,"starting_time":measure_starts[measure][1],"ending_time":ending_time}

def overlay_instruction(music, text=None, measure_numbers=[],offset_in_ms=0, instruction_duration_in_measures = 1, measures_info = dict(), rhythmic=False, bpm=None):
    """
    overlay tts instruction at selected measures
    """
    for measure_number in measure_numbers:
        if rhythmic:
            bpm = int(round(60*1000000.0/measure_starts[measure_number][2]))
            tts_filename = f"./tts/{text}_rhythmic_{bpm}.mp3"
            if not os.path.exists(tts_filename):
                synth_rhythmic_speech(" ".join(text.split("_")), bpm = bpm)
        else:
            tts_filename = f"./tts/{text}.mp3"
            if not os.path.exists(tts_filename):
                synth_sentence(" ".join(text.split("_")))
        voice = AudioSegment.from_mp3(tts_filename)
        music = overlay_at_measure(music,voice,measure_number=measure_number, midifile = midifile, offset_in_ms=offset_in_ms)
    # record the time info
    for starting_measure in measure_numbers:
        annotate_measure_info(text, starting_measure, starting_measure+instruction_duration_in_measures-1, measures_info=measures_info)
    return music

def video_from_measures_info(measures_info, videofile = None, audiofile = None):
    """
    measures_info: a list of tuples of (text_label, starting_time, ending_time)
    audiofile: path of the audiofile
    """
    print("MAKING VIDEO")
    text_duration = 0.0
    previous_text = measures_info[1]["text"]
    text_starting_time = measures_info[1]["starting_time"]
    texts = []

    for measure in sorted(measures_info.keys()):
        measure_info = measures_info[measure]
        #print(measure, measure_info)
        text = measure_info["text"]
        if text==previous_text:
            text_ending_time = measure_info["ending_time"]
        else:
            texts.append((previous_text, text_starting_time, text_ending_time))
            text_starting_time = measure_info["starting_time"]
            text_ending_time = measure_info["ending_time"]
        previous_text = text
    texts.append((previous_text, text_starting_time, text_ending_time))
    print(texts)

    text_size = (1200, 300)
    clips = []
    for text,text_starting_time, text_ending_time in texts:
        text = " ".join(text.split("_"))
        # Define the duration for each slide
        duration = text_ending_time-text_starting_time  # seconds
        # Create a clip with the text "walking"
        clip = TextClip(text, fontsize=70, color='white', size=text_size, method='caption').set_duration(duration).set_pos('center').on_color(color=(0, 0, 0), col_opacity=1)
        clips.append(clip)

    # Concatenate the two clips
    final_clip = concatenate_videoclips(clips)
    # Load the audio file
    audio = AudioFileClip(audiofile).subclip(0, final_clip.duration)
    # Set the audio to the video clip
    final_clip = final_clip.set_audio(audio)
    # Write the result to a file
    final_clip.write_videofile(videofile, fps=24, codec="h264", ffmpeg_params=["-pix_fmt", "yuv420p"])

def overlay_from_yaml(yaml_path=None, music=None, midifile=None, measures_info=None):
    stuff = load_yaml(yaml_path)
    for ctd in stuff["countdowns"]:
        # get the tempo at the measure
        bpm = int(round(60*1000000.0/measure_starts[ctd["start_measure"]][2]))
        music = overlay_countdown(music, midifile=midifile,start_measure=ctd["start_measure"],bpm=bpm/ctd.get("every_x_beat",1) ,count_from=ctd["count_from"],offset_in_ms=ctd.get("offset_in_ms",0))
    instructions = stuff["instructions"]
    for info in instructions:
        text = "_".join(info["text"].split())
        if info["voiced"]:
            instruction_duration_in_measures = info.get("instruction_duration_in_measures",1)
            rhythmic = info.get("rhythmic",False)
            music = overlay_instruction(music, text=text, measure_numbers = info["measure_numbers"], instruction_duration_in_measures = instruction_duration_in_measures, measures_info=measures_info, rhythmic=rhythmic, bpm=bpm)
        else:
            for start_measure in info["measure_numbers"]:
                annotate_measure_info(text,start_measure,start_measure+info["instruction_duration_in_measures"]-1,measures_info=measures_info)
    return music


# Define paths and filenames
#midi_file = "./midi/Mary_had_a_Little_Lamb_-_variations_through_time.mid"
#midi_file = "./midi/London_Bridge_Is_Falling_Down.mid"
midi_file = "./midi/Mozart_12_Variations_on_Ah_vous_dirai-je_Maman_K.265.mid"
midi_file = "./midi/My-Favorite-Things-(From-'The-Sound-Of-Music')-1.mid"
midi_file = "./midi/MyFavoriteThings.mid"
midi_file = "./midi/K265_cut.mid"
midi_file = "./midi/Yankee_doodle_Saloon_style.mid"
midi_file = "./midi/doremi.mid"
midi_file = "./midi/fav.mid"
midi_file = "./midi/K265_cutmore.mid"
soundfont = "~/Music/FluidR3_GM/FluidR3_GM.sf2"

# Convert MIDI to WAV
#wav_file = midi_to_mp3(midi_file, mp3_file, soundfont)

# https://en.wikipedia.org/wiki/General_MIDI

# when bpm is None, no tempo change is performed
bpm = 120


#original_name = "Yankee_doodle_Saloon_style"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="e-piano1", perc_inst="woodblock", num_measures_padded = 8, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"


#original_name = "Yankee_doodle_Saloon_style_running_standing"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="e-piano1", perc_inst="woodblock", num_measures_padded = 8, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"

#original_name = "metronome"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="woodblock", perc_inst="woodblock", num_measures_padded = 32, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"


#original_name = "stroke_more"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="accordion", perc_inst="woodblock", num_measures_padded = 20, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="accordion", perc_inst="woodblock", num_measures_padded = 32, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"

#original_name = "roman_II"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="accordion", perc_inst="woodblock", num_measures_padded = 20, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"

#original_name = "roman_III"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="accordion", perc_inst="woodblock", num_measures_padded = 20, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"

#original_name = "roman_IV"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="accordion", perc_inst="woodblock", num_measures_padded = 20, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"

#original_name = "roman_V"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="accordion", perc_inst="woodblock", num_measures_padded = 20, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"

#original_name = "roman_VI"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="accordion", perc_inst="woodblock", num_measures_padded = 20, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"




#original_name = "roman_VII"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="accordion", perc_inst="woodblock", num_measures_padded = 20, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"


#original_name = "roman_VIII"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="accordion", perc_inst="woodblock", num_measures_padded = 20, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"


#original_name = "roman_IX"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="accordion", perc_inst="woodblock", num_measures_padded = 20, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"

#original_name = "roman_X"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="accordion", perc_inst="woodblock", num_measures_padded = 20, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"


#original_name = "stroke_clockwise_triangle"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="accordion", perc_inst="woodblock", num_measures_padded = 24, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"

#original_name = "stroke_counterclockwise_triangle"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="accordion", perc_inst="woodblock", num_measures_padded = 24, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"


#original_name = "stroke_rulb_lbru"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="e-piano1", perc_inst="woodblock", num_measures_padded = 32, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"


original_name = "numbers1"
midi_file =f"./midi/{original_name}.mid"
generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="e-piano1", perc_inst="woodblock", num_measures_padded = 16, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
yaml_name = f"{original_name}_padded"

#original_name = "stroke_lurb_rblu"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="e-piano1", perc_inst="woodblock", num_measures_padded = 32, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"

#original_name = "stroke_down_up"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="e-piano1", perc_inst="woodblock", num_measures_padded = 32, numerator_padded=1, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"


#original_name = "K265_cutmore"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="e-piano1", perc_inst="woodblock", num_measures_padded = 8, change_inst=True, add_drum=True, change_tempo=True)
#yaml_name = f"{original_name}_padded"

#original_name = "doremi"
#midi_file =f"./midi/{original_name}.mid"
#yaml_name =f"{original_name}_padded_simple"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="e-piano1", perc_inst="woodblock", num_measures_padded = 8, change_inst=True, add_drum=True, change_tempo=True)

#bpm = None
#original_name = "doremi_acc"
#midi_file =f"./midi/{original_name}.mid"
#yaml_name =f"doremi_padded_simple"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="e-piano1", perc_inst="woodblock", num_measures_padded = 0, change_inst=True, add_drum=True, change_tempo=False)


#original_name = "fav"
#midi_file =f"./midi/{original_name}.mid"
#generate_mp3(midi_file, bpm = bpm, soundfont = soundfont, inst="accordion", perc_inst="woodblock", num_measures_padded = 3, numerator_padded=3, denominator_padded=4, change_inst=True, add_drum=True, change_tempo=True)
if bpm:
    mp3file = f"./music/{original_name}_padded_{bpm}_drum_added.mp3"
    midifile = f"./midi/{original_name}_padded_{bpm}_drum_added.mid"
    mp3file_overlay = f"./music/{original_name}_padded_{bpm}_drum_added_overlay.mp3"
    mp4file = f"{yaml_name}_bpm{bpm}.mp4"
else:
    mp3file = f"./music/{original_name}_padded_drum_added.mp3"
    midifile = f"./midi/{original_name}_padded_drum_added.mid"
    mp3file_overlay = f"./music/{original_name}_padded_drum_added_overlay.mp3"
    mp4file = f"{yaml_name}.mp4"

total_audio_duration = get_duration(mp3file)#alternatively: mid.length the two might be different, due to reverb
mid = mido.MidiFile(midifile)
music = AudioSegment.from_mp3(mp3file)
measure_starts = get_measure_starts(mid) # a dict, in ticks and seconds and tempo (microseconds)
total_measures_count = max(measure_starts.keys())
print("total number of measures",total_measures_count,"total duration",total_audio_duration)
measures_info = dict() #global

music = overlay_from_yaml(yaml_path=f"./yaml/{yaml_name}.yaml", music=music, midifile=midifile, measures_info=measures_info)

music.export(mp3file_overlay, format="mp3")

{print(f"{key}: {value}") for key, value in measures_info.items()}
video_from_measures_info(measures_info, videofile=mp4file, audiofile = mp3file_overlay)