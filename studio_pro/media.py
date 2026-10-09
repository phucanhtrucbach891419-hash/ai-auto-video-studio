"""Sequential, bounded FFmpeg pipeline; no network protocols or shell commands."""
import io
import json
import math
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from PIL import Image

from studio import StudioError, demo_image, prepare_image
from .models import FPS, MAX_MEDIA_BYTES, RenderResult, local_profile, validate_timeline
from .subtitles import make_cues, parse_srt, to_ass, to_srt

_RENDER_LOCK = threading.BoundedSemaphore(1)


def execute(args, timeout=240, cwd=None):
    try:
        return subprocess.run(args, cwd=cwd, timeout=timeout, check=True, capture_output=True)
    except subprocess.TimeoutExpired as exc:
        raise StudioError("Xử lý quá thời gian. Hãy giảm thời lượng/độ phân giải hoặc chuyển sang máy cá nhân/server.") from exc
    except subprocess.CalledProcessError as exc:
        raise StudioError("FFmpeg không xử lý được media. Kiểm tra tệp, codec và bộ lọc libass; thử xuất 720p.") from exc
    except OSError as exc:
        raise StudioError("Không chạy được FFmpeg hoặc không đủ dung lượng lưu trữ trên máy chủ.") from exc


def ffmpeg():
    return ["ffmpeg", "-y", "-nostdin", "-hide_banner", "-v", "error", "-filter_threads", "1", "-filter_complex_threads", "1"]


def inspect_file(path, kind):
    info = json.loads(execute(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-show_streams", "-show_format", "-of", "json", str(path)], 30).stdout)
    streams = info.get('streams', [])
    names = set(info.get('format', {}).get('format_name', '').split(','))
    try:
        duration = float(info['format']['duration'])
    except (KeyError, TypeError, ValueError) as exc:
        raise StudioError("Media không có thời lượng hợp lệ.") from exc
    if not math.isfinite(duration) or not 0 < duration <= 600:
        raise StudioError("Media tải lên cần có thời lượng trên 0 và tối đa 600 giây.")
    if kind == 'audio':
        if not names.intersection({'mp3', 'wav'}) or not any(s.get('codec_type') == 'audio' for s in streams) or any(s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic') for s in streams):
            raise StudioError("Âm thanh phải là tệp MP3 hoặc WAV hợp lệ.")
    else:
        video = next((s for s in streams if s.get('codec_type') == 'video'), None)
        if 'mp4' not in names or not video:
            raise StudioError("Clip phải là tệp MP4 có hình ảnh hợp lệ.")
        if video.get('width', 0) * video.get('height', 0) > 3840 * 2160 or min(video.get('width', 0), video.get('height', 0)) <= 0:
            raise StudioError("Clip nguồn tối đa 8,3 triệu điểm ảnh (4K).")
    return duration


def write_media(root, name, data, kind):
    if not isinstance(data, bytes) or not data or len(data) > MAX_MEDIA_BYTES:
        raise StudioError("Tệp media tối đa 25 MB và phải có dữ liệu.")
    path = root / name
    path.write_bytes(data)
    return path, inspect_file(path, kind)


def validate_upload(data, kind):
    """Validate untrusted media in an isolated directory, before expensive rendering."""
    with tempfile.TemporaryDirectory(prefix='studio-check-') as directory:
        return write_media(Path(directory), 'upload.bin', data, kind)[1]


def motion_filter(motion, size, frames):
    w, h = size
    end = max(1, frames - 1)
    if motion == 'static':
        return f"scale={w}:{h},setsar=1,fps={FPS}"
    if motion == 'zoom':
        z, x, y = f"1+0.18*on/{end}", 'iw/2-iw/zoom/2', 'ih/2-ih/zoom/2'
    elif motion == 'pan':
        z, x, y = '1.15', f"(iw-iw/zoom)*on/{end}", 'ih/2-ih/zoom/2'
    else:
        z, x, y = f"1.05+0.13*on/{end}", f"(iw-iw/zoom)*on/{end}", f"(ih-ih/zoom)*on/{end}"
    return f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={w}x{h}:fps={FPS},setsar=1"


def normalize_audio(root, source, target, duration, settings):
    args = ffmpeg()
    if source is None:
        args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
    else:
        args += ['-protocol_whitelist', 'file,pipe', '-i', str(source)]
    args += ['-map', '0:a:0', '-af', f"aformat=sample_fmts=fltp,atempo={settings.voice_speed},volume={settings.voice_volume},apad,atrim=duration={duration},asetpts=PTS-STARTPTS",
             '-t', str(duration), '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', str(target)]
    execute(args, cwd=root)


def render(scenes, settings, topic='Video của bạn', narration=None, music=None, srt=None, progress=None):
    """Return MP4 bytes; all inputs/segments are removed on success or failure."""
    total = validate_timeline(scenes, settings)
    if narration is not None and any(s.voice is not None for s in scenes):
        raise StudioError("Chọn lời đọc toàn video hoặc lời đọc từng cảnh, không dùng đồng thời.")
    if not all(shutil.which(tool) for tool in ('ffmpeg', 'ffprobe')):
        raise StudioError("Máy chủ cần cài FFmpeg và FFprobe.")
    cues = parse_srt(srt, total) if srt is not None else make_cues(scenes)
    # Validate auto-generated cues too, including rounding of tiny segments.
    normalized_srt = to_srt(cues)
    cues = parse_srt(normalized_srt, total)
    if not _RENDER_LOCK.acquire(blocking=False):
        raise StudioError("Máy chủ đang dựng một video Pro khác. Vui lòng thử lại sau.")
    warnings = []
    try:
        with tempfile.TemporaryDirectory(prefix='studio-pro-') as directory:
            root = Path(directory)
            full_voice = None
            if narration is not None:
                full_voice, length = write_media(root, 'narration.bin', narration, 'audio')
                if length / settings.voice_speed > total + .05:
                    warnings.append('Lời đọc toàn video dài hơn timeline; phần cuối đã bị cắt.')
            music_path = None
            if music is not None:
                music_path, _ = write_media(root, 'music.bin', music, 'audio')
            for i, scene in enumerate(scenes):
                seconds = scene.seconds
                args = ffmpeg()
                if scene.video is not None:
                    path, length = write_media(root, f'clip-{i}.mp4', scene.video, 'video')
                    args += ['-protocol_whitelist', 'file,pipe', '-i', str(path)]
                    w, h = settings.size
                    filters = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={FPS},tpad=stop_mode=clone:stop_duration={seconds}"
                    if length < seconds:
                        warnings.append(f'Cảnh {i+1}: clip ngắn, khung hình cuối được giữ đến hết cảnh.')
                else:
                    if scene.image is not None:
                        with Image.open(io.BytesIO(scene.image)) as image:
                            if image.format not in ('PNG', 'JPEG', 'WEBP'):
                                raise StudioError('Ảnh cảnh chỉ hỗ trợ PNG, JPEG hoặc WebP.')
                        image = prepare_image(scene.image, settings.size)
                    else:
                        image = demo_image(topic, i, settings.size)
                    path = root / f'image-{i}.png'
                    image.save(path)
                    args += ['-loop', '1', '-framerate', str(FPS), '-i', str(path)]
                    filters = motion_filter(scene.motion, settings.size, scene.frames)
                fade = min(settings.transition, seconds / 2)
                if fade:
                    filters += f",fade=t=in:st=0:d={fade},fade=t=out:st={seconds-fade}:d={fade}"
                filters += ',format=yuv420p,setpts=PTS-STARTPTS'
                args += ['-an', '-vf', filters, '-frames:v', str(scene.frames), '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-threads', '2', str(root / f'scene-{i}.mp4')]
                execute(args, timeout=600 if local_profile() else 240, cwd=root)
                if full_voice is None:
                    source = None
                    if scene.voice is not None:
                        source, length = write_media(root, f'voice-{i}.bin', scene.voice, 'audio')
                        if length / settings.voice_speed > seconds + .05:
                            warnings.append(f'Cảnh {i+1}: lời đọc dài hơn cảnh, phần cuối đã bị cắt. Tăng thời lượng cảnh nếu cần.')
                    normalize_audio(root, source, root / f'audio-{i}.wav', seconds, settings)
                if progress:
                    progress(.8 * (i + 1) / len(scenes), f'Đã dựng cảnh {i+1}/{len(scenes)}')
            (root / 'video-list.txt').write_text(''.join(f"file 'scene-{i}.mp4'\n" for i in range(len(scenes))))
            execute(ffmpeg() + ['-f', 'concat', '-safe', '1', '-i', 'video-list.txt', '-an', '-c:v', 'copy', 'picture.mp4'], cwd=root)
            if full_voice is not None:
                normalize_audio(root, full_voice, root / 'voice.wav', total, settings)
            else:
                (root / 'audio-list.txt').write_text(''.join(f"file 'audio-{i}.wav'\n" for i in range(len(scenes))))
                execute(ffmpeg() + ['-f', 'concat', '-safe', '1', '-i', 'audio-list.txt', '-c:a', 'pcm_s16le', 'voice.wav'], cwd=root)
            if progress:
                progress(.85, 'Đang trộn âm thanh và gắn phụ đề…')
            args = ffmpeg() + ['-i', 'picture.mp4', '-i', 'voice.wav']
            fade = min(settings.fade, total / 2)
            fade_filter = f"afade=t=in:st=0:d={fade},afade=t=out:st={total-fade}:d={fade}," if fade else ''
            graph = f"[1:a]{fade_filter}anull[voice];"
            if music_path:
                args += ['-stream_loop', '-1', '-protocol_whitelist', 'file,pipe', '-i', str(music_path)]
                graph += f"[2:a]aresample=48000,volume={settings.music_volume},{fade_filter}atrim=duration={total},asetpts=PTS-STARTPTS[music];[voice][music]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=0:latency=1[a]"
            else:
                graph += '[voice]alimiter=limit=0.95:level=0:latency=1[a]'
            args += ['-filter_complex', graph, '-map', '0:v:0', '-map', '[a]']
            if settings.burn_subtitles and cues:
                (root / 'captions.ass').write_text(to_ass(cues, settings.size), encoding='utf-8')
                args += ['-vf', 'ass=filename=captions.ass', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-threads', '2', '-pix_fmt', 'yuv420p']
            else:
                args += ['-c:v', 'copy']
            args += ['-t', str(total), '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-ac', '2', '-movflags', '+faststart', 'final.mp4']
            execute(args, timeout=600 if local_profile() else 240, cwd=root)
            result = RenderResult((root / 'final.mp4').read_bytes(), normalized_srt, total, warnings)
        if progress:
            progress(1.0, 'Video đã hoàn tất')
        return result
    except (OSError, Image.DecompressionBombError, ValueError) as exc:
        if isinstance(exc, StudioError):
            raise
        raise StudioError("Không đọc được dữ liệu hoặc không đủ tài nguyên. Kiểm tra media và thử lại ở 720p.") from exc
    finally:
        _RENDER_LOCK.release()
