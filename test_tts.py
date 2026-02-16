"""Quick test for Azure Neural TTS playback."""
import os
import subprocess
import tempfile

import requests

key = os.environ.get("AZURE_SPEECH_KEY", "")
if not key:
    print("ERROR: AZURE_SPEECH_KEY not set")
    exit(1)

ssml = (
    '<speak version="1.0" xml:lang="en-US">'
    '<voice name="en-US-JennyNeural">Hello, this is a test of Azure Neural Text to Speech.</voice>'
    '</speak>'
)

url = "https://italynorth.tts.speech.microsoft.com/cognitiveservices/v1"
headers = {
    "Ocp-Apim-Subscription-Key": key,
    "Content-Type": "application/ssml+xml",
    "X-Microsoft-OutputFormat": "riff-16khz-16bit-mono-pcm",
}

print("Calling Azure TTS...")
r = requests.post(url, headers=headers, data=ssml.encode("utf-8"), timeout=10)
print(f"HTTP {r.status_code}, size={len(r.content)} bytes")

if r.status_code != 200:
    print(f"Error: {r.text[:300]}")
    exit(1)

wav_path = "/tmp/test_azure_tts.wav"
with open(wav_path, "wb") as f:
    f.write(r.content)
print(f"Saved to {wav_path}")

# Try playback methods
for cmd in [
    ["aplay", "-D", "plughw:0,0", wav_path],
    ["aplay", wav_path],
    ["paplay", wav_path],
    ["ffplay", "-nodisp", "-autoexit", wav_path],
]:
    print(f"Trying: {' '.join(cmd)}")
    ret = subprocess.run(cmd, capture_output=True, text=True)
    if ret.returncode == 0:
        print("  -> SUCCESS")
        break
    else:
        print(f"  -> Failed: {ret.stderr.strip()[:100]}")
else:
    print("All playback methods failed. Check audio output config.")
