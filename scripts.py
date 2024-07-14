from pydub import AudioSegment
from utils import *
import mido
from overlay import *

# Annotate yankee
bpm = 100
mp3file = f"./music/Yankee_doodle_Saloon_style_padded_{bpm}_drum_added.mp3"
midifile = f"./midi/Yankee_doodle_Saloon_style_padded_{bpm}_drum_added.mid"
music = AudioSegment.from_mp3(mp3file)

# overlay countdown
music = overlay_countdown(music, midifile=midifile,measure_number=8,bpm=bpm,count_from=4,offset=-20)
music = overlay_countdown(music, midifile=midifile,measure_number=26,bpm=bpm,count_from=4,offset=-20)
music = overlay_countdown(music, midifile=midifile,measure_number=44,bpm=bpm,count_from=4,offset=-20)
music = overlay_countdown(music, midifile=midifile,measure_number=62,bpm=bpm,count_from=4,offset=-20)

# overlay instructions
voice = AudioSegment.from_mp3("./tts/moving.mp3")
music = overlay_at_measure(music,voice,measure_numbers=[1,3,5], midifile = midifile)
voice = AudioSegment.from_mp3("./tts/stop.mp3")
music = overlay_at_measure(music,voice,measure_numbers=[2,4,6], midifile = midifile, offset=-20)
voice = AudioSegment.from_mp3("./tts/next_walking_forward.mp3")
music = overlay_at_measure(music,voice,measure_numbers=[7], midifile = midifile)
voice = AudioSegment.from_mp3("./tts/next_running_forward.mp3")
music = overlay_at_measure(music,voice,measure_numbers=[25], midifile = midifile)
voice = AudioSegment.from_mp3("./tts/next_walking_forward.mp3")
music = overlay_at_measure(music,voice,measure_numbers=[43], midifile = midifile)
voice = AudioSegment.from_mp3("./tts/next_standing_still.mp3")
music = overlay_at_measure(music,voice,measure_numbers=[61], midifile = midifile)
music.export("output_combined.mp3", format="mp3")