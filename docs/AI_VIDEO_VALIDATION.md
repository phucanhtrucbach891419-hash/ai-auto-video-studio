# Xác minh AI Video Generator (09/10/2026)

## Đã kiểm thử

Môi trường Python 3.12, Streamlit 1.50, FFmpeg 7.1.5 và Chromium trong workspace Linux. Không có GPU worker/model weights hoặc khóa dịch vụ trả phí được cấu hình.

- `python -m unittest discover -s tests -v`: **28/28 kiểm thử đạt**, gồm 17 kiểm thử A/bản cơ bản và 11 kiểm thử mới cho connector/giao diện. Thời gian chạy toàn bộ 93,733 giây; sau khi gia cố cấu hình URL/token và schema GPU, chạy lại 11/11 kiểm thử connector đạt (2,225 giây). Bộ kiểm thử dùng workflow/profile thật của repository nhưng API trả lời bằng fixture, không phải GPU inference.
- Hợp đồng T2V/I2V, bindings/frames/kích thước, ảnh conditioning được chuẩn hóa thật, chặn workflow node API được nhận diện, chế độ mặc định không gửi request.
- Queue → running → complete → tải MP4; lỗi worker, HTTP timeout/5xx, nhận phản hồi không rõ, deadline, thiếu output, đường dẫn không an toàn, giới hạn tải, redirect và lỗi xác thực. Không retry POST khi có thể đã nhận job.
- HTTP loopback thực với `requests`, Bearer auth, GET/POST và stream tải MP4, sau đó FFprobe và đưa clip vào backend FFmpeg A. **Clip test được sinh bằng FFmpeg testsrc2, chỉ dùng trong kiểm thử; không phải clip AI.**
- Streamlit AppTest: chưa có worker thì không gọi mạng hoặc tạo kết quả; không thể xuất cảnh GPU thiếu clip; chế độ phim chặn ảnh; kết nối → gửi → nhận → đưa clip vào đúng cảnh, cập nhật thời lượng. API fixture chỉ dùng trong test, app sản xuất không có mock/demo AI video.
- Chromium thật: luồng A vẫn xuất, xem/phát và tải MP4 3 giây, 720×1280; file tải 767.963 bytes; dark mode đúng, không lỗi JavaScript/Streamlit và không tràn ngang. Kiểm tra riêng thấy cảnh báo chưa kết nối và chế độ phim vô hiệu hóa nút xuất khi còn ảnh.
- `pip check` và `git diff --check` đạt. `app.py`, `studio.py`, backend media/subtitles/TTS A giữ nguyên.

## Chưa xác minh

- **Chưa gửi tác vụ tới ComfyUI/GPU thật; chưa tạo được clip Wan/LTX thật và chưa chứng minh nhân vật/bối cảnh chuyển động.** Hai workflow Wan native là mẫu cấu hình, không phải workflow đã được chạy GPU.
- Chưa triển khai proxy Caddy hoặc worker thực; chưa xác minh HTTPS từ Streamlit Community Cloud/staging. Kiểm thử cục bộ không bảo đảm GPU, quota, RAM/VRAM hoặc tài nguyên Cloud thực tế.
- LTX chỉ có cơ chế thêm workflow export/profile; không có profile LTX đã chạy GPU. ZeroGPU không có adapter. Edge TTS live/4K tiếp tục chưa kiểm thử như A.
- Animated titles, kinetic typography, phụ đề động, chuyển cảnh overlap và project ZIP nằm trong thiết kế PR sau, không có nút chức năng giả trong bản này.

## Chạy lại

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
# Chromium cài sẵn hoặc browser Playwright đã được cài
pip install -r requirements-dev.txt
streamlit run app.py --server.headless true --server.port 8505
# Trong terminal khác:
python tests/browser_smoke.py --url http://127.0.0.1:8505 --browser-path /usr/bin/chromium
```

HTTP integration test mở socket loopback; cần môi trường cho phép bind localhost. Browser smoke kiểm tra bộ dựng A không cần worker. AppTest mới kiểm tra trạng thái chưa kết nối/chế độ phim và luồng quản lý tác vụ bằng fixture. Các file screenshot/video test đặt trong `work/`, không commit media giả thành mẫu phim AI.

Nghiệm thu inference thật yêu cầu worker được cấp quyền, chạy workflow trước, tạo T2V và I2V qua HTTPS từ app, xem đủ clip để kiểm tra chuyển động, ghi GPU/model/version/seed/runtime/hash và xuất cuối qua timeline. Xem [điều kiện nghiệm thu](AI_VIDEO_PLAN.md#điều-kiện-nghiệm-thu-inference-thật) và [triển khai worker](../worker/README.md).
