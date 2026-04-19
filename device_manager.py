import pyaudiowpatch as pyaudio


def _open_pa():
    return pyaudio.PyAudio()


def get_output_devices():
    """Return list of (name, output_device_index) for WASAPI output devices."""
    p = _open_pa()
    devices = []
    try:
        wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        for i in range(p.get_device_count()):
            d = p.get_device_info_by_index(i)
            if (d["hostApi"] == wasapi["index"]
                    and d["maxOutputChannels"] > 0
                    and not d.get("isLoopbackDevice", False)):
                devices.append((d["name"], i))
    finally:
        p.terminate()
    return devices


def get_default_output_index():
    """Return the pyaudiowpatch index of the Windows default output device."""
    p = _open_pa()
    try:
        wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        return wasapi["defaultOutputDevice"]
    finally:
        p.terminate()


def get_loopback_for_output(output_index):
    """
    Return (loopback_index, sample_rate, channels) for the given output device,
    or (None, None, None) if no loopback device is found.
    """
    p = _open_pa()
    try:
        output_info = p.get_device_info_by_index(output_index)
        output_name = output_info["name"]
        wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)

        for i in range(p.get_device_count()):
            d = p.get_device_info_by_index(i)
            if (d["hostApi"] == wasapi["index"]
                    and d.get("isLoopbackDevice", False)
                    and d["name"] == f"{output_name} [Loopback]"):
                return (
                    i,
                    int(d["defaultSampleRate"]),
                    d["maxInputChannels"],
                )
        return None, None, None
    finally:
        p.terminate()


def get_default_device_name():
    idx = get_default_output_index()
    p = _open_pa()
    try:
        return p.get_device_info_by_index(idx)["name"]
    finally:
        p.terminate()
