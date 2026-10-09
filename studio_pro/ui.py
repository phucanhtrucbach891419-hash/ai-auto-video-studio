"""Working phase-A editor, separate from the original Streamlit workflow."""
import hashlib
from dataclasses import asdict

import streamlit as st

from studio import StudioError, demo_image, prepare_image, split_script
from .media import render, validate_upload
from .models import RenderSettings, Scene, dimensions, four_k_enabled, local_profile, validate_timeline
from .subtitles import make_cues, parse_srt, to_srt
from .tts import VOICES, synthesize

MOTION_LABELS = {'Đứng yên': 'static', 'Zoom chậm': 'zoom', 'Pan ngang': 'pan', 'Ken Burns': 'ken_burns'}
DEFAULT_TEXT = 'Bắt đầu ngày mới với những thói quen nhỏ. Mang theo bình nước cá nhân để giảm chai nhựa. Chọn đi bộ cho những quãng đường gần. Tận dụng ánh sáng tự nhiên và tiết kiệm điện. Phân loại rác và tái sử dụng đồ dùng. Mỗi hành động hôm nay góp phần tạo nên một tương lai xanh hơn.'


def signature(text, voice):
    return hashlib.sha256(f'{text}|{voice}'.encode()).hexdigest()


def render_signature(scenes, settings, topic, narration, music, srt):
    digest = hashlib.sha256(f'{asdict(settings)}|{topic}|{srt}'.encode())
    # Explicit boundaries so different media arrangements cannot hash identically.
    for scene in scenes:
        digest.update(repr((scene.text, scene.duration, scene.motion)).encode())
        for data in (scene.image, scene.video, scene.voice):
            digest.update(hashlib.sha256(data or b'').digest())
    for data in (narration, music):
        digest.update(hashlib.sha256(data or b'').digest())
    return digest.hexdigest()


def main():
    st.markdown('<style>.block-container {padding-top:4rem;}</style>', unsafe_allow_html=True)
    st.caption('🎬 AI AUTO VIDEO STUDIO PRO · GIAI ĐOẠN A')
    st.title('Dựng video theo cách của bạn')
    st.write('Chuyển động, giọng đọc, nhạc nền và phụ đề — bộ dựng miễn phí, không cần API key.')
    st.info('Bộ dựng Pro A đã có chức năng thực. Dashboard 10 mục, mẫu kịch bản, thư viện ZIP và AI tạo ảnh/video thuộc các giai đoạn tiếp theo, chưa hỗ trợ trong bản này. Dữ liệu hiện chỉ ở phiên làm việc; hãy tải MP4/SRT trước khi đóng phiên.')
    with st.sidebar:
        st.header('Cấu hình Pro')
        ratio = st.radio('Tỷ lệ Pro', ['9:16', '16:9', '1:1'], horizontal=True, key='pro_ratio')
        choices = ['720p', '1080p'] + (['4K'] if four_k_enabled() else [])
        resolution = st.selectbox('Độ phân giải', choices, key='pro_resolution')
        transition = st.slider('Chuyển cảnh qua nền đen (giây)', 0.0, 1.0, .25, .05, key='pro_transition')
        burn = st.checkbox('Gắn phụ đề trực tiếp vào video', value=True, key='pro_burn')
        st.caption('24 fps · H.264/AAC. 1080p tốn nhiều tài nguyên hơn 720p. Chuyển cảnh fade qua nền đen giữ nguyên tổng thời lượng.')
        st.caption('Profile: máy cá nhân/server' if local_profile() else 'Profile: Cloud · tối đa 9 cảnh / 90 giây')
        if not four_k_enabled():
            st.caption('4K đang khóa; chỉ bật bằng cấu hình môi trường local trên máy đủ tài nguyên.')
    st.subheader('01 · Kịch bản')
    topic = st.text_input('Chủ đề Pro', 'Một ngày sống xanh', max_chars=100, key='pro_topic')
    script = st.text_area('Kịch bản có sẵn', DEFAULT_TEXT, height=130, max_chars=12000, key='pro_script')
    duration = st.selectbox('Thời lượng ban đầu (giây)', [30, 60, 90], key='pro_initial_duration')
    source = hashlib.sha256(f'{topic}|{script}|{duration}'.encode()).hexdigest()
    if st.button('Chia cảnh Pro', type='primary', key='pro_split'):
        try:
            if not topic.strip():
                raise StudioError('Vui lòng nhập chủ đề.')
            texts = split_script(script, duration)
            st.session_state.pro_scenes = texts
            st.session_state.pro_source = source
            st.session_state.pro_revision = st.session_state.get('pro_revision', 0) + 1
            st.session_state.pop('pro_result', None)
            st.session_state.pop('pro_tts', None)
            st.session_state.pop('pro_srt_source', None)
        except StudioError as exc:
            st.error(str(exc))
    texts = st.session_state.get('pro_scenes', [])
    if not texts:
        st.info('Nhập kịch bản rồi nhấn “Chia cảnh Pro” để bắt đầu.')
        return
    if source != st.session_state.pro_source:
        st.warning('Kịch bản hoặc thời lượng ban đầu đã thay đổi. Hãy chia lại cảnh; thao tác này thay thế các chỉnh sửa cảnh hiện tại.')
        st.session_state.pop('pro_result', None)
        return

    st.subheader('02 · Giọng đọc & âm thanh')
    voice_mode = st.radio('Nguồn giọng đọc', ['Không có giọng đọc', 'MP3/WAV toàn video', 'Giọng theo cảnh'], key='pro_voice_mode')
    voice_label = st.selectbox('Giọng Edge TTS tiếng Việt', list(VOICES), key='pro_edge_voice')
    enabled = st.checkbox('Cho phép gửi nội dung đến Edge TTS qua mạng', value=False, key='pro_edge_enabled')
    st.caption('Edge TTS là dịch vụ mạng tùy chọn, có thể không khả dụng. Chỉ gửi nội dung khi nhấn “Tạo giọng cảnh”; không phải giọng offline và không gọi API trả phí. Tốc độ bên dưới áp dụng lúc ghép video.')
    audio_cols = st.columns(3)
    speed = audio_cols[0].slider('Tốc độ giọng đọc', .5, 2.0, 1.0, .05, key='pro_speed')
    voice_volume = audio_cols[1].slider('Âm lượng giọng đọc', 0.0, 2.0, 1.0, .05, key='pro_voice_volume')
    music_volume = audio_cols[2].slider('Âm lượng nhạc nền', 0.0, 1.0, .15, .05, key='pro_music_volume')
    fade = st.slider('Fade in/out âm thanh (giây)', 0.0, 5.0, 1.0, .25, key='pro_audio_fade')
    narration = None
    valid = True
    if voice_mode == 'MP3/WAV toàn video':
        uploaded = st.file_uploader('Lời đọc toàn video · MP3/WAV · tối đa 25 MB', type=['mp3', 'wav'], key='pro_narration')
        if uploaded:
            narration = uploaded.getvalue()
            st.audio(narration)
        else:
            st.warning('Hãy tải lời đọc hoặc chọn nguồn giọng khác.')
            valid = False
    music_upload = st.file_uploader('Nhạc nền tùy chọn · MP3/WAV · tối đa 25 MB', type=['mp3', 'wav'], key='pro_music')
    music = music_upload.getvalue() if music_upload else None
    st.caption('Nhạc ngắn sẽ lặp. Giọng đọc ngắn được thêm im lặng; giọng dài hơn cảnh/video sẽ bị cắt và có cảnh báo sau khi xuất. Hãy tăng thời lượng cảnh nếu cần giữ toàn bộ lời đọc.')

    st.subheader('03 · Cảnh & timeline')
    st.caption('Chỉnh vị trí để đổi thứ tự; mỗi vị trí phải khác nhau. Media luôn đi cùng cảnh. Không có ảnh sẽ dùng nền đồ họa. Với MP4, âm thanh gốc bị bỏ, clip ngắn giữ khung hình cuối; hiệu ứng chuyển động chỉ áp dụng cho ảnh.')
    entries = []
    revision = st.session_state.pro_revision
    tts_store = st.session_state.setdefault('pro_tts', {})
    for i, text in enumerate(texts):
        prefix = f'pro_{revision}_{i}'
        with st.container(border=True):
            st.markdown(f'**Cảnh gốc {i+1:02d}**')
            controls = st.columns(3)
            order = controls[0].number_input(f'Vị trí cảnh {i+1}', 1, len(texts), i+1, key=prefix+'_order')
            seconds = controls[1].number_input(f'Thời lượng cảnh {i+1} (giây)', 1.0, 60.0, float(duration/len(texts)), .25, key=prefix+'_seconds')
            motion_label = controls[2].selectbox(f'Chuyển động cảnh {i+1}', list(MOTION_LABELS), index=3, key=prefix+'_motion')
            scene_text = st.text_area(f'Lời đọc / phụ đề cảnh {i+1}', text, height=90, max_chars=12000, key=prefix+'_text')
            kind = st.radio(f'Hình ảnh cảnh {i+1}', ['Ảnh hoặc nền đồ họa', 'Clip MP4'], horizontal=True, key=prefix+'_kind')
            image_data, video_data, voice_data = None, None, None
            if kind == 'Clip MP4':
                uploaded = st.file_uploader(f'Clip cảnh {i+1} · tối đa 25 MB', type=['mp4'], key=prefix+'_video')
                if uploaded:
                    video_data = uploaded.getvalue()
                else:
                    st.warning('Hãy tải MP4 cho cảnh này.')
                    valid = False
            else:
                uploaded = st.file_uploader(f'Ảnh cảnh Pro {i+1} · tối đa 15 MB', type=['png', 'jpg', 'jpeg', 'webp'], key=prefix+'_image')
                image_data = uploaded.getvalue() if uploaded else None
                try:
                    preview_size = dimensions(ratio, '720p')
                    img = prepare_image(image_data, preview_size) if image_data else demo_image(topic, i, preview_size)
                    st.image(img, width=180)
                except StudioError as exc:
                    st.error(str(exc))
                    valid = False
            if voice_mode == 'Giọng theo cảnh':
                uploaded_voice = st.file_uploader(f'Giọng cảnh {i+1} · MP3/WAV · tối đa 25 MB', type=['mp3', 'wav'], key=prefix+'_voice')
                key = signature(scene_text, VOICES[voice_label])
                if st.button(f'Tạo giọng cảnh {i+1}', disabled=not enabled, key=prefix+'_tts'):
                    try:
                        with st.spinner(f'Đang kết nối Edge TTS cho cảnh {i+1}…'):
                            data = synthesize(scene_text, VOICES[voice_label], enabled=enabled)
                            validate_upload(data, 'audio')
                        tts_store[i] = {'key': key, 'data': data}
                        st.success('Giọng đọc đã được tạo. Chỉ dùng trong phiên hiện tại.')
                    except StudioError as exc:
                        st.error(str(exc))
                generated = tts_store.get(i)
                if uploaded_voice:
                    voice_data = uploaded_voice.getvalue()
                elif generated and generated['key'] == key:
                    voice_data = generated['data']
                else:
                    st.warning('Tải MP3/WAV hoặc tạo giọng cảnh. Nếu sửa lời đọc/giọng, cần tạo lại âm thanh.')
                    valid = False
                if voice_data:
                    st.audio(voice_data)
                    st.download_button(f'Tải giọng cảnh {i+1}', voice_data, f'giong-canh-{i+1}.mp3' if not uploaded_voice else f'giong-canh-{i+1}.{uploaded_voice.name.rsplit(".",1)[-1].lower()}', key=prefix+'_voice_download')
            entries.append((order, i, Scene(scene_text, seconds, MOTION_LABELS[motion_label], image_data, video_data, voice_data)))
    if len({entry[0] for entry in entries}) != len(entries):
        st.error('Vị trí các cảnh đang trùng nhau. Mỗi cảnh cần một vị trí riêng trước khi xuất.')
        valid = False
    scenes = [entry[2] for entry in sorted(entries, key=lambda e: (e[0], e[1]))]
    settings = RenderSettings(ratio, resolution, transition, speed, voice_volume, music_volume, fade, burn)
    try:
        total = validate_timeline(scenes, settings)
    except StudioError as exc:
        st.error(str(exc))
        total = sum(s.seconds for s in scenes)
        valid = False
    offset, rows = 0.0, []
    for position, (_, original, scene) in enumerate(sorted(entries, key=lambda e: (e[0], e[1]))):
        rows.append({'Vị trí': position+1, 'Cảnh gốc': original+1, 'Bắt đầu (s)': round(offset, 3), 'Kết thúc (s)': round(offset+scene.seconds, 3), 'Lời đọc': scene.text[:100]})
        offset += scene.seconds
    st.dataframe(rows, hide_index=True, width="stretch")
    st.metric('Tổng timeline', f'{total:.2f} giây')

    st.subheader('04 · Phụ đề có thể chỉnh sửa')
    st.caption('Mốc tự sinh ước lượng theo kịch bản và thời lượng cảnh, chưa nhận dạng/alignment giọng nói. Bạn có thể sửa chữ và mốc SRT; không chồng lấn và không vượt timeline. Thay đổi timeline cần cập nhật SRT trước khi gắn vào video.')
    timeline_key = hashlib.sha256(repr([(s.text, s.frames) for s in scenes]).encode()).hexdigest()
    if 'pro_srt_source' not in st.session_state:
        st.session_state.pro_srt_editor = to_srt(make_cues(scenes))
        st.session_state.pro_srt_source = timeline_key
    if st.button('Tạo lại SRT theo timeline', key='pro_regenerate_srt'):
        st.session_state.pro_srt_editor = to_srt(make_cues(scenes))
        st.session_state.pro_srt_source = timeline_key
    srt = st.text_area('Biên tập SRT', height=220, key='pro_srt_editor', max_chars=60000)
    try:
        parse_srt(srt, total)
    except StudioError as exc:
        st.error(str(exc))
        valid = False
    if st.session_state.pro_srt_source != timeline_key:
        st.warning('Timeline/lời đọc đã thay đổi. “Tạo lại SRT” sẽ thay thế bản sửa, hoặc giữ bản sửa nếu bạn đã tự điều chỉnh mốc.')
        if st.button('Giữ SRT đã sửa cho timeline này', key='pro_keep_srt'):
            try:
                parse_srt(srt, total)
                st.session_state.pro_srt_source = timeline_key
                st.rerun()
            except StudioError as exc:
                st.error(str(exc))
        if burn:
            valid = False
    st.download_button('Tải phụ đề SRT', srt.encode('utf-8'), 'phu-de.srt', 'application/x-subrip', key='pro_download_srt')
    st.subheader('05 · Xuất & xem trước')
    digest = render_signature(scenes, settings, topic, narration, music, srt)
    if st.session_state.get('pro_render_key') != digest or not valid:
        st.session_state.pop('pro_result', None)
    if st.button('Xuất video Pro MP4', type='primary', disabled=not valid, key='pro_export', width="stretch"):
        bar = st.progress(0, text='Đang kiểm tra dữ liệu…')
        try:
            result = render(scenes, settings, topic, narration, music, srt, lambda p, msg: bar.progress(p, text=msg))
            st.session_state.pro_result = result
            st.session_state.pro_render_key = digest
            st.success('Đã xuất MP4 H.264/AAC. Xem trước và tải bên dưới.')
        except StudioError as exc:
            st.error(str(exc))
        finally:
            bar.empty()
    result = st.session_state.get('pro_result')
    if result:
        for warning in result.warnings:
            st.warning(warning)
        st.video(result.video)
        st.download_button('Tải video Pro MP4', result.video, 'video-pro.mp4', 'video/mp4', key='pro_download_video', width="stretch")
    st.caption('Ảnh, âm thanh và video được xử lý trên máy chủ. File tạm tự xóa sau xuất hoặc khi có lỗi. Chưa có lưu dự án lâu dài trong Giai đoạn A.')
