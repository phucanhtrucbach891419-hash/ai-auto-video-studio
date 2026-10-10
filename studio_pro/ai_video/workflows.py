"""Trusted API-format ComfyUI workflows with explicit input bindings."""
import copy
import hashlib
import io
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image
from studio import StudioError, prepare_image
from studio_pro.models import bounded


@dataclass
class VideoRequest:
    scene_id: str
    mode: str
    action: str
    character: str = ''
    setting: str = ''
    camera: str = ''
    seconds: float = 5
    ratio: str = '16:9'
    seed: int = 0
    image: bytes | None = field(default=None, repr=False)

    def validate(self):
        if self.mode not in ('t2v', 'i2v') or self.ratio not in ('9:16', '16:9', '1:1'):
            raise StudioError('Chế độ/tỷ lệ AI video không hợp lệ.')
        for name, value, limit in [('Hành động', self.action, 2000), ('Nhân vật', self.character, 500), ('Bối cảnh', self.setting, 500), ('Camera', self.camera, 500)]:
            if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 and c not in '\n\t' for c in value):
                raise StudioError(f'{name} không hợp lệ hoặc quá {limit} ký tự.')
        if not self.action.strip():
            raise StudioError('Hãy mô tả hành động/chuyển động thật cần tạo.')
        bounded(self.seconds, 1, 10, 'Thời lượng clip AI')
        if not isinstance(self.seed, int) or isinstance(self.seed, bool) or not 0 <= self.seed <= 2**32-1:
            raise StudioError('Seed cần là số nguyên từ 0 đến 4.294.967.295.')
        if self.mode == 'i2v' and not self.image:
            raise StudioError('Image-to-video cần ảnh tham chiếu; không dùng ảnh demo thay thế.')

    @property
    def prompt(self):
        return '. '.join(value.strip() for value in (self.action, self.character, self.setting, self.camera) if value.strip())


@dataclass
class WorkflowProfile:
    id: str
    label: str
    mode: str
    graph: dict
    bindings: dict
    output_node: str
    fps: int = 16
    frame_step: int = 4
    max_seconds: int = 5
    sizes: dict = field(default_factory=lambda: {'16:9': [832, 480], '9:16': [480, 832], '1:1': [512, 512]})

    @property
    def signature(self):
        return hashlib.sha256(json.dumps(self.__dict__, sort_keys=True).encode()).hexdigest()

    def validate(self):
        if self.mode not in ('t2v', 'i2v') or not self.graph or len(self.graph) > 200:
            raise StudioError('Workflow phải có 1–200 node ở định dạng API của ComfyUI.')
        if self.output_node not in self.graph or self.graph[self.output_node].get('class_type') not in ('SaveVideo', 'VHS_VideoCombine'):
            raise StudioError('Workflow cần output node SaveVideo hoặc VHS_VideoCombine xuất MP4.')
        for node in self.graph.values():
            if not isinstance(node, dict) or not isinstance(node.get('class_type'), str) or not isinstance(node.get('inputs'), dict):
                raise StudioError('Workflow không phải đồ thị API hợp lệ; không dùng JSON giao diện ComfyUI.')
            if any(word in node['class_type'].lower() for word in ('api', 'kling', 'veo', 'runway', 'minimax')):
                raise StudioError('Profile này chỉ cho phép workflow mô hình local trên worker, không dùng node API trả phí.')
        required = {'prompt', 'seed', 'width', 'height', 'frames', 'fps', 'prefix'} | ({'image'} if self.mode == 'i2v' else set())
        if not required <= self.bindings.keys():
            raise StudioError('Workflow thiếu ánh xạ prompt/seed/kích thước/frames/fps/prefix/ảnh.')
        for binding in self.bindings.values():
            if not isinstance(binding, list) or len(binding) != 2 or binding[0] not in self.graph or binding[1] not in self.graph[binding[0]]['inputs']:
                raise StudioError('Ánh xạ node/input của workflow không hợp lệ.')
        if not 1 <= self.fps <= 60 or self.frame_step not in (4, 8) or not 1 <= self.max_seconds <= 10:
            raise StudioError('FPS, bước khung hình hoặc giới hạn clip của profile không hợp lệ.')
        for ratio in ('16:9', '9:16', '1:1'):
            size = self.sizes.get(ratio, [])
            if len(size) != 2 or any(not isinstance(n, int) or n < 128 or n > 1280 or n % 16 for n in size):
                raise StudioError('Kích thước workflow cần bội số 16, từ 128 đến 1280.')
        return self

    def parameters(self, request):
        request.validate()
        if request.mode != self.mode or request.seconds > self.max_seconds:
            raise StudioError(f'Profile {self.label} hỗ trợ {self.mode}, tối đa {self.max_seconds} giây/clip.')
        frames = math.ceil((request.seconds*self.fps-1)/self.frame_step)*self.frame_step+1
        width, height = self.sizes[request.ratio]
        return {'prompt': request.prompt, 'seed': request.seed, 'width': width, 'height': height, 'frames': frames, 'fps': self.fps}, frames/self.fps

    def build(self, request, job_id, image_name=None):
        self.validate()
        values, actual = self.parameters(request)
        values['prefix'] = 'studio/'+job_id
        if self.mode == 'i2v':
            if not image_name:
                raise StudioError('Ảnh tham chiếu chưa được tải thành công lên worker.')
            values['image'] = image_name
        graph = copy.deepcopy(self.graph)
        for name, value in values.items():
            node, key = self.bindings[name]
            graph[node]['inputs'][key] = value
        return graph, actual


def load_profiles(catalog):
    """Read only operator-installed files, never arbitrary browser-uploaded workflows."""
    path = Path(catalog).resolve()
    try:
        if path.stat().st_size > 1024*1024:
            raise StudioError('Catalog workflow quá lớn.')
        entries = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(entries, list) or len(entries) > 12:
            raise StudioError('Catalog cần danh sách tối đa 12 profile.')
        profiles = []
        for entry in entries:
            entry = dict(entry)
            graph_path = (path.parent / entry.pop('workflow')).resolve()
            if not graph_path.is_relative_to(path.parent) or graph_path.stat().st_size > 1024*1024:
                raise StudioError('Workflow cần nằm trong thư mục catalog, tối đa 1 MB.')
            graph = json.loads(graph_path.read_text(encoding='utf-8'))
            profile = WorkflowProfile(graph=graph, **entry).validate()
            profiles.append(profile)
        if len({p.id for p in profiles}) != len(profiles):
            raise StudioError('ID profile bị trùng.')
        return profiles
    except (OSError, ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, StudioError):
            raise
        raise StudioError('Không đọc được catalog/workflow. Chủ ứng dụng cần kiểm tra cấu hình JSON.') from exc


def reference_png(request, profile):
    width, height = profile.sizes[request.ratio]
    image = prepare_image(request.image, (width, height))
    buffer = io.BytesIO()
    image.save(buffer, 'PNG')
    return buffer.getvalue()
