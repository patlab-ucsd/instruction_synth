from moviepy.editor import *

# Define the duration for each slide
duration = 10.0  # seconds

text_size = (1000, 200)
# Create a clip with the text "walking"
walking_clip = TextClip("walking", fontsize=70, color='white', size=text_size).set_duration(duration).set_pos('center').on_color(color=(0, 0, 0), col_opacity=1)

# Create a clip with the text "running"
running_clip = TextClip("running", fontsize=70, color='white', size=text_size).set_duration(duration).set_pos('center').on_color(color=(0, 0, 0), col_opacity=1)

# Concatenate the two clips
final_clip = concatenate_videoclips([walking_clip, running_clip])

# Write the result to a file
final_clip.write_videofile("walking_running.mp4", fps=24, codec="h264")