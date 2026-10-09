"""Deterministic scene-based cues, editable SRT and escaped ASS for libass."""
import re
import textwrap
from dataclasses import dataclass

from studio import StudioError


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def timestamp(seconds, ass=False):
    scale = 100 if ass else 1000
    ticks = round(seconds * scale)
    whole, fraction = divmod(ticks, scale)
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    if ass:
        return f"{hours}:{minutes:02d}:{secs:02d}.{fraction:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{fraction:03d}"


def make_cues(scenes):
    cues, offset = [], 0.0
    for scene in scenes:
        text = ' '.join(scene.text.split())
        chunks = textwrap.wrap(text, width=72, break_long_words=True, break_on_hyphens=False)
        weights = [len(chunk.split()) for chunk in chunks]
        total = sum(weights)
        elapsed = 0
        for chunk, weight in zip(chunks, weights):
            start = offset + scene.seconds * elapsed / total
            elapsed += weight
            end = offset + scene.seconds * elapsed / total
            cues.append(Cue(start, end, '\n'.join(textwrap.wrap(chunk, width=36))))
        offset += scene.seconds
    return cues


def to_srt(cues):
    return '\n\n'.join(f"{i + 1}\n{timestamp(c.start)} --> {timestamp(c.end)}\n{c.text}" for i, c in enumerate(cues)) + ('\n' if cues else '')


def parse_srt(content, duration):
    if not isinstance(content, str) or len(content) > 60000:
        raise StudioError("SRT tối đa 60.000 ký tự.")
    content = content.lstrip('\ufeff').replace('\r\n', '\n').strip()
    if not content:
        return []
    cues, previous = [], 0
    pattern = r'(\d{2}):(\d{2}):(\d{2}),(\d{3})'
    for block in re.split(r'\n\s*\n', content):
        lines = block.split('\n')
        if len(lines) < 3 or not lines[0].isdigit() or int(lines[0]) != len(cues) + 1:
            raise StudioError("SRT cần số thứ tự liên tiếp từ 1, mốc thời gian và nội dung.")
        match = re.fullmatch(pattern + r' --> ' + pattern, lines[1])
        if not match:
            raise StudioError("Mốc SRT phải có dạng 00:00:00,000 --> 00:00:01,000.")
        values = list(map(int, match.groups()))
        if any(values[i] >= 60 for i in (1, 2, 5, 6)):
            raise StudioError("Phút/giây trong SRT phải nhỏ hơn 60.")
        def seconds(v):
            return v[0] * 3600 + v[1] * 60 + v[2] + v[3] / 1000
        start, end = seconds(values[:4]), seconds(values[4:])
        text = '\n'.join(lines[2:]).strip()
        if not text or len(text) > 1000 or any(ord(c) < 32 and c not in '\n\t' for c in text):
            raise StudioError("Nội dung mỗi dòng phụ đề phải có chữ, tối đa 1.000 ký tự và không chứa ký tự điều khiển.")
        if start < previous - .001 or end <= start or end > duration + .001:
            raise StudioError("Phụ đề phải tăng theo thời gian, không chồng lấn và nằm trong thời lượng video.")
        cues.append(Cue(start, end, text))
        previous = end
        if len(cues) > 500:
            raise StudioError("Tối đa 500 mốc phụ đề.")
    return cues


def ass_text(text):
    # Prevent user-controlled ASS override tags and escape sequences.
    return text.replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\t', ' ').replace('\n', r'\N')


def to_ass(cues, size):
    w, h = size
    size_font = round(min(w, h) * .045)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{size_font},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,{round(w*.06)},{round(w*.06)},{round(h*.07)},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header + ''.join(f"Dialogue: 0,{timestamp(c.start, True)},{timestamp(c.end, True)},Default,,0,0,0,,{ass_text(c.text)}\n" for c in cues)
