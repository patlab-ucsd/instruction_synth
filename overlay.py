from pydub import AudioSegment

# Load the music and voice tracks
music = AudioSegment.from_mp3("./music/Yankee_doodle_Saloon_style_120.mp3")
voice = AudioSegment.from_mp3("./tts/standing still.mp3")

# Define the position (in milliseconds) to overlay the voice track
overlay_position_ms = 2.5 * 1000

# Overlay the voice track onto the music track at the specified position
combined = music.overlay(voice, position=overlay_position_ms)
combined = combined.overlay(voice, position=overlay_position_ms*2)

# Export the mixed track
combined.export("output_combined.mp3", format="mp3")

print("Mixed audio track saved as output_combined.mp3")