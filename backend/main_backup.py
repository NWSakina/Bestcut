from pathlib import Path
import shutil
import subprocess
import uuid
import json

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

        if len(lines) < 3:
            continue

        if "-->" not in lines[1]:
            continue

        start, end = lines[1].split("-->")
        subtitle = " ".join(lines[2:]).replace("[","").replace("]","").replace("|","").strip()

        if not subtitle:
            continue

        # فصل النص تلقائياً بناءً على الأرقام الفاصلة بين الآيات (مثل 3، 4، 5...)
        parts = [p.strip() for p in re.split(r'\b\d+\b', subtitle) if p.strip()]

        if not parts:
            continue

        start_ms = time_to_ms(start)
        end_ms = time_to_ms(end)
        total_duration = end_ms - start_ms
        part_duration = total_duration / len(parts)

        # إزاحة زمنية طفيفة (150 ملي ثانية) لتأخير النص قليلاً ليتطابق مع الصوت في المقاطع المقسمة
        offset = 150 if len(parts) > 1 else 0

        for idx, part_text in enumerate(parts):
            c_start = start_ms + int(idx * part_duration) + offset
            c_end = start_ms + int((idx + 1) * part_duration) + offset
            if c_end > end_ms:
                c_end = end_ms
            subtitles.append({
                "start": ms_to_time(c_start),
                "end": ms_to_time(c_end),
                "text": part_text,
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
















def hex_to_ass_color(hex_str):
    hex_str = hex_str.lstrip('#')
    r = hex_str[0:2]
    g = hex_str[2:4]
    b = hex_str[4:6]
    return f"&H00{b}{g}{r}".upper()

@app.post("/export")
async def export(
    file: UploadFile = File(...),
    srt: str = Form(...),
    subtitle_left: float = Form(50.0),
    subtitle_top: float = Form(22.0),
    subtitle_scale: float = Form(1.0),
    subtitle_color: str = Form("#FFFFFF"),
    shadow_color: str = Form("#000000"),
    custom_texts: str = Form("[]"),
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

        # الإعدادات الثابتة للأبعاد
        vid_width = 720
        vid_height = 1280

        # حساب الإحداثيات وحجم الخط بناءً على المدخلات
        pos_x = int((subtitle_left / 100.0) * vid_width)
        pos_y = int((subtitle_top / 100.0) * vid_height)
        font_size = int(55 * subtitle_scale)

        def hex_to_ass_color(hex_str):
            hex_str = hex_str.lstrip('#')
            r = hex_str[0:2]
            g = hex_str[2:4]
            b = hex_str[4:6]
            return f"&H00{b}{g}{r}".upper()

        primary_color = hex_to_ass_color(subtitle_color)
        shadow_ass_color = hex_to_ass_color(shadow_color)
        style_line = f"Style: Default,sans-serif,{font_size},{primary_color},&H000000FF,&H00000000,{shadow_ass_color},0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1"

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
            srt_data = f.read().replace('\r\n', '\n')

        blocks = srt_data.strip().split('\n\n')

        def convert_time(t_str):
            t_str = t_str.strip()
            parts = t_str.split(',')
            hms = parts[0]
            ms = parts[1] if len(parts) > 1 else "000"
            cc = ms[:2].ljust(2, '0')
            return f"{hms}.{cc}"

        for block in blocks:
            block_lines = [l.strip() for l in block.split('\n')]
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
                    end = convert_time(times[1])
                    text = " \\N ".join(text_lines)
                    # تطبيق الإحداثيات المثالية هنا
                    ass_content += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{\\pos({pos_x},{pos_y})}}{text}\n"

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        ass_file_str = ass_path.resolve().as_posix()

        custom_filters = ""
        try:
            texts_data = json.loads(custom_texts) if custom_texts else []
            for item in texts_data:
                if item.get("text", "").strip():
                    safe_text = item["text"].replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")
                    x_val = f"({item['left']}/100)*w-text_w/2"
                    y_val = f"({item['top']}/100)*h-text_h/2"
                    fs = int(40 * item['scale'])
                    custom_filters += f",drawtext=text='{safe_text}':x={x_val}:y={y_val}:fontsize={fs}:fontcolor=white:shadowx=2:shadowy=2"
        except Exception:
            pass

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path.resolve().as_posix()),
            "-fps_mode", "cfr",
            "-vf", f"subtitles=\'{ass_file_str}\'{custom_filters}",
            "-c:a", "aac",
            output_path.resolve().as_posix()
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if not output_path.exists():
            return JSONResponse(
                status_code=500,
                content={"message": "FFmpeg output file not generated"}
            )

        return FileResponse(
            path=str(output_path),
            media_type="video/mp4",
            filename=f"final_{video_id}.mp4"
        )

    except subprocess.CalledProcessError as e:
        return JSONResponse(
            status_code=500,
            content={"message": "FFmpeg error"}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"message": "Internal error"}
        )
