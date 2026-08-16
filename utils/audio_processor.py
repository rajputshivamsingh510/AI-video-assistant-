import yt_dlp
from pydub import AudioSegment
import os
import shutil

DOWNLOAD_DIR = 'downloades'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ffmpeg location handling — works both locally on Windows AND on
# Streamlit Community Cloud (Linux):
#
# - Locally on Windows: ffmpeg isn't on PATH, so we point at the hardcoded
#   install folder.
# - On Streamlit Cloud: ffmpeg is installed via packages.txt (apt-get) and
#   is already on the system PATH — shutil.which("ffmpeg") finds it, so we
#   skip the hardcoded Windows path entirely and let yt-dlp/pydub use
#   whatever's on PATH.
_ffmpeg_on_path = shutil.which("ffmpeg") is not None

FFMPEG_LOCATION = None
if os.name == "nt" and not _ffmpeg_on_path:
    FFMPEG_LOCATION = r"C:\Users\rajpu\ffmpeg\bin"

if FFMPEG_LOCATION:
    os.environ["PATH"] = FFMPEG_LOCATION + os.pathsep + os.environ["PATH"]
    AudioSegment.converter = os.path.join(FFMPEG_LOCATION, "ffmpeg.exe")
    AudioSegment.ffprobe = os.path.join(FFMPEG_LOCATION, "ffprobe.exe")
# else: ffmpeg is already resolvable on PATH (Cloud / properly configured
# local machine) — pydub and yt-dlp will find it automatically.


def download_youtube_audio(url: str) -> str:
    output_path = os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_path,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "ffmpeg_location": FFMPEG_LOCATION,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        # IMPORTANT: prepare_filename() returns the name of the file BEFORE
        # postprocessing (i.e. the original .mp4/.webm/.m4a/.opus download).
        # FFmpegExtractAudio then converts that file to .wav on disk, but
        # does NOT rename the variable we hold here. Guessing extensions
        # with .replace(".webm", ".wav") only covers a couple of cases and
        # breaks for anything else (e.g. .mp4 audio streams — this is what
        # caused the earlier FileNotFoundError). Since preferredcodec="wav"
        # is always forced above, the real output file on disk is ALWAYS
        # <original_name_without_ext>.wav — so just strip whatever
        # extension yt-dlp used and append .wav.
        raw_filename = ydl.prepare_filename(info)
        filename = os.path.splitext(raw_filename)[0] + ".wav"

    if not os.path.exists(filename):
        raise RuntimeError(
            f"Expected output file not found after download/conversion: "
            f"'{filename}'. Check the '{DOWNLOAD_DIR}' folder to see what "
            f"yt-dlp actually produced — the title may contain characters "
            f"that were sanitized differently than expected."
        )

    return filename


def convert_to_wav(input_path: str) -> str:
    """Convert any audio/video file to WAV format using pydub."""
    output_path = os.path.splitext(input_path)[0] + "_converted.wav"
    audio = AudioSegment.from_file(input_path)
    audio = audio.set_channels(1).set_frame_rate(16000)  # 16khz
    audio.export(output_path, format="wav")
    return output_path


def chunk_audio(wav_path: str, chunk_minutes: int = 10) -> list:
    audio = AudioSegment.from_wav(wav_path)
    chunk_ms = chunk_minutes * 60 * 1000

    chunks = []

    for i, start in enumerate(range(0, len(audio), chunk_ms)):
        chunk = audio[start: start + chunk_ms]
        chunk_path = f"{wav_path}_chunk_{i}.wav"
        chunk.export(chunk_path, format="wav")

        chunks.append(chunk_path)

    return chunks


def process_input(source: str) -> list:
    if source.startswith("http://") or source.startswith("https://"):
        print("Detected YouTube URL. Downloading audio...")
        wav_path = download_youtube_audio(source)
    else:
        print("Detected local file. Converting to WAV...")
        wav_path = convert_to_wav(source)

    print("Chunking audio...")
    chunks = chunk_audio(wav_path)
    print(f"Audio ready — {len(chunks)} chunk(s) created.")
    return chunks
