"""Operator-controlled endpoints; secrets never enter job records or frontend fields."""
import ipaddress
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from studio import StudioError


@dataclass(frozen=True)
class WorkerConfig:
    url: str
    token: str = field(repr=False)
    catalog: Path = Path('worker/workflows/catalog.json')
    wait_seconds: int = 1800
    allow_local: bool = False

    def validate(self, resolve=False):
        try:
            parts = urlsplit(self.url)
            parts.port  # Reject malformed/out-of-range ports before requests.
        except (ValueError, TypeError) as exc:
            raise StudioError('URL worker không hợp lệ.') from exc
        if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or '..' in parts.path or '%' in parts.path:
            raise StudioError('URL worker cần là địa chỉ gốc hợp lệ, không chứa tài khoản, query hoặc đường dẫn .. .')
        if parts.scheme != 'https' and not (self.allow_local and parts.scheme == 'http' and parts.hostname in ('localhost', '127.0.0.1', '::1')):
            raise StudioError('Worker ngoài phải dùng HTTPS. HTTP chỉ dành cho localhost trong profile local có cấu hình rõ ràng.')
        if not self.allow_local and not self.token:
            raise StudioError('Worker HTTPS cần token xác thực do chủ worker cấp; đây không phải API key trả phí.')
        if not isinstance(self.wait_seconds, int) or not 60 <= self.wait_seconds <= 7200:
            raise StudioError('Thời gian theo dõi cần từ 60 đến 7.200 giây.')
        if resolve and not self.allow_local:
            try:
                addresses = socket.getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)
                if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                    raise StudioError('Worker Cloud cần địa chỉ public; địa chỉ nội bộ/metadata không được phép.')
            except (socket.gaierror, ValueError) as exc:
                raise StudioError('Không phân giải được địa chỉ worker.') from exc
        return self

    @property
    def identity(self):
        # No token in provenance, hashes or downloadable tracking data.
        return self.url.rstrip('/')


def load_config(secrets=None):
    section = dict(secrets or {})
    url = os.getenv('AI_VIDEO_WORKER_URL', section.get('worker_url', ''))
    if not isinstance(url, str):
        raise StudioError('worker_url cần là chuỗi địa chỉ HTTPS.')
    url = url.strip().rstrip('/')
    if not url:
        return None
    token = os.getenv('AI_VIDEO_WORKER_TOKEN', section.get('worker_token', ''))
    catalog_value = os.getenv('AI_VIDEO_CATALOG', section.get('catalog', 'worker/workflows/catalog.json'))
    if not isinstance(token, str) or not isinstance(catalog_value, str):
        raise StudioError('Token và đường dẫn catalog cần là chuỗi cấu hình.')
    catalog = Path(catalog_value)
    local = os.getenv('STUDIO_RENDER_PROFILE') == 'local' and os.getenv('AI_VIDEO_ALLOW_LOCAL') == '1'
    try:
        wait = int(os.getenv('AI_VIDEO_WAIT_SECONDS', section.get('wait_seconds', 1800)))
    except (ValueError, TypeError) as exc:
        raise StudioError('Cấu hình thời gian chờ worker không hợp lệ.') from exc
    return WorkerConfig(url, token, catalog, wait, local).validate()
