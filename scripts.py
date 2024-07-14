from pydub import AudioSegment
from utils import *
import mido
from overlay import *
from moviepy.editor import *

def annotate_measure_info(text, starting_measure, ending_measure):
    """
    annotate measure info for each measure [starting_measure, ending_measure] (inclusive)
    """
    for measure in range(starting_measure,ending_measure+1):
        if measure  < total_measures_count:
            ending_time = measure_starts[measure+1][1]
        else:
            ending_time = total_audio_duration
        measures_info[measure] = {"text":text,"starting_time":measure_starts[measure][1],"ending_time":ending_time}

def overlay_instruction(music, text=None, measure_numbers=None,offset=0, instruction_duration_in_measures = 1):
    """
    overlay tts instruction at selected measures
    """
    voice = AudioSegment.from_mp3(f"./tts/{text}.mp3")
    music = overlay_at_measure(music,voice,measure_numbers=measure_numbers, midifile = midifile, offset=offset)
    # record the time info
    for starting_measure in measure_numbers:
        annotate_measure_info(text, starting_measure, starting_measure+instruction_duration_in_measures-1)
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

    text_size = (1000, 200)
    clips = []
    for text,text_starting_time, text_ending_time in texts:
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


# Scripts for overlay and nnnotate yankee
bpm = 100
mp3file = f"./music/Yankee_doodle_Saloon_style_padded_{bpm}_drum_added.mp3"
midifile = f"./midi/Yankee_doodle_Saloon_style_padded_{bpm}_drum_added.mid"
mp3file_overlay = f"./music/Yankee_doodle_Saloon_style_padded_{bpm}_drum_added_overlay.mp3"
total_audio_duration = get_duration(mp3file)
mid = mido.MidiFile(midifile)
music = AudioSegment.from_mp3(mp3file)
measure_starts = get_measure_starts(mid) # a dict, in ticks and seconds
total_measures_count = max(measure_starts.keys())
print("total number of measures",total_measures_count,"total duration",total_audio_duration)
measures_info = dict() #global

# overlay countdown
music = overlay_countdown(music, midifile=midifile,measure_number=8,bpm=bpm,count_from=4,offset=-20)
music = overlay_countdown(music, midifile=midifile,measure_number=26,bpm=bpm,count_from=4,offset=-20)
music = overlay_countdown(music, midifile=midifile,measure_number=44,bpm=bpm,count_from=4,offset=-20)
music = overlay_countdown(music, midifile=midifile,measure_number=62,bpm=bpm,count_from=4,offset=-20)

# overlay instructions
music = overlay_instruction(music, text="moving", measure_numbers = [1,3,5])
music = overlay_instruction(music, text="stop", measure_numbers = [2,4,6],offset=-20)
music = overlay_instruction(music, text="next_walking_forward", measure_numbers = [7], instruction_duration_in_measures=2)
annotate_measure_info("walking_forward",9,24)
music = overlay_instruction(music, text="next_running_forward", measure_numbers = [25], instruction_duration_in_measures=2)
annotate_measure_info("running_forward",27,42)
music = overlay_instruction(music, text="next_walking_forward", measure_numbers = [43], instruction_duration_in_measures=2)
annotate_measure_info("walking_forward",45,60)
music = overlay_instruction(music, text="next_standing_still", measure_numbers = [61], instruction_duration_in_measures=2)
annotate_measure_info("standing_still",63,78)

music.export(mp3file_overlay, format="mp3")

{print(f"{key}: {value}") for key, value in measures_info.items()}
video_from_measures_info(measures_info, videofile= "walking_running.mp4", audiofile = mp3file_overlay)