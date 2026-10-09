"""Provider contracts. No remote calls or paid adapters are registered in phase A."""
from dataclasses import dataclass
from typing import Protocol

from studio import StudioError


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    uses_network: bool
    paid: bool
    capabilities: tuple[str, ...]


class SpeechProvider(Protocol):
    info: ProviderInfo

    def synthesize(self, text: str, voice: str) -> bytes: ...


class ScriptProvider(Protocol):
    info: ProviderInfo

    def generate(self, topic: str, audience: str, tone: str) -> str: ...


class VisualProvider(Protocol):
    info: ProviderInfo

    def generate(self, prompt: str, ratio: str) -> bytes: ...


def require_activation(info, enabled=False, cost_accepted=False):
    if info.uses_network and not enabled:
        raise StudioError('Dịch vụ mạng chưa được bạn chủ động bật.')
    if info.paid and not cost_accepted:
        raise StudioError('API trả phí đang tắt. Cần xem thông tin chi phí và chủ động xác nhận trước mỗi tác vụ.')
