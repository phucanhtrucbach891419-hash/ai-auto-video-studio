# Xác minh Giai đoạn A — 09/10/2026

## Môi trường và kết quả thực tế

Python 3.12.14, Streamlit 1.50.0, Pillow 11.3.0, FFmpeg/FFprobe 7.1.5 trên Debian. Edge TTS 7.2.3 được cài; `pip check` không có xung đột. `compileall` và `git diff --check` đạt.

`python -m unittest discover -s tests -v`: **17/17 kiểm thử đạt**, khoảng 93 giây, gồm 6 kiểm thử cũ giữ nguyên và 11 kiểm thử Pro.

| Phạm vi | Bằng chứng |
| --- | --- |
| Hồi quy bản cơ bản | Chia cảnh, nhập/chỉnh nội dung, nút xuất demo, vô hiệu hóa kết quả cũ và thiếu media; xuất/giải mã 30/60/90s, MP3 ngắn/dài |
| Video Pro dài | Dựng thực 30s 9:16, 60s 16:9, 90s 1:1, Ken Burns và phụ đề; FFprobe xác nhận kích thước/codec/thời lượng; FFmpeg giải mã toàn bộ output |
| Chuyển động | So sánh pixel khung hình đầu/cuối: static gần như không đổi, zoom/pan/Ken Burns có khác biệt rõ |
| Chuyển cảnh, phụ đề | Khung đầu fade đen; khung giữa có hình; vùng phụ đề khác ảnh gốc sau burn SRT tiếng Việt đã chỉnh |
| Giọng đọc/nhạc | Giải mã AAC thành mẫu float: tốc độ 2x, khoảng im lặng đúng cảnh, volume 0, nhạc ngắn lặp, fade đầu/cuối. Có kiểm thử chống lỗi DC offset của anullsrc 8-bit qua atempo |
| Clip, 1080p | Clip nguồn 0,5s giữ hình cuối đến hết cảnh 1s, xuất 1920×1080 H.264/AAC và giải mã thành công |
| Dữ liệu/lỗi | SRT sai mốc/thứ tự/chồng lấn bị từ chối; escape ASS; media không hợp lệ; 4K bị khóa trên Cloud; tốc độ/thời lượng không hợp lệ; cleanup khi lỗi và khóa tác vụ được giải phóng; timeout rõ ràng |
| TTS và chi phí | Mock kiểm tra không gọi khi chưa bật, lỗi dịch vụ có phương án MP3/WAV, voice ID không hợp lệ bị từ chối; provider trả phí cần bật mạng + chấp thuận chi phí |
| Giao diện Pro | AppTest đổi thời lượng/thứ tự cảnh, cập nhật/sửa SRT, xuất thật, ẩn output cũ, thiếu giọng làm nút xuất bị khóa, trở về bản cơ bản không lỗi |

## Kiểm thử Chromium thật

Đã chạy `tests/browser_smoke.py` với Chromium hệ thống, Playwright 1.63.0 và máy chủ Streamlit cục bộ:

- Mở bản cơ bản, chọn Pro, chia cảnh, chỉnh 3 cảnh về 1 giây/cảnh, tạo lại SRT, xuất, xem trước và tải xuống.
- MP4 tải xuống **767.963 bytes**; metadata trình phát 720×1280, 3 giây. Đã gọi play/pause thành công. FFprobe xác nhận H.264/AAC và 3 giây.
- Dark mode có màu nền `rgb(14, 17, 27)`; xem ảnh chụp màn hình để kiểm tra bố cục.
- Không có JavaScript page error, không có Streamlit exception, không tràn ngang tại viewport 1440×1000.
- Endpoint `/_stcore/health` trả `ok`, log server cuối không có traceback.

Các lần chạy trước phát hiện Streamlit telemetry cố ghi machine ID vào home chỉ đọc, gây lỗi gửi cấu hình đầu phiên. Đã đặt `browser.gatherUsageStats=false` và `theme.base="dark"`; không cần ghi vào home. Đã xác minh lại bằng máy chủ mới và Chromium sau sửa.

Để chạy lại (không cần đưa Playwright vào dependencies triển khai Cloud):

```bash
pip install -r requirements-dev.txt
# Nếu chưa có Chromium:
python -m playwright install chromium
streamlit run app.py --server.port 8501
# Terminal khác:
python tests/browser_smoke.py --url http://127.0.0.1:8501
# Nếu dùng Chromium hệ thống:
python tests/browser_smoke.py --url http://127.0.0.1:8501 --browser-path /usr/bin/chromium
```

Script lưu ảnh chụp và MP4 dưới `work/browser/` (không commit Git). Kiểm thử trình duyệt này kiểm tra một video Pro ngắn; kiểm thử FFmpeg riêng ở trên bao phủ 30/60/90s và 1080p.

## Chưa xác minh hoặc chưa triển khai

- **Chưa gọi Edge TTS live**: chỉ kiểm tra adapter bằng mock và phương án lỗi, không tuyên bố dịch vụ đang hoạt động trong mạng này. Mạng hiện tại không cho phép đích Edge TTS; tính khả dụng cần kiểm tra trên máy/server triển khai.
- **Chưa render 4K**: đã kiểm tra kích thước cấu hình và điều kiện bật, chưa chứng minh tài nguyên/codec ở 4K.
- **Chưa triển khai/xác minh trên Streamlit Community Cloud**: có requirements/packages/config phù hợp và hướng dẫn; vẫn cần staging thực tế ở D. Health và Chromium cục bộ không thay thế Cloud.
- **B–D chưa hoàn thành**: không có dashboard 10 mục, mẫu/LLM kịch bản, thư viện dự án, ZIP/lưu bền vững, provider AI ảnh/video trả phí hoặc job worker từ xa. Không có nút giả cho các phần này. Lộ trình và phương án lưu bền vững nằm trong PRO_PLAN.md.
