import matplotlib.pyplot as plt
import numpy as np
from pydub import AudioSegment
import sys
from utils import *
import librosa
from IPython.display import Audio, display
import ipywidgets as widgets
import pygame
from pygame.locals import QUIT, KEYDOWN, K_SPACE, K_s, K_p, K_q
import time

def plot_wave(filename):
    # Load the MP3 file
    audio = load_audio(filename)

    # Convert the audio segment to raw data
    signal = np.array(audio.get_array_of_samples())

    # Get the frame rate
    fs = audio.frame_rate

    # If the audio has 2 channels (stereo), convert to mono by averaging the channels
    if audio.channels == 2:
        print("the loaded file is stereo")
        signal = signal.reshape((-1, 2))
        signal = signal.mean(axis=1)

    # Create a time axis in seconds
    Time = np.linspace(0, len(signal) / fs, num=len(signal))

    # Plot the waveform
    plt.figure(1)
    plt.title("Signal Wave")
    plt.plot(Time, signal)
    plt.xlabel("Time (seconds)")
    plt.ylabel("Amplitude")
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    plt.show()

plot_wave("./music/Yankee_doodle_Saloon_style_120.mp3")

