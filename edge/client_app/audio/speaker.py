import simpleaudio as sa


def play_audio(path):
    wave = sa.WaveObject.from_wave_file(path)
    play = wave.play()
    play.wait_done()
