"""Offline scene planning and bounded FFmpeg rendering."""
import io
import json
import shutil
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

SIZES = {"9:16": (720, 1280), "16:9": (1280, 720), "1:1": (720, 720)}
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_AUDIO_BYTES = 25 * 1024 * 1024


class StudioError(ValueError):
    pass


def split_script(content, duration):
    if duration not in (30, 60, 90):
        raise StudioError("Thời lượng phải là 30, 60 hoặc 90 giây.")
    words = content.strip().split()
    if not words:
        raise StudioError("Vui lòng nhập nội dung video.")
    if len(content) > 12000:
        raise StudioError("Nội dung tối đa 12.000 ký tự.")
    # Contiguous balanced groups preserve every word, even without punctuation.
    count = min(duration // 10, len(words))
    scenes = []
    for i in range(count):
        start, end = i * len(words) // count, (i + 1) * len(words) // count
        scenes.append(" ".join(words[start:end]))
    return scenes


def font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def demo_image(topic, index, size):
    w, h = size
    image = Image.new("RGB", size, "#11172C")
    draw = ImageDraw.Draw(image)
    colors = ["#7C3AED", "#2563EB", "#0D9488"]
    color = colors[index % len(colors)]
    draw.ellipse((w * .25, h * .10, w * 1.15, h * .70), fill=color)
    draw.rounded_rectangle((w * .08, h * .55, w * .92, h * .91), radius=24, fill="#191D2E")
    draw.text((w * .12, h * .59), f"CẢNH {index + 1:02d}", font=font(24), fill="#C4B5FD")
    title = textwrap.fill(topic[:100], width=max(12, w // 27))
    draw.multiline_text((w * .12, h * .65), title, font=font(36), fill="white", spacing=12)
    return image


def prepare_image(data, size):
    if len(data) > MAX_IMAGE_BYTES:
        raise StudioError("Ảnh tối đa 15 MB.")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > 25_000_000:
                raise StudioError("Ảnh tối đa 25 triệu điểm ảnh.")
            source.load()
            return ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"), size)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise StudioError("Không đọc được ảnh. Hãy tải PNG, JPG hoặc WebP hợp lệ.") from exc


def run(args, timeout=240):
    try:
        return subprocess.run(args, check=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise StudioError("Xử lý quá thời gian cho phép. Hãy thử lại với video ngắn hơn.") from exc
    except (subprocess.CalledProcessError, OSError) as exc:
        raise StudioError("Không thể xử lý media. Kiểm tra tệp đầu vào và cài đặt FFmpeg.") from exc


def probe(path):
    result = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], 30)
    return json.loads(result.stdout)


def render_video(images, audio, duration, ratio, directory, progress=None):
    if duration not in (30, 60, 90) or ratio not in SIZES:
        raise StudioError("Cấu hình video không hợp lệ.")
    if not images or len(images) > 9:
        raise StudioError("Cần từ 1 đến 9 ảnh cho video.")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise StudioError("Máy chủ chưa cài FFmpeg và FFprobe.")
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    audio_path = root / "voice.mp3"
    if audio is not None:
        if not audio or len(audio) > MAX_AUDIO_BYTES:
            raise StudioError("MP3 phải có dữ liệu và không vượt quá 25 MB.")
        audio_path.write_bytes(audio)
        info = probe(audio_path)
        streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
        if not streams or streams[0].get("codec_name") != "mp3":
            raise StudioError("Tệp giọng đọc phải là âm thanh MP3 hợp lệ.")
    frames = duration * 24
    for i, image in enumerate(images):
        image_path = root / f"image-{i}.png"
        if image.size != SIZES[ratio]:
            image = ImageOps.fit(image.convert("RGB"), SIZES[ratio])
        image.save(image_path)
        count = (i + 1) * frames // len(images) - i * frames // len(images)
        run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "24", "-i", str(image_path),
             "-frames:v", str(count), "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
             "-pix_fmt", "yuv420p", "-threads", "2", str(root / f"scene-{i}.mp4")])
        if progress:
            progress((i + 1) / (len(images) + 1))
    playlist = root / "scenes.txt"
    playlist.write_text("".join(f"file 'scene-{i}.mp4'\n" for i in range(len(images))), encoding="utf-8")
    command = ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "1", "-i", str(playlist)]
    if audio is None:
        command += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    else:
        command += ["-i", str(audio_path)]
    output = root / "video.mp4"
    command += ["-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-af", "apad", "-t", str(duration),
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output)]
    run(command)
    if progress:
        progress(1.0)
    return output.read_bytes()
