from pathlib import Path
import shutil
import subprocess
import uuid

from fastapi import FastAPI, File, UploadFile, Form
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


import re

def time_to_ms(t_str):
    t_str = t_str.strip()
    parts = t_str.split(':')
    h = int(parts[0])
    m = int(parts[1])
    s_ms = parts[2].split(',')
    s = int(s_ms[0])
    ms = int(s_ms[1]) if len(s_ms) > 1 else 0
    return h * 3600000 + m * 60000 + s * 1000 + ms

def ms_to_time(ms):
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def parse_srt(path: Path):
    subtitles = []
    
    if not path.exists():
        return subtitles
        
    text = path.read_text(encoding="utf-8")
    
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        if not lines:
            continue
            
        # البحث عن السطر الذي يحتوي على التوقيت لتجنب قراءة الأرقام نهائياً
        time_line_idx = -1
        for i, line in enumerate(lines):
            if "-->" in line:
                time_line_idx = i
                break
                
        if time_line_idx == -1:
            continue
            
        # استخراج أوقات البداية والنهاية
        time_parts = lines[time_line_idx].split("-->")
        if len(time_parts) != 2:
            continue
            
        start = time_parts[0].strip()
        end = time_parts[1].strip()
        
        # دمج كل الأسطر التي تلي سطر التوقيت لتكون هي النص (مع تجاهل رقم الكتلة العلوي)
        subtitle_lines = lines[time_line_idx + 1:]
        subtitle = " ".join(subtitle_lines).strip()
        
        if not subtitle:
            continue
            
        subtitles.append({
            "start": start,
            "end": end,
            "text": subtitle
        })
        
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
EXPORTED = Path("exported")
EXPORTED.mkdir(exist_ok=True)

EXPORTED = Path("exported")
EXPORTED.mkdir(exist_ok=True)



















@app.post("/export")
async def export(
    file: UploadFile = File(...),
    srt: str = Form(...),
    subtitle_left: float = Form(50.0),
    subtitle_top: float = Form(22.0),
    subtitle_scale: float = Form(1.0)
):
    try:
        video_id = str(uuid.uuid4())
        UPLOADS.mkdir(exist_ok=True, parents=True)
        EXPORTED.mkdir(exist_ok=True, parents=True)

        video_path = UPLOADS / f"{video_id}.mp4"
        srt_path = UPLOADS / f"{video_id}.srt"
        ass_path = UPLOADS / f"{video_id}.ass"
        output_path = EXPORTED / f"final_{video_id}.mp4"

        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt)

        vid_width = 720
        vid_height = 1280

        pos_x = int((subtitle_left / 100.0) * vid_width)
        pos_y = int((subtitle_top / 100.0) * vid_height)
        
        # حجم خط واضح ومثالي للفيديو الرأسي
        font_size = int(55 * max(0.5, min(subtitle_scale, 3.0)))

        # تصميم النص بحدود خارجية سوداء وخلفية شفافة تماماً
        style_line = f"Style: Default,sans-serif,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,2,6,5,10,10,10,1"

        ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {vid_width}
PlayResY: {vid_height}
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style_line}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        with open(srt_path, "r", encoding="utf-8") as f:
            srt_data = f.read().replace('\r\n', '\n').replace('\r', '')

        blocks = srt_data.strip().split('\n\n')
        
        # دالة دقيقة لتحويل توقيت SRT إلى توقيت ASS متوافق 100% لتجنب فقدان المزامنة
        def convert_time(t_str):
            t_str = t_str.strip()
            parts = t_str.split(',')
            hms = parts[0]
            ms = parts[1] if len(parts) > 1 else "000"
            cc = ms[:2].ljust(2, '0')
            return f"{hms}.{cc}"

        for block in blocks:
            block_lines = [l.strip() for l in block.split('\n') if l.strip()]
            if len(block_lines) >= 2:
                if "-->" in block_lines[0]:
                    time_line = block_lines[0]
                    text_lines = block_lines[1:]
                elif len(block_lines) >= 3 and "-->" in block_lines[1]:
                    time_line = block_lines[1]
                    text_lines = block_lines[2:]
                else:
                    continue

                times = time_line.split(" --> ")
                if len(times) == 2:
                    start = convert_time(times[0])
                    end = convert_time(times[1].split(" ")[0])
                    text = " \\N ".join(text_lines)
                    ass_content += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{\\an5\\pos({pos_x},{pos_y})}}{text}\n"

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        ass_file_str = ass_path.resolve().as_posix()

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path.resolve().as_posix(),
            "-fps_mode", "cfr",
            "-vf", f"subtitles=\'{ass_file_str}\'",
            "-c:a", "aac",
            output_path.resolve().as_posix()
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        if not output_path.exists():
            return JSONResponse(
                status_code=500,
                content={"message": "FFmpeg output not found", "details": result.stderr}
            )

        return FileResponse(
            path=str(output_path),
            media_type="video/mp4",
            filename=f"final_{video_id}.mp4"
        )

    except subprocess.CalledProcessError as e:
        return JSONResponse(
            status_code=500,
            content={"message": "FFmpeg error", "details": e.stderr}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"message": "Internal error", "details": str(e)}
        )
