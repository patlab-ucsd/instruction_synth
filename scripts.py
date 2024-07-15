from pydub import AudioSegment
from utils import *
import mido
from overlay import *
from moviepy.editor import *

def annotate_measure_info(text, starting_measure, ending_measure, measures_info = dict()):
    """
    annotate measure info for each measure [starting_measure, ending_measure] (inclusive)
    """
    for measure in range(starting_measure,ending_measure+1):
        if measure  < total_measures_count:
            ending_time = measure_starts[measure+1][1]
        else:
            ending_time = total_audio_duration
        measures_info[measure] = {"text":text,"starting_time":measure_starts[measure][1],"ending_time":ending_time}

def overlay_instruction(music, text=None, measure_numbers=[],offset_in_ms=0, instruction_duration_in_measures = 1, measures_info = dict()):
    """
    overlay tts instruction at selected measures
    """
    voice = AudioSegment.from_mp3(f"./tts/{text}.mp3")
    music = overlay_at_measure(music,voice,measure_numbers=measure_numbers, midifile = midifile, offset_in_ms=offset_in_ms)
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
        clip = TextClip(text, fontsize=70, color='white', size=text_size).set_duration(duration).set_pos('center').on_color(color=(0, 0, 0), col_opacity=1)
        clips.append(clip)

    # Concatenate the two clips
    final_clip = concatenate_videoclips(clips)
    # Load the audio file
    audio = AudioFileClip(audiofile).subclip(0, final_clip.duration)
    # Set the audio to the video clip
    final_clip = final_clip.set_audio(audio)
    # Write the result to a file
    final_clip.write_videofile(videofile, fps=24, codec="h264")

def overlay_from_yaml(yaml_path=None, music=None, midifile=None, bpm=None,measures_info=None):
    stuff = load_yaml(yaml_path)
    for ctd in stuff["countdowns"]:
        music = overlay_countdown(music, midifile=midifile,start_measure=ctd["start_measure"],bpm=bpm,count_from=ctd["count_from"],offset_in_ms=ctd["offset_in_ms"])
    instructions = stuff["instructions"]
    for info in instructions:
        text = "_".join(info["text"].split())
        if info["voiced"]:
            instruction_duration_in_measures = info.get("instruction_duration_in_measures",1)
            music = overlay_instruction(music, text=text, measure_numbers = info["measure_numbers"], instruction_duration_in_measures = instruction_duration_in_measures, measures_info=measures_info)
        else:
            for start_measure in info["measure_numbers"]:
                annotate_measure_info(text,start_measure,start_measure+info["instruction_duration_in_measures"]-1,measures_info=measures_info)
    return music

# Scripts for overlay and nnnotate yankee
bpm = 100
mp3file = f"./music/Yankee_doodle_Saloon_style_padded_{bpm}_drum_added.mp3"
midifile = f"./midi/Yankee_doodle_Saloon_style_padded_{bpm}_drum_added.mid"
mp3file_overlay = f"./music/Yankee_doodle_Saloon_style_padded_{bpm}_drum_added_overlay.mp3"
total_audio_duration = get_duration(mp3file)#alternatively: mid.length the two might be different, due to reverb
mid = mido.MidiFile(midifile)
music = AudioSegment.from_mp3(mp3file)
measure_starts = get_measure_starts(mid) # a dict, in ticks and seconds
total_measures_count = max(measure_starts.keys())
print("total number of measures",total_measures_count,"total duration",total_audio_duration)
measures_info = dict() #global

"""
# overlay countdown
music = overlay_countdown(music, midifile=midifile,start_measure=8,bpm=bpm,count_from=4,offset_in_ms=-20)
music = overlay_countdown(music, midifile=midifile,start_measure=26,bpm=bpm,count_from=4,offset_in_ms=-20)
music = overlay_countdown(music, midifile=midifile,start_measure=44,bpm=bpm,count_from=4,offset_in_ms=-20)
music = overlay_countdown(music, midifile=midifile,start_measure=62,bpm=bpm,count_from=4,offset_in_ms=-20)

# overlay instructions
# note: if parsing a file, needs to add _ 
music = overlay_instruction(music, text="moving", measure_numbers = [1,3,5],measures_info=measures_info)
music = overlay_instruction(music, text="stop", measure_numbers = [2,4,6],offset_in_ms=-20,measures_info=measures_info)
music = overlay_instruction(music, text="get_ready_to_walk_forward", measure_numbers = [7], instruction_duration_in_measures=2,measures_info=measures_info)
annotate_measure_info("walking_forward",9,24,measures_info=measures_info)
music = overlay_instruction(music, text="get_ready_to_run_forward", measure_numbers = [25], instruction_duration_in_measures=2,measures_info=measures_info)
annotate_measure_info("running_forward",27,42,measures_info=measures_info)
music = overlay_instruction(music, text="get_ready_to_walk_forward", measure_numbers = [43], instruction_duration_in_measures=2,measures_info=measures_info)
annotate_measure_info("walking_forward",45,60,measures_info=measures_info)
music = overlay_instruction(music, text="get_ready_to_stand_still", measure_numbers = [61], instruction_duration_in_measures=2,measures_info=measures_info)
annotate_measure_info("standing_still",63,78,measures_info=measures_info)
"""

music = overlay_from_yaml(yaml_path="./yaml/Yankee_doodle_Saloon_style_padded.yaml", music=music, midifile=midifile, bpm=bpm, measures_info=measures_info)

music.export(mp3file_overlay, format="mp3")

{print(f"{key}: {value}") for key, value in measures_info.items()}
video_from_measures_info(measures_info, videofile= "walking_running.mp4", audiofile = mp3file_overlay)