"""ComfyUI self-hosted HTTP adapter. No retry of GPU submission, no global interrupt."""
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import PurePosixPath

import requests

from studio import StudioError
from studio_pro.media import validate_upload
from studio_pro.models import MAX_MEDIA_BYTES
from .workflows import reference_png

TERMINAL = {'complete', 'failed', 'timed_out', 'downloaded', 'paused'}
ACTIVE = {'queued', 'running', 'submission_unknown', 'missing'}


class NetworkError(StudioError):
    pass


def valid_id(value):
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def safe_file(item):
    if not isinstance(item, dict):
        raise StudioError('Worker trả mô tả tệp không hợp lệ.')
    name, folder = item.get('filename', ''), item.get('subfolder', '')
    if not isinstance(name, str) or not isinstance(folder, str) or len(name)+len(folder) > 512 or item.get('type') != 'output':
        raise StudioError('Worker chỉ được trả tệp output hợp lệ.')
    for value in (name, folder):
        if '\\' in value or '%' in value or ':' in value or any(ord(c) < 32 for c in value) or '..' in PurePosixPath(value).parts or value.startswith('/'):
            raise StudioError('Đường dẫn media từ worker không an toàn.')
    if '/' in name or not name.lower().endswith('.mp4'):
        raise StudioError('Workflow cần trả MP4; ảnh/GIF không được dùng thay video AI.')
    return {'filename': name, 'subfolder': folder, 'type': 'output'}


@dataclass
class VideoJob:
    id: str
    scene_id: str
    worker: str
    profile: str
    output_node: str
    expected_seconds: float
    deadline: float
    created: float = field(default_factory=time.time)
    remote_id: str | None = None
    state: str = 'queued'
    message: str = 'Đang gửi workflow'
    output: dict | None = None
    data: bytes | None = field(default=None, repr=False)
    actual_seconds: float | None = None


class ComfyClient:
    def __init__(self, config, session=None):
        self.config = config.validate()
        self.session = session or requests.Session()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.session.close()

    def _read(self, method, route, limit=8*1024*1024, **kwargs):
        self.config.validate(resolve=True)
        headers = {'Authorization': 'Bearer '+self.config.token} if self.config.token else {}
        try:
            with self.session.request(method, self.config.url+'/'+route.lstrip('/'), headers=headers,
                                      timeout=(5, 15), allow_redirects=False, stream=True, **kwargs) as response:
                if 300 <= response.status_code < 400:
                    raise StudioError('Worker chuyển hướng URL; hãy cấu hình endpoint HTTPS trực tiếp, không theo redirect.')
                if response.status_code in (401, 403):
                    raise StudioError('Worker từ chối xác thực. Chủ ứng dụng cần kiểm tra token/quyền truy cập.')
                if response.status_code >= 500:
                    raise NetworkError('Worker/proxy lỗi 5xx; chưa rõ tác vụ đã nhận hay chưa. Kiểm tra trạng thái, không tự gửi lại.')
                if response.status_code >= 400:
                    raise StudioError(f'Worker trả HTTP {response.status_code}. Kiểm tra workflow, model và giới hạn worker; không tự gửi lại tác vụ.')
                chunks, size, start = [], 0, time.monotonic()
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > limit:
                        raise StudioError('Dữ liệu worker vượt giới hạn tải về cho phép.')
                    if time.monotonic()-start > 45:
                        raise NetworkError('Tải dữ liệu quá 45 giây. Kiểm tra trạng thái trước khi thử tải lại.')
                    chunks.append(chunk)
                return b''.join(chunks)
        except requests.RequestException as exc:
            raise NetworkError('Mất kết nối hoặc quá thời gian HTTP. Không tự gửi lại workflow để tránh tạo tác vụ trùng.') from exc

    def _json(self, method, route, **kwargs):
        try:
            data = json.loads(self._read(method, route, **kwargs))
            if not isinstance(data, dict):
                raise ValueError('not an object')
            return data
        except (ValueError, TypeError) as exc:
            if isinstance(exc, StudioError):
                raise
            if method == 'POST' and route == 'prompt':
                raise NetworkError('Không đọc được phản hồi gửi workflow; chưa rõ worker đã nhận. Không tự gửi lại.') from exc
            raise StudioError('Worker không trả JSON ComfyUI hợp lệ.') from exc

    def connect(self, profiles):
        stats = self._json('GET', 'system_stats')
        if not isinstance(stats.get('devices'), list):
            raise StudioError('system_stats không có danh sách thiết bị hợp lệ.')
        gpu = any(d.get('type') == 'cuda' and isinstance(d.get('vram_total'), (int, float)) and d['vram_total'] > 0 for d in stats.get('devices', []) if isinstance(d, dict))
        info = self._json('GET', 'object_info')
        errors = {}
        for profile in profiles:
            reasons = []
            for node in profile.graph.values():
                kind = node['class_type']
                schema = info.get(kind)
                if not isinstance(schema, dict):
                    reasons.append(f'Thiếu node {kind}')
                    continue
                if schema.get('api_node') or schema.get('is_api_node'):
                    reasons.append(f'Node {kind} là API ngoài; không được phép trong chế độ miễn phí')
                inputs = schema.get('input', {})
                if not isinstance(inputs, dict) or not all(isinstance(inputs.get(k, {}), dict) for k in ('required', 'optional')):
                    raise StudioError('object_info không có schema input hợp lệ.')
                fields = {**inputs.get('required', {}), **inputs.get('optional', {})}
                for name, value in node['inputs'].items():
                    if name not in fields:
                        reasons.append(f'Node {kind} không có input {name}; cần export lại workflow theo phiên bản worker')
                    elif isinstance(value, str) and isinstance(fields[name], list) and fields[name] and isinstance(fields[name][0], list) and value not in fields[name][0]:
                        reasons.append(f'Node {kind}: chưa có model/lựa chọn cho {name}')
            if not gpu:
                reasons.append('Worker chưa báo thiết bị CUDA có VRAM; không gửi tác vụ sinh video')
            errors[profile.id] = sorted(set(reasons))
        return {'gpu_reported': gpu, 'errors': errors}

    def submit(self, request, profile, enabled=False):
        if not enabled:
            raise StudioError("Chưa chủ động bật gửi tác vụ đến GPU worker.")
        # Local validation and image conversion happen before any GPU submission.
        _, seconds = profile.parameters(request)
        profile.validate()
        job_id = str(uuid.uuid4())
        image_name = None
        if request.mode == 'i2v':
            png = reference_png(request, profile)
            uploaded = self._json('POST', 'upload/image', files={'image': (job_id+'.png', png, 'image/png')}, data={'type': 'input', 'subfolder': 'studio', 'overwrite': 'false'})
            name, folder = uploaded.get('name', ''), uploaded.get('subfolder', '')
            # Reuse path validation, allowing only the exact generated upload name.
            if name != job_id+'.png' or folder != 'studio':
                raise StudioError('Worker không xác nhận đúng ảnh tham chiếu đã tải lên.')
            image_name = folder+'/'+name
        graph, seconds = profile.build(request, job_id, image_name)
        job = VideoJob(job_id, request.scene_id, self.config.identity, profile.id, profile.output_node, seconds, time.time()+self.config.wait_seconds)
        try:
            response = self._json('POST', 'prompt', json={'prompt': graph, 'client_id': job_id, 'prompt_id': job_id})
            remote = response.get('prompt_id')
            if not valid_id(remote):
                # An invalid successful response may still have queued a job.
                job.state, job.message = 'submission_unknown', 'Worker nhận request nhưng không trả mã hợp lệ. Cập nhật trạng thái; không tự gửi lại.'
            else:
                job.remote_id = remote
                job.message = 'Worker đã nhận workflow; chờ kiểm tra hàng đợi'
        except NetworkError:
            job.state, job.message = 'submission_unknown', 'Không biết worker đã nhận tác vụ hay chưa. Cập nhật trạng thái trước khi quyết định gửi lại.'
        return job

    def poll(self, job):
        if job.worker != self.config.identity:
            raise StudioError('Tác vụ thuộc endpoint khác. Kết nối lại đúng worker để kiểm tra.')
        if job.state in TERMINAL:
            return job
        if time.time() > job.deadline:
            job.state, job.message = 'timed_out', 'Hết thời gian theo dõi; tác vụ trên GPU có thể vẫn chạy. Không tự hủy hoặc gửi lại.'
            return job
        try:
            history_id = job.remote_id or job.id
            history = self._json('GET', 'history/'+history_id).get(history_id)
            if history:
                status = history.get('status', {})
                messages = status.get('messages', [])
                if status.get('status_str') == 'error' or any(m[0] in ('execution_error', 'execution_interrupted') for m in messages if isinstance(m, list) and m):
                    job.state, job.message = 'failed', 'Worker báo lỗi thực thi hoặc tác vụ bị ngắt. Chủ worker cần kiểm tra VRAM, model và log ComfyUI.'
                elif status.get('completed') is True:
                    node = history.get('outputs', {}).get(job.output_node, {})
                    items = [item for key in ('videos', 'gifs', 'images') for item in node.get(key, []) if isinstance(item, dict) and str(item.get('filename', '')).lower().endswith('.mp4')]
                    if not items:
                        job.state, job.message = 'failed', 'Workflow hoàn tất nhưng không trả MP4 ở output node đã cấu hình. Không dùng ảnh/GIF thay thế.'
                    else:
                        try:
                            job.output = safe_file(items[0])
                        except StudioError as exc:
                            job.state, job.message = 'failed', str(exc)
                            return job
                        job.remote_id = history_id
                        job.state, job.message = 'complete', 'Worker trả MP4; có thể tải và kiểm tra media.'
                return job
            queue = self._json('GET', 'queue')
            for key, state in (('queue_running', 'running'), ('queue_pending', 'queued')):
                for entry in queue.get(key, []):
                    if not isinstance(entry, list) or len(entry) < 4:
                        continue
                    if entry[1] == history_id or (isinstance(entry[3], dict) and entry[3].get('client_id') == job.id):
                        if valid_id(entry[1]):
                            job.remote_id = entry[1]
                            job.state = state
                            job.message = 'Worker đang sinh video' if state == 'running' else 'Đang chờ trong hàng đợi worker'
                            return job
            job.state, job.message = ('submission_unknown' if job.remote_id is None else 'missing'), 'Chưa thấy trong hàng đợi/lịch sử. Có thể worker vừa chuyển trạng thái, khởi động lại hoặc xóa history; không tự gửi lại.'
        except NetworkError as exc:
            job.message = str(exc)  # Keep the remote state; a network failure is not a GPU failure.
        except (ValueError, TypeError, AttributeError, KeyError, IndexError) as exc:
            if isinstance(exc, StudioError):
                raise
            raise StudioError('Queue/history của worker không đúng định dạng ComfyUI.') from exc
        return job

    def download(self, job):
        if job.worker != self.config.identity or job.state != 'complete' or not job.output:
            raise StudioError('Cần đúng worker và một tác vụ có MP4 hoàn tất để tải.')
        descriptor = safe_file(job.output)
        data = self._read('GET', 'view', limit=MAX_MEDIA_BYTES, params=descriptor)
        if len(data) < 12 or data[4:8] != b'ftyp':
            raise StudioError('Kết quả không phải MP4 hợp lệ; không có video thay thế.')
        seconds = validate_upload(data, 'video')
        if seconds < 1:
            raise StudioError('Clip AI ngắn hơn 1 giây; không tự kéo dài bằng ảnh tĩnh. Kiểm tra workflow trên worker.')
        if seconds > 60:
            raise StudioError('Clip AI nhận về vượt 60 giây/cảnh. Cần kiểm tra workflow trên worker.')
        job.data, job.actual_seconds, job.state = data, seconds, 'downloaded'
        job.message = 'Đã tải và kiểm tra MP4 từ worker. Hãy xem nội dung trước khi đưa vào timeline.'
        return job


def resume(job, wait_seconds):
    if job.state in ('timed_out', 'paused', 'missing', 'submission_unknown'):
        job.state, job.deadline = 'queued', time.time()+wait_seconds
        job.message = 'Tiếp tục theo dõi tác vụ cũ; không gửi workflow mới'
