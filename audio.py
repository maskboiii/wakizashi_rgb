"""Audio capture and analysis for the Wakizashi RGB audio-reactive effects.

SoundCard's WASAPI loopback records the system output (what you actually hear)
without any virtual driver, so the keyboard can react to music and games.  The
capture runs in a QThread and never blocks the GUI; the DSP is split into small
pure NumPy helpers that can be exercised from the console without any audio
hardware attached.
"""

import math
import time

try:
    import numpy as np
except Exception:  # numpy is optional; the audio effects need it
    np = None

try:
    import soundcard as sc
except Exception:  # soundcard is optional, like mss in app.py
    sc = None

from PyQt6.QtCore import QThread, pyqtSignal

AVAILABLE = np is not None and sc is not None

DEFAULT_SR = 48000
DEFAULT_BLOCK = 2048
DEFAULT_BANDS = 16
DEFAULT_FMIN = 30.0
DEFAULT_FMAX = 16000.0
DEFAULT_FLOOR_DB = -80.0
DEFAULT_CEIL_DB = 0.0


# --------------------------------------------------------------------------
# DSP helpers (pure NumPy, no device access)
# --------------------------------------------------------------------------
def hann_window(size):
    return np.hanning(int(size))


def _hz_to_mel(hz):
    return 2595.0 * np.log10(1.0 + np.asarray(hz, dtype=float) / 700.0)


def _mel_to_hz(mel):
    return 700.0 * (10.0 ** (np.asarray(mel, dtype=float) / 2595.0) - 1.0)


def band_edges(sr, fft_size, n_bands, fmin=DEFAULT_FMIN, fmax=DEFAULT_FMAX,
               scale="log"):
    """Return ``[(lo, hi), ...]`` FFT-bin slices (end exclusive) per band.

    ``scale`` is one of ``"log"`` (default), ``"mel"`` or ``"linear"``.  Every
    band is guaranteed to cover at least one bin, even when the requested
    resolution is finer than the FFT.
    """
    n_bands = max(1, int(n_bands))
    fft_size = max(2, int(fft_size))
    nyquist = sr / 2.0
    fmin = max(1.0, min(float(fmin), nyquist))
    fmax = max(fmin + 1.0, min(float(fmax), nyquist))

    if scale == "linear":
        freqs = np.linspace(fmin, fmax, n_bands + 1)
    elif scale == "mel":
        freqs = _mel_to_hz(
            np.linspace(_hz_to_mel(fmin), _hz_to_mel(fmax), n_bands + 1))
    else:
        freqs = np.geomspace(fmin, fmax, n_bands + 1)

    n_bins = fft_size // 2 + 1
    bin_freqs = np.fft.rfftfreq(fft_size, 1.0 / sr)
    indices = np.searchsorted(bin_freqs, freqs)

    edges = []
    for i in range(n_bands):
        lo = int(min(indices[i], n_bins - 1))
        hi = int(min(max(indices[i + 1], lo + 1), n_bins))
        edges.append((lo, hi))
    return edges


def spectrum_db(block, window=None):
    """Amplitude spectrum of a mono block, normalised to dBFS.

    A full-scale sine peaks near 0 dB, which makes the dB floor/ceiling
    controls behave intuitively.
    """
    x = np.asarray(block, dtype=np.float64)
    n = x.size
    if n == 0:
        return np.zeros(1, dtype=float)
    if window is None or len(window) != n:
        window = np.hanning(n)
    gain = window.sum() / 2.0
    if gain <= 0:
        gain = 1.0
    spec = np.abs(np.fft.rfft(x * window)) / gain
    return 20.0 * np.log10(np.maximum(spec, 1e-9))


def band_levels(spec_db, edges):
    """Peak level (dB) inside every band slice."""
    levels = np.empty(len(edges), dtype=float)
    for i, (lo, hi) in enumerate(edges):
        levels[i] = spec_db[lo:hi].max() if hi > lo else -120.0
    return levels


def normalize_db(values, floor_db=DEFAULT_FLOOR_DB, ceil_db=DEFAULT_CEIL_DB):
    """Map dB values into 0..1 between the noise floor and the ceiling."""
    span = max(1e-6, float(ceil_db) - float(floor_db))
    return np.clip((np.asarray(values, dtype=float) - float(floor_db)) / span,
                   0.0, 1.0)


class EnvelopeTracker:
    """Attack/release smoothing for per-band levels.

    ``attack``/``release`` are time constants in seconds.  A short attack makes
    hits snappy, while a long release lets the bars fade gracefully.
    """

    def __init__(self, size, attack=0.01, release=0.15, dt=1.0 / 30.0):
        self.size = max(1, int(size))
        self.attack = max(1e-4, float(attack))
        self.release = max(1e-4, float(release))
        self.dt = float(dt)
        self.state = np.zeros(self.size, dtype=float)

    def reset(self):
        self.state = np.zeros(self.size, dtype=float)

    @staticmethod
    def _coef(tau, dt):
        return 1.0 - math.exp(-max(0.0, float(dt)) / tau)

    def update(self, values, dt=None):
        values = np.asarray(values, dtype=float)
        if values.size != self.size:
            self.size = values.size
            self.state = np.zeros(self.size, dtype=float)
        step = self.dt if dt is None else float(dt)
        rise = self._coef(self.attack, step)
        fall = self._coef(self.release, step)
        rising = values > self.state
        self.state = np.where(
            rising,
            self.state + (values - self.state) * rise,
            self.state + (values - self.state) * fall,
        )
        return self.state


def rms_level(block):
    x = np.asarray(block, dtype=np.float64)
    if x.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(x * x)))
    return 20.0 * math.log10(max(rms, 1e-9))


def peak_level(block):
    x = np.asarray(block, dtype=np.float64)
    if x.size == 0:
        return -120.0
    return 20.0 * math.log10(max(float(np.max(np.abs(x))), 1e-9))


def waveform(block, ncols):
    """Signed peak sample per column, for an oscilloscope-style display."""
    x = np.asarray(block, dtype=float)
    ncols = max(1, int(ncols))
    if x.size == 0:
        return np.zeros(ncols, dtype=float)
    if x.size <= ncols:
        out = np.zeros(ncols, dtype=float)
        out[:x.size] = x
        return out
    bounds = np.linspace(0, x.size, ncols + 1).astype(int)
    out = np.empty(ncols, dtype=float)
    for i in range(ncols):
        seg = x[bounds[i]:bounds[i + 1]]
        out[i] = seg[np.argmax(np.abs(seg))] if seg.size else 0.0
    return out


def to_mono(data, mono=True):
    """Reduce a frames x channels block to a 1-D float array.

    With ``mono=True`` the channels are averaged; otherwise the first channel
    is used.  The flag is kept for a future stereo effect.
    """
    arr = np.asarray(data, dtype=np.float64)
    if arr.ndim == 1:
        return arr
    if arr.size == 0:
        return arr.reshape(-1)
    if mono or arr.shape[1] == 1:
        return arr.mean(axis=1)
    return arr[:, 0]


def remove_dc(x):
    x = np.asarray(x, dtype=np.float64)
    return x - x.mean() if x.size else x


# --------------------------------------------------------------------------
# Device helpers
# --------------------------------------------------------------------------
def loopback_devices():
    """Return ``[(speaker_id, name), ...]`` usable as loopback sources.

    The default output is listed first.  SoundCard models loopback capture as
    a microphone wrapping a render (speaker) device, so we enumerate speakers
    and hand their ids to :func:`resolve_loopback`.
    """
    if sc is None:
        return []
    try:
        default_id = sc.default_speaker().id
    except Exception:
        default_id = None
    try:
        speakers = list(sc.all_speakers())
    except Exception:
        return []
    speakers.sort(key=lambda s: 0 if getattr(s, "id", None) == default_id else 1)
    return [(spk.id, spk.name) for spk in speakers]


def resolve_loopback(device_id=None):
    """Return the loopback microphone for a speaker id (or name)."""
    if sc is None:
        raise RuntimeError("soundcard не установлен")
    if not device_id:
        device_id = sc.default_speaker().id
    mic = sc.get_microphone(device_id, include_loopback=True)
    if getattr(mic, "isloopback", False):
        return mic
    # get_microphone may match a regular input with the same name; find the
    # loopback counterpart explicitly.
    for cand in sc.all_microphones(include_loopback=True):
        if getattr(cand, "isloopback", False) and cand.name == mic.name:
            return cand
    raise RuntimeError("устройство не поддерживает loopback")


# --------------------------------------------------------------------------
# Capture worker
# --------------------------------------------------------------------------
class AudioWorker(QThread):
    """Capture the system output and emit analysed audio data.

    Emits one dict per block:
    ``{"bands": [...], "wave": [...], "level": 0..1, "peak": 0..1,
    "device": name}``.
    """

    audioReady = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.device_id = None
        self.samplerate = DEFAULT_SR
        self.block = DEFAULT_BLOCK
        self.bands = DEFAULT_BANDS
        self.scale = "log"
        self.fmin = DEFAULT_FMIN
        self.fmax = DEFAULT_FMAX
        self.floor_db = DEFAULT_FLOOR_DB
        self.ceil_db = DEFAULT_CEIL_DB
        self.gain_db = 0.0
        self.attack = 0.01
        self.release = 0.15
        self.mono = True
        self._window = None
        self._edges = None
        self._envelope = None
        self._geometry_key = None
        self._last_device = None

    def _geometry(self):
        return (self.samplerate, self.block, self.bands, self.scale,
                round(self.fmin, 2), round(self.fmax, 2),
                round(self.attack, 4), round(self.release, 4))

    def _sync_geometry(self):
        key = self._geometry()
        if key == self._geometry_key:
            return
        self._window = hann_window(self.block)
        self._edges = band_edges(self.samplerate, self.block, self.bands,
                                 self.fmin, self.fmax, self.scale)
        self._envelope = EnvelopeTracker(self.bands, self.attack, self.release,
                                         self.block / self.samplerate)
        self._geometry_key = key

    def run(self):
        if not AVAILABLE:
            return
        delay = 0.25
        while not self.isInterruptionRequested():
            try:
                mic = resolve_loopback(self.device_id)
                self._last_device = mic.name
                with mic.recorder(samplerate=self.samplerate,
                                  blocksize=self.block * 4) as rec:
                    delay = 0.25
                    while not self.isInterruptionRequested():
                        data = rec.record(numframes=self.block)
                        self._emit(data)
            except Exception:
                if self.isInterruptionRequested():
                    break
                self.msleep(int(delay * 1000))
                delay = min(2.0, delay * 1.5)

    def _emit(self, data):
        self._sync_geometry()
        mono = remove_dc(to_mono(data, self.mono))
        levels = band_levels(spectrum_db(mono, self._window), self._edges)
        levels = levels + float(self.gain_db)
        norm = self._envelope.update(
            normalize_db(levels, self.floor_db, self.ceil_db),
            self.block / self.samplerate)
        self.audioReady.emit({
            "bands": norm.tolist(),
            "wave": waveform(mono, 64).tolist(),
            "level": float(normalize_db(rms_level(mono), self.floor_db,
                                        self.ceil_db)),
            "peak": float(normalize_db(peak_level(mono), self.floor_db,
                                       self.ceil_db)),
            "device": self._last_device,
        })


# --------------------------------------------------------------------------
# Console smoke test
# --------------------------------------------------------------------------
def _smoke_test(seconds=5.0, device_id=None):
    if not AVAILABLE:
        print("Зависимости не установлены: py -m pip install soundcard numpy")
        return 1
    mic = resolve_loopback(device_id)
    print(f"Захват: {mic.name} @ {DEFAULT_SR} Гц, блок {DEFAULT_BLOCK}")
    window = hann_window(DEFAULT_BLOCK)
    edges = band_edges(DEFAULT_SR, DEFAULT_BLOCK, DEFAULT_BANDS,
                       DEFAULT_FMIN, DEFAULT_FMAX, "log")
    envelope = EnvelopeTracker(DEFAULT_BANDS, 0.01, 0.15,
                               DEFAULT_BLOCK / DEFAULT_SR)
    bars = " .:-=+*#%@"
    start = time.monotonic()
    try:
        with mic.recorder(samplerate=DEFAULT_SR,
                          blocksize=DEFAULT_BLOCK * 4) as rec:
            while time.monotonic() - start < seconds:
                mono = remove_dc(to_mono(rec.record(numframes=DEFAULT_BLOCK)))
                levels = band_levels(spectrum_db(mono, window), edges)
                norm = envelope.update(
                    normalize_db(levels, DEFAULT_FLOOR_DB, DEFAULT_CEIL_DB),
                    DEFAULT_BLOCK / DEFAULT_SR)
                line = "".join(bars[min(9, int(v * 9.999))] for v in norm)
                print(f"\r[{line}] {int(norm.max() * 100):3d}%", end="",
                      flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(_smoke_test())
