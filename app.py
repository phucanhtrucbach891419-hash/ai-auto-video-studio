import hashlib
import shutil
import tempfile

import streamlit as st

from studio import SIZES, StudioError, demo_image, prepare_image, render_video, split_script

st.set_page_config(page_title="AI Auto Video Studio", page_icon="🎬", layout="wide")
st.markdown("""<style>
.block-container {max-width:1200px;padding-top:2rem;}
h1 {letter-spacing:-1.5px;}
.stButton>button {border-radius:12px;min-height:44px;}
[data-testid="stMetric"] {background:#191D2E;padding:18px;border-radius:16px;}
</style>""", unsafe_allow_html=True)
with st.sidebar:
    editor = st.selectbox("Bộ dựng video", ["Bản cơ bản", "Pro · Giai đoạn A"], key="studio_editor")
if editor == "Pro · Giai đoạn A":
    from studio_pro.ui import main
    main()
    st.stop()

st.caption("🎬 XƯỞNG VIDEO • PHIÊN BẢN ĐẦU TIÊN")
st.title("Biến ý tưởng thành video")
st.write("Lên kịch bản, thêm hình ảnh và giọng đọc — xuất video của bạn trong một không gian.")
with st.sidebar:
    st.header("Cài đặt video")
    demo = st.toggle("Chế độ demo", value=True)
    duration = st.selectbox("Thời lượng (giây)", [30, 60, 90])
    ratio = st.radio("Tỷ lệ khung hình", list(SIZES), horizontal=True)
    st.caption("9:16 · video dọc\n\n16:9 · video ngang\n\n1:1 · video vuông")
    st.info("Demo chạy ngoại tuyến, dùng ảnh đồ họa tự tạo và âm thanh im lặng nếu chưa tải MP3. Chưa tích hợp AI tạo nội dung hoặc giọng đọc.")
    if not shutil.which("ffmpeg"):
        st.error("Máy chủ cần cài FFmpeg để xuất video.")

st.subheader("01 · Ý tưởng & kịch bản")
topic = st.text_input("Chủ đề video", value="Một ngày sống xanh", max_chars=100)
content = st.text_area("Nội dung video", value="Bắt đầu ngày mới với những thói quen nhỏ. Mang theo bình nước cá nhân để giảm chai nhựa. Chọn đi bộ cho những quãng đường gần. Tận dụng ánh sáng tự nhiên và tiết kiệm điện. Phân loại rác và tái sử dụng đồ dùng. Mỗi hành động hôm nay góp phần tạo nên một tương lai xanh hơn.", height=150, max_chars=12000)
st.caption("Kịch bản được chia tự động theo nhóm từ, thời lượng chia đều cho các cảnh. Có thể sửa nội dung từng cảnh bên dưới.")
fingerprint = hashlib.sha256(f"{topic}|{content}|{duration}|{ratio}".encode()).hexdigest()
if st.button("✦ Chia kịch bản thành cảnh", type="primary", use_container_width=True):
    try:
        if not topic.strip():
            raise StudioError("Vui lòng nhập chủ đề video.")
        st.session_state.scenes = split_script(content, duration)
        st.session_state.source = fingerprint
        st.session_state.revision = st.session_state.get("revision", 0) + 1
        st.session_state.pop("video", None)
    except StudioError as exc:
        st.error(str(exc))

scenes = st.session_state.get("scenes", [])
if scenes and st.session_state.get("source") != fingerprint:
    st.warning("Cài đặt hoặc kịch bản đã thay đổi. Hãy chia lại cảnh để tiếp tục.")
    st.stop()
if not scenes:
    st.info("Bắt đầu bằng cách nhập ý tưởng và nhấn “Chia kịch bản thành cảnh”.")
    st.stop()

cols = st.columns(3)
cols[0].metric("Số cảnh", len(scenes))
cols[1].metric("Thời lượng", f"{duration} giây")
cols[2].metric("Khung hình", ratio)
st.subheader("02 · Hình ảnh cho từng cảnh")
st.caption("Tải ảnh từ máy tính (PNG, JPG, WebP; tối đa 15 MB/ảnh). Ảnh được cắt giữa để vừa khung hình. Nội dung cảnh dùng để lên kế hoạch, chưa được chèn thành phụ đề.")
images, edited, valid = [], [], True
revision = st.session_state.revision
for i, scene in enumerate(scenes):
    with st.container(border=True):
        left, right = st.columns([1, 3])
        with right:
            st.markdown(f"**Cảnh {i + 1:02d} · {duration / len(scenes):.1f} giây**")
            text = st.text_area(f"Nội dung cảnh {i + 1}", value=scene, key=f"scene-{revision}-{i}", height=90, max_chars=12000)
            edited.append(text)
            upload = st.file_uploader(f"Ảnh cảnh {i + 1}", type=["png", "jpg", "jpeg", "webp"], key=f"image-{revision}-{i}")
        try:
            if upload:
                img = prepare_image(upload.getvalue(), SIZES[ratio])
            elif demo:
                img = demo_image(topic, i, SIZES[ratio])
            else:
                img = None
                valid = False
                right.warning("Hãy tải ảnh cho cảnh này.")
            if img is not None:
                left.image(img, width="stretch")
                images.append(img)
        except StudioError as exc:
            right.error(str(exc))
            valid = False

st.subheader("03 · Giọng đọc & xuất video")
audio = st.file_uploader("Tải giọng đọc MP3 (tối đa 25 MB)", type=["mp3"])
audio_bytes = audio.getvalue() if audio else None
if audio_bytes:
    st.audio(audio_bytes, format="audio/mpeg")
if not audio and not demo:
    st.warning("Hãy tải MP3 hoặc bật chế độ demo để dùng âm thanh im lặng.")
    valid = False
st.caption("MP3 ngắn hơn video sẽ được thêm khoảng im lặng; MP3 dài hơn sẽ được cắt theo thời lượng đã chọn. Không thay đổi tốc độ giọng đọc.")
# Hide stale output whenever any input to the rendered video changes.
digest = hashlib.sha256(f"{fingerprint}|{demo}|{edited}".encode())
for img in images:
    digest.update(img.tobytes())
digest.update(audio_bytes or b"")
render_key = digest.hexdigest()
if st.session_state.get("render_key") != render_key:
    st.session_state.pop("video", None)
if st.button("🎬 Tạo video MP4", type="primary", disabled=not valid, use_container_width=True):
    bar = st.progress(0, text="Đang xử lý các cảnh…")
    try:
        with tempfile.TemporaryDirectory(prefix="video-studio-") as directory:
            video = render_video(images, audio_bytes, duration, ratio, directory, lambda p: bar.progress(p, text="Đang ghép video…"))
        st.session_state.video = video
        st.session_state.render_key = render_key
        st.success("Đã xuất video. Bạn có thể xem trước và tải xuống bên dưới.")
    except StudioError as exc:
        st.error(str(exc))
    finally:
        bar.empty()
if st.session_state.get("video"):
    st.subheader("04 · Video của bạn")
    st.video(st.session_state.video)
    st.download_button("↓ Tải video MP4", st.session_state.video, "video-hoan-chinh.mp4", "video/mp4", use_container_width=True)
st.caption("AI Auto Video Studio · Dữ liệu được xử lý trên máy chủ Streamlit. Tệp tạm được xóa sau mỗi lần xuất; video lưu trong phiên hiện tại.")
