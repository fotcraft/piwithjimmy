import os
import queue
import subprocess
import threading
from typing import Any, Dict, Optional

from app.prompts.phrases import PROMPT_PHRASES


class AudioOutput:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.prompts_cfg = config.get("prompts", {})
        self.base_dir = self.prompts_cfg.get("base_dir", "assets/prompts")
        self.prompt_map = self.prompts_cfg.get("map", {})

        device_cfg = config.get("device", {})
        self._volume = int(device_cfg.get("audio_volume", 85))
        tts_cfg = config.get("tts", {})
        self.voice_en = tts_cfg.get("voice_en", "en-us")
        self.voice_el = tts_cfg.get("voice_el", "el")
        self.tts_rate = int(tts_cfg.get("rate", 145))
        self.tts_pitch = int(tts_cfg.get("pitch", 40))
        self.tts_amplitude = int(tts_cfg.get("amplitude", 140))
        self.tts_word_gap_ms = int(tts_cfg.get("word_gap_ms", 5))

        self._queue: "queue.Queue[tuple[str, str, Optional[str]]]" = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def adjust_volume(self, delta: int) -> None:
        self._volume = max(0, min(100, self._volume + delta))
        subprocess.run(
            ["amixer", "sset", "Master", f"{self._volume}%"],
            check=False,
        )

    def play_prompt(self, prompt_id: str, lang: str) -> None:
        self._queue.put(("prompt", lang, prompt_id))

    def speak_text(self, text: str, lang: str) -> None:
        self._queue.put(("tts", lang, text))

    def _worker(self) -> None:
        while True:
            kind, lang, payload = self._queue.get()
            try:
                if kind == "prompt":
                    self._play_prompt_file_or_tts(payload, lang)
                else:
                    self._speak(payload, lang)
            finally:
                self._queue.task_done()

    def wait_idle(self) -> None:
        """
        Block until all queued audio has finished playing.
        Useful for one-shot runs that would otherwise exit early.
        """
        self._queue.join()

    def _play_prompt_file_or_tts(self, prompt_id: str, lang: str) -> None:
        file_key = self.prompt_map.get(prompt_id, prompt_id)
        path = os.path.join(self.base_dir, lang, f"{file_key}.wav")
        if os.path.exists(path):
            self._play_wav(path)
            return
        phrase = PROMPT_PHRASES.get(lang, {}).get(prompt_id)
        if phrase:
            self._speak(phrase, lang)

    def _play_wav(self, path: str) -> None:
        subprocess.run(["aplay", path], check=False)

    def _speak(self, text: str, lang: str) -> None:
        voice = self.voice_el if lang == "el" else self.voice_en
        amplitude = str(
            max(0, min(200, int(self.tts_amplitude * (self._volume / 100.0))))
        )
        subprocess.run(
            [
                "espeak-ng",
                "-v",
                voice,
                "-s",
                str(self.tts_rate),
                "-p",
                str(self.tts_pitch),
                "-a",
                amplitude,
                "-g",
                str(self.tts_word_gap_ms),
                text,
            ],
            check=False,
        )
