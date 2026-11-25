"""Speech output.

- Azure Neural TTS (natural voices), espeak-ng when offline.
- Short phrases (the device's spoken prompts) are cached on disk after the
  first synthesis, so prompts keep the natural voice when offline.
- stop() interrupts whatever is playing: pressing Scan or Repeat during
  reading stops the current speech immediately.
"""
import hashlib
import logging
import os
import queue
import shutil
import subprocess
import tempfile
import threading
from typing import Any, Dict, Optional, Tuple
from xml.sax.saxutils import escape

import requests

from app import net
from app.prompts.phrases import PROMPT_PHRASES

logger = logging.getLogger(__name__)

_CACHE_MAX_CHARS = 300


def build_ssml(text: str, voice: str, xml_lang: str, rate: str = "") -> str:
    """Build SSML with the text XML-escaped (OCR text often contains & < >)."""
    body = escape(text)
    if rate:
        body = f"<prosody rate='{escape(rate)}'>{body}</prosody>"
    return (
        f"<speak version='1.0' xml:lang='{xml_lang}'>"
        f"<voice name='{escape(voice)}'>{body}</voice>"
        f"</speak>"
    )


class AudioOutput:
    def __init__(self, config: Dict[str, Any]) -> None:
        prompts_cfg = config.get("prompts", {})
        self.base_dir = prompts_cfg.get("base_dir", "assets/prompts")
        self.prompt_map = prompts_cfg.get("map", {})

        device_cfg = config.get("device", {})
        self._volume = int(device_cfg.get("audio_volume", 85))
        tts_cfg = config.get("tts", {})

        self.azure_tts_enabled = bool(tts_cfg.get("azure_enabled", False))
        self.azure_tts_key = tts_cfg.get("azure_speech_key", "") or os.getenv("AZURE_SPEECH_KEY", "")
        self.azure_voice_en = tts_cfg.get("azure_voice_en", "en-US-JennyNeural")
        self.azure_voice_el = tts_cfg.get("azure_voice_el", "el-GR-AthinaNeural")
        self.azure_tts_region = tts_cfg.get("azure_region", "italynorth")
        self.azure_audio_format = tts_cfg.get("azure_audio_format", "riff-16khz-16bit-mono-pcm")
        self.azure_tts_timeout = float(tts_cfg.get("azure_timeout_seconds", 10))
        self.azure_rate = str(tts_cfg.get("azure_rate", ""))
        self.cache_dir = tts_cfg.get("cache_dir", "data/tts_cache")

        self.voice_en = tts_cfg.get("voice_en", "en-us")
        self.voice_el = tts_cfg.get("voice_el", "el")
        self.tts_rate = int(tts_cfg.get("rate", 145))
        self.tts_pitch = int(tts_cfg.get("pitch", 40))
        self.tts_amplitude = int(tts_cfg.get("amplitude", 140))
        self.tts_word_gap_ms = int(tts_cfg.get("word_gap_ms", 5))

        self._queue: "queue.Queue[Tuple[int, str, str, str]]" = queue.Queue()
        self._generation = 0
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        self._apply_volume()

    # ----------------------------------------------------------- public api
    @property
    def volume(self) -> int:
        return self._volume

    def adjust_volume(self, delta: int) -> int:
        self._volume = max(10, min(100, self._volume + delta))
        self._apply_volume()
        return self._volume

    def play_prompt(self, prompt_id: str, lang: str, **fmt: Any) -> None:
        self._queue.put((self._generation, "prompt", lang, prompt_id + _encode_fmt(fmt)))

    def speak_text(self, text: str, lang: str) -> None:
        self._queue.put((self._generation, "tts", lang, text))

    def stop(self) -> None:
        """Drop queued speech and stop what is playing now."""
        with self._lock:
            self._generation += 1
            proc = self._proc
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
        if proc and proc.poll() is None:
            proc.terminate()

    def is_busy(self) -> bool:
        with self._lock:
            playing = self._proc is not None and self._proc.poll() is None
        return playing or not self._queue.empty()

    def wait_idle(self) -> None:
        self._queue.join()

    # --------------------------------------------------------------- worker
    def _worker(self) -> None:
        while True:
            gen, kind, lang, payload = self._queue.get()
            try:
                if gen != self._generation:
                    continue  # stopped while queued
                if kind == "prompt":
                    self._play_prompt(payload, lang, gen)
                else:
                    self._speak(payload, lang, gen)
            except Exception as exc:
                logger.exception("Audio error: %s", exc)
            finally:
                self._queue.task_done()

    def _play_prompt(self, payload: str, lang: str, gen: int) -> None:
        prompt_id, fmt = _decode_fmt(payload)
        file_key = self.prompt_map.get(prompt_id, prompt_id)
        path = os.path.join(self.base_dir, lang, f"{file_key}.wav")
        if not fmt and os.path.exists(path):
            self._run([_player(), path], gen)
            return
        phrase = PROMPT_PHRASES.get(lang, PROMPT_PHRASES["en"]).get(prompt_id)
        if phrase:
            self._speak(phrase.format(**fmt), lang, gen)

    def _speak(self, text: str, lang: str, gen: int) -> None:
        if not text:
            return
        wav = self._azure_wav(text, lang)
        if wav:
            try:
                self._run([_player(), wav], gen)
            finally:
                if not wav.startswith(os.path.abspath(self.cache_dir)):
                    _unlink(wav)
            return
        self._speak_espeak(text, lang, gen)

    # ---------------------------------------------------------------- azure
    def _azure_wav(self, text: str, lang: str) -> Optional[str]:
        """Return a path to a WAV of `text`, from cache or Azure, or None."""
        if not self.azure_tts_enabled or not self.azure_tts_key:
            return None
        voice = self.azure_voice_el if lang == "el" else self.azure_voice_en
        cache_path = None
        if len(text) <= _CACHE_MAX_CHARS:
            digest = hashlib.sha1(f"{voice}|{self.azure_rate}|{text}".encode("utf-8")).hexdigest()
            cache_path = os.path.join(os.path.abspath(self.cache_dir), f"{digest}.wav")
            if os.path.exists(cache_path):
                return cache_path

        url = f"https://{self.azure_tts_region}.tts.speech.microsoft.com/cognitiveservices/v1"
        if not net.is_reachable(url):
            return None
        ssml = build_ssml(text, voice, "el-GR" if lang == "el" else "en-US", self.azure_rate)
        headers = {
            "Ocp-Apim-Subscription-Key": self.azure_tts_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": self.azure_audio_format,
            "User-Agent": "readable",
        }
        try:
            resp = requests.post(
                url, headers=headers, data=ssml.encode("utf-8"), timeout=self.azure_tts_timeout
            )
        except requests.RequestException as exc:
            logger.error("Azure TTS request failed: %s", exc)
            return None
        if resp.status_code != 200 or not resp.content:
            logger.error("Azure TTS HTTP %d: %s", resp.status_code, resp.text[:200])
            return None

        if cache_path:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            tmp = cache_path + ".part"
            with open(tmp, "wb") as fh:
                fh.write(resp.content)
            os.replace(tmp, cache_path)
            return cache_path
        fd, path = tempfile.mkstemp(suffix=".wav")
        with os.fdopen(fd, "wb") as fh:
            fh.write(resp.content)
        return path

    # --------------------------------------------------------------- espeak
    def _speak_espeak(self, text: str, lang: str, gen: int) -> None:
        voice = self.voice_el if lang == "el" else self.voice_en
        amplitude = max(0, min(200, int(self.tts_amplitude * (self._volume / 100.0))))
        self._run(
            [
                "espeak-ng", "-v", voice,
                "-s", str(self.tts_rate),
                "-p", str(self.tts_pitch),
                "-a", str(amplitude),
                "-g", str(self.tts_word_gap_ms),
                text,
            ],
            gen,
        )

    # -------------------------------------------------------------- helpers
    def _run(self, cmd, gen: int) -> int:
        env = os.environ.copy()
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        with self._lock:
            if gen != self._generation:
                return -1
            try:
                self._proc = subprocess.Popen(cmd, env=env)
            except FileNotFoundError:
                logger.error("Audio command not found: %s", cmd[0])
                return -1
            proc = self._proc
        rc = proc.wait()
        with self._lock:
            if self._proc is proc:
                self._proc = None
        return rc

    def _apply_volume(self) -> None:
        pct = f"{self._volume}%"
        if shutil.which("pactl"):
            ret = subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", pct],
                check=False, capture_output=True,
            )
            if ret.returncode == 0:
                return
        if shutil.which("amixer"):
            subprocess.run(["amixer", "-q", "sset", "Master", pct], check=False, capture_output=True)


def _player() -> str:
    return "paplay" if shutil.which("paplay") else "aplay"


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _encode_fmt(fmt: Dict[str, Any]) -> str:
    if not fmt:
        return ""
    return "|" + "|".join(f"{k}={v}" for k, v in fmt.items())


def _decode_fmt(payload: str):
    prompt_id, *pairs = payload.split("|")
    fmt = dict(p.split("=", 1) for p in pairs if "=" in p)
    return prompt_id, fmt
