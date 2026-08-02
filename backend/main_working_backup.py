from pathlib import Path
import shutil
import subprocess
import uuid

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

UPLOADS = Path("uploads")
UPLOADS.mkdir(exist_ok=True)

WHISPER_BIN = Path("/data/data/com.termux/files/home/whisper.cpp/build/bin/whisper-cli")
MODEL = Path("/data/data/com.termux/files/home/whisper.cpp/models/ggml-small.bin")


@app.get("/")
def home():
    return FileResponse("static/index.html")


def parse_srt(path: Path):
    subtitles = []

    if not path.exists():
        return subtitles

    text = path.read_text(encoding="utf-8")

    for block in text.strip().split("\n\n"):
        lines = block.splitlines()

        if len(lines) < 3:
            continue

        if "-->" not in lines[1]:
            continue

        start, end = lines[1].split("-->")
        subtitle = " ".join(lines[2:]).replace("[","").replace("]","").replace("|","").strip()

        subtitles.append(
            {
                "start": start.strip(),
                "end": end.strip(),
                "text": subtitle,
            }
        )

    return subtitles

@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix

    video_path = UPLOADS / f"{uuid.uuid4()}{ext}"
    audio_path = video_path.with_suffix(".wav")
    srt_base = video_path.with_suffix("")
    srt_path = video_path.with_suffix(".srt")

    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-ar",
                "16000",
                "-ac",
                "1",
                str(audio_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        subprocess.run(
            [
                str(WHISPER_BIN),
                "-m",
                str(MODEL),
                "-f",
                str(audio_path),
                "--language",
                "ar",
                "--output-srt",
                "--output-file",
                str(srt_base),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        subtitles = parse_srt(srt_path)

        full_text = "\n".join(item["text"] for item in subtitles)

        return JSONResponse(
            {
                "success": True,
                "message": "تمت المعالجة",
                "text": full_text,
                "subtitles": subtitles,
                "video": "/" + str(video_path),
                "srt": "/" + str(srt_path),
            }
        )

    except subprocess.CalledProcessError as e:
        return JSONResponse(
            {
                "success": False,
                "message": f"Processing error: {e}",
            },
            status_code=500,
        )
