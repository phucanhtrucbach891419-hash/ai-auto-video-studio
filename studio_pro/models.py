"""Typed contracts and validation shared by UI, workers and future projects."""
import math
import os
from dataclasses import dataclass, field

from studio import StudioError

FPS = 24
MOTIONS = ("static", "zoom", "pan", "ken_burns")
MAX_MEDIA_BYTES = 25 * 1024 * 1024


def bounded(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise StudioError(f"{label} phải nằm trong khoảng {low}–{high}.")


def local_profile():
    return os.getenv("STUDIO_RENDER_PROFILE", "cloud") == "local"


def four_k_enabled():
    return local_profile() and os.getenv("STUDIO_ENABLE_4K", "0") == "1"


def dimensions(ratio, resolution):
    if ratio not in ("9:16", "16:9", "1:1") or resolution not in ("720p", "1080p", "4K"):
        raise StudioError("Tỷ lệ hoặc độ phân giải không hợp lệ.")
    short, long = {"720p": (720, 1280), "1080p": (1080, 1920), "4K": (2160, 3840)}[resolution]
    return {"9:16": (short, long), "16:9": (long, short), "1:1": (short, short)}[ratio]


@dataclass
class Scene:
    text: str
    duration: float
    motion: str = "ken_burns"
    image: bytes | None = None
    video: bytes | None = None
    voice: bytes | None = None

    @property
    def frames(self):
        return round(self.duration * FPS)

    @property
    def seconds(self):
        return self.frames / FPS

    def validate(self):
        if not isinstance(self.text, str) or len(self.text) > 12000:
            raise StudioError("Nội dung mỗi cảnh tối đa 12.000 ký tự.")
        bounded(self.duration, 1, 60, "Thời lượng mỗi cảnh")
        if self.motion not in MOTIONS:
            raise StudioError("Chuyển động không được hỗ trợ.")
        if self.image is not None and self.video is not None:
            raise StudioError("Mỗi cảnh chỉ dùng ảnh hoặc video, không dùng cả hai.")
        for data in (self.image, self.video, self.voice):
            if data is not None and (not isinstance(data, bytes) or not data or len(data) > MAX_MEDIA_BYTES):
                raise StudioError("Media phải có dữ liệu và không vượt quá 25 MB/tệp.")


@dataclass
class RenderSettings:
    ratio: str = "9:16"
    resolution: str = "720p"
    transition: float = 0.25
    voice_speed: float = 1.0
    voice_volume: float = 1.0
    music_volume: float = 0.15
    fade: float = 1.0
    burn_subtitles: bool = True

    @property
    def size(self):
        return dimensions(self.ratio, self.resolution)

    def validate(self):
        dimensions(self.ratio, self.resolution)
        if self.resolution == "4K" and not four_k_enabled():
            raise StudioError("4K chỉ được bật trên máy cá nhân/server bằng STUDIO_RENDER_PROFILE=local và STUDIO_ENABLE_4K=1.")
        for name, value, low, high in (
            ("Chuyển cảnh", self.transition, 0, 1), ("Tốc độ lời đọc", self.voice_speed, .5, 2),
            ("Âm lượng lời đọc", self.voice_volume, 0, 2), ("Âm lượng nhạc", self.music_volume, 0, 1),
            ("Fade âm thanh", self.fade, 0, 5),
        ):
            bounded(value, low, high, name)
        if not isinstance(self.burn_subtitles, bool):
            raise StudioError("Tùy chọn phụ đề không hợp lệ.")


@dataclass
class RenderResult:
    video: bytes
    srt: str
    duration: float
    warnings: list[str] = field(default_factory=list)


def validate_timeline(scenes, settings):
    settings.validate()
    maximum = 30 if local_profile() else 9
    if not scenes or len(scenes) > maximum:
        raise StudioError(f"Cần từ 1 đến {maximum} cảnh trong cấu hình hiện tại.")
    for scene in scenes:
        scene.validate()
    total = sum(s.seconds for s in scenes)
    limit = 300 if local_profile() else 90
    if total > limit:
        raise StudioError(f"Tổng thời lượng tối đa {limit} giây. Tác vụ dài hơn cần máy cá nhân/server.")
    if sum(len(data) for s in scenes for data in (s.image, s.video, s.voice) if data) > 150 * 1024 * 1024:
        raise StudioError("Tổng media cảnh tối đa 150 MB.")
    return total
