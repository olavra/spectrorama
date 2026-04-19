# Spectrorama

A lightweight real-time audio spectrum analyzer for Windows. It captures your system's audio output (loopback) and displays a live 1/3-octave dBFS spectrum — no microphone required.

## Demo

![Demo](src/Demo.mp4)

## Features

- 31-band ISO 1/3-octave spectrum (20 Hz – 20 kHz)
- Peak hold with slow decay
- Long-term average line
- Output device selector
- Always-on-top toggle (pin button)

## Requirements

- Windows 10/11
- Python 3.11+
- A WASAPI loopback-capable audio driver (provided by `pyaudiowpatch`)

## Running from source

```bash
# 1. Install dependencies
pip install -r requirements.txt
pip install pyaudiowpatch

# 2. Run
python main.py
```

> `pyaudiowpatch` is not listed in `requirements.txt` because it replaces the standard `pyaudio` package and must be installed separately.

## Compiling to an executable

Uses [PyInstaller](https://pyinstaller.org). A pre-configured `.spec` file is included.

```bash
# Install PyInstaller if needed
pip install pyinstaller

# Clean build
rm -rf build dist
pyinstaller spectrorama.spec
```

The output executable will be at `dist/Spectrorama.exe` — a single-file, no-console binary with all dependencies bundled.
