"""Optional Vietnamese Edge TTS. Network service, never advertised as offline."""
import asyncio

from studio import StudioError
from .providers import ProviderInfo, require_activation

VOICES = {'Nữ · Hoài My': 'vi-VN-HoaiMyNeural', 'Nam · Nam Minh': 'vi-VN-NamMinhNeural'}
INFO = ProviderInfo('edge-tts', 'Edge TTS', True, False, ('speech',))
MAX_TTS_BYTES = 25 * 1024 * 1024


async def _synthesize(text, voice):
    import edge_tts
    chunks, size = [], 0
    communicator = edge_tts.Communicate(text, voice, connect_timeout=10, receive_timeout=30)
    async for message in communicator.stream():
        if message['type'] == 'audio':
            size += len(message['data'])
            if size > MAX_TTS_BYTES:
                raise StudioError('Giọng đọc tạo ra vượt quá 25 MB. Hãy rút ngắn nội dung cảnh.')
            chunks.append(message['data'])
    if not chunks:
        raise StudioError('Dịch vụ không trả về âm thanh. Hãy tải MP3/WAV thay thế.')
    return b''.join(chunks)


def synthesize(text, voice, enabled=False):
    require_activation(INFO, enabled=enabled)
    if voice not in VOICES.values() or not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise StudioError('Chọn giọng tiếng Việt hợp lệ và nội dung từ 1 đến 4.000 ký tự/cảnh.')
    try:
        # Called only on an explicit UI action, outside any active event loop.
        return asyncio.run(asyncio.wait_for(_synthesize(text, voice), timeout=60))
    except StudioError:
        raise
    except ImportError as exc:
        raise StudioError('Chưa cài edge-tts. Có thể tải MP3/WAV thay thế.') from exc
    except Exception as exc:
        raise StudioError('Không kết nối được Edge TTS hoặc dịch vụ không khả dụng. Không có giọng offline; hãy tải MP3/WAV thay thế.') from exc
