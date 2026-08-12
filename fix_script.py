from pathlib import Path

path = Path('backend/main.py')
lines = path.read_text(encoding='utf-8').splitlines(keepends=True)

# البحث عن السطر بدقة وتعديله
for i, line in enumerate(lines):
    if 'subtitles=' in line and 'ass_file_str' in line:
        lines[i] = '            "-vf", f"subtitles=\\\'{ass_file_str}\\\':fontsdir={Path(\"fonts\").resolve().as_posix()}\",\n'
        print(f"تم تعديل السطر رقم {i} بنجاح!")
        break

path.write_text(''.join(lines), encoding='utf-8')
