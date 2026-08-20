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
HARFBUZZ_VIEW = Path("/data/data/com.termux/files/usr/bin/hb-view")
ARABIC_FONT = Path("/data/data/com.termux/files/home/Bestcut/backend/fonts/ScheherazadeNew-Regular.ttf")

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
import urllib.request

UTHMANI_AYAHS = None

def normalize_quran_text(s):
    s = re.sub(r'[\u064B-\u065F\u0670\u06D6-\u06ED]', '', s)
    s = s.replace("ٱ", "ا")
    s = re.sub(r'[أإآ]', 'ا', s)
    s = s.replace("ى", "ي")
    s = s.replace("ـ", "")
    s = s.replace("ا", "")
    return s

def load_uthmani_ayahs():
    global UTHMANI_AYAHS

    if UTHMANI_AYAHS is not None:
        return UTHMANI_AYAHS

    try:
        url = "https://api.alquran.cloud/v1/quran/quran-uthmani"
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.load(r)

        UTHMANI_AYAHS = []

        for surah in data["data"]["surahs"]:
            for ayah in surah["ayahs"]:
                text = ayah["text"].replace("\ufeff", "").strip()
                UTHMANI_AYAHS.append(text)

        return UTHMANI_AYAHS

    except Exception as e:
        print("UTHMANI LOAD ERROR:", e)
        return []

def find_uthmani_text(text):
    normalized = normalize_quran_text(text)

    if not normalized:
        return text

    ayahs = load_uthmani_ayahs()

    for ayah in ayahs:
        if normalize_quran_text(ayah) == normalized:
            return ayah

    return text

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

def render_arabic_text(text: str, output_path: Path, font_size: int = 50):
    subprocess.run(
        [
            str(HARFBUZZ_VIEW),
            str(ARABIC_FONT),
            text,
            "--background=none",
            "--foreground=ffffff",
            f"--font-size={font_size}",
            "-o",
            str(output_path),
        ],
        check=True,
    )

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
    font: str = Form("default"),
    subtitle_left: float = Form(50.0),
    subtitle_top: float = Form(22.0),
    subtitle_scale: float = Form(1.0),
    subtitle_color: str = Form("#FFFFFF"),
    shadow_color: str = Form("#000000"),
    custom_texts: str = Form("[]"),
):
    print("EXPORT FUNCTION STARTED")
    try:
        video_id = str(uuid.uuid4())
        UPLOADS.mkdir(exist_ok=True, parents=True)
        EXPORTED.mkdir(exist_ok=True, parents=True)

        harfbuzz_dir = UPLOADS / f"{video_id}_harfbuzz"
        harfbuzz_dir.mkdir(exist_ok=True, parents=True)

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
        font_size = int(50 * subtitle_scale)

        def hex_to_ass_color(hex_str):
            hex_str = hex_str.lstrip('#')
            r = hex_str[0:2]
            g = hex_str[2:4]
            b = hex_str[4:6]
            return f"&H00{b}{g}{r}".upper()

        primary_color = hex_to_ass_color(subtitle_color)
        shadow_ass_color = hex_to_ass_color(shadow_color)
        style_line = f"Style: Default,{'Scheherazade New' if font == 'Scheherazade' else 'sans-serif'},{font_size},{primary_color},&H000000FF,&H00000000,{shadow_ass_color},0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1"

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

        harfbuzz_images = []

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
                    if font == "Scheherazade":
                        hb_text = find_uthmani_text(" ".join(text_lines))
                        image_path = harfbuzz_dir / f"subtitle_{len(harfbuzz_images)}.png"
                        render_arabic_text(hb_text, image_path, font_size)
                        start_parts = start.split(":")
                        end_parts = end.split(":")
                        hb_start = int(start_parts[0]) * 3600 + int(start_parts[1]) * 60 + float(start_parts[2])
                        hb_end = int(end_parts[0]) * 3600 + int(end_parts[1]) * 60 + float(end_parts[2])
                        harfbuzz_images.append({
                            "path": image_path,
                            "start": hb_start,
                            "end": hb_end,
                        })
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
                    x_val = f"(main_w * {item['left']}/100) - (text_w/2)"
                    y_val = f"(main_h * {item['top']}/100)"
                    fs = int(40 * item['scale'])
                    custom_filters += f",drawtext=text='{safe_text}':x={x_val}:y={y_val}:fontsize={fs}:fontcolor=white:shadowx=2:shadowy=2"
        except Exception:
            pass
        if font == "Scheherazade" and harfbuzz_images:
            hb_inputs = []
            hb_filters = []
            current_video = "[0:v]"

            for idx, item in enumerate(harfbuzz_images):
                hb_inputs.extend(["-loop", "1", "-i", str(item["path"].resolve().as_posix())])

                x_expr = f"(main_w * {subtitle_left}/100) - (overlay_w/2)"
                y_expr = f"(main_h * {subtitle_top}/100) - overlay_h"

                output_label = f"[hb{idx}]"
                hb_filters.append(
                    f"{current_video}[{idx + 1}:v]overlay="
                    f"x={x_expr}:y={y_expr}:"
                    f"enable='between(t,{item['start']},{item['end']})'"
                    f":format=auto{output_label}"
                )
                current_video = output_label

        if font == "Scheherazade" and harfbuzz_images:
            filter_complex = ";".join(hb_filters)

            if custom_filters:
                filter_complex += f";{current_video}{custom_filters}[vout]"
            else:
                filter_complex += f";{current_video}null[vout]"

            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path.resolve().as_posix()),
                *hb_inputs,
                "-filter_complex", filter_complex,
                "-map", "[vout]",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-pix_fmt", "yuv420p",
                "-shortest",
                output_path.resolve().as_posix()
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path.resolve().as_posix()),
                "-fps_mode", "cfr",
                "-vf", f"subtitles=\'{ass_file_str}\':fontsdir=\'{Path('backend/fonts').resolve().as_posix()}\'{custom_filters}",
                "-c:a", "aac",
                output_path.resolve().as_posix()
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        print("FFMPEG STDERR:", result.stderr)
        print("FFMPEG RETURN CODE:", result.returncode)

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
