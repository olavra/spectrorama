import numpy as np
import pyaudiowpatch as pyaudio
from PyQt6.QtCore import QThread, pyqtSignal


class AudioCaptureThread(QThread):
    samples_ready = pyqtSignal(np.ndarray)

    def __init__(self, loopback_index=None, sample_rate=44100, channels=2, parent=None):
        super().__init__(parent)
        self._loopback_index = loopback_index
        self._sample_rate = sample_rate
        self._channels = channels
        self._running = False

    def run(self):
        self._running = True
        CHUNK = 1024
        p = pyaudio.PyAudio()

        def callback(in_data, frame_count, time_info, status):
            if not self._running:
                return (None, pyaudio.paComplete)
            samples = np.frombuffer(in_data, dtype=np.float32).copy()
            if self._channels > 1:
                samples = samples.reshape(-1, self._channels)
                mono = np.mean(samples, axis=1)
            else:
                mono = samples.flatten()
            self.samples_ready.emit(mono)
            return (None, pyaudio.paContinue)

        try:
            stream = p.open(
                format=pyaudio.paFloat32,
                channels=self._channels,
                rate=self._sample_rate,
                frames_per_buffer=CHUNK,
                input=True,
                input_device_index=self._loopback_index,
                stream_callback=callback,
            )
            stream.start_stream()
            while self._running and stream.is_active():
                self.msleep(10)
            stream.stop_stream()
            stream.close()
        except Exception as e:
            print(f"[AudioCapture] Error: {e}")
        finally:
            p.terminate()

    def stop(self):
        self._running = False
        self.wait(2000)
