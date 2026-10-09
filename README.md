# AI Auto Video Studio

Ứng dụng Streamlit bằng tiếng Việt để tạo video từ kịch bản, ảnh và MP3. Phiên bản đầu tiên hoạt động không cần khóa API: chia cảnh bằng thuật toán nhóm từ, ảnh demo được vẽ bằng Pillow. **Chưa tích hợp mô hình AI, tìm ảnh trên Internet hoặc tạo giọng đọc.**

## Chạy trên máy tính

Yêu cầu Python 3.11 hoặc 3.12 và FFmpeg có bộ mã hóa `libx264`, AAC, kèm `ffprobe` trong PATH.

```bash
# Ubuntu / Debian
sudo apt-get update
sudo apt-get install ffmpeg fonts-dejavu-core
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Trên macOS cài FFmpeg bằng `brew install ffmpeg`. Trên Windows cài FFmpeg, thêm thư mục `bin` vào PATH, kích hoạt môi trường bằng `.venv\Scripts\activate`. Mở URL mà Streamlit hiển thị trong trình duyệt máy tính.

## Sử dụng

1. Nhập chủ đề và nội dung; chọn 30, 60 hoặc 90 giây và tỷ lệ 9:16, 16:9 hoặc 1:1.
2. Nhấn **Chia kịch bản thành cảnh**. Kịch bản được chia thành tối đa 3, 6 hoặc 9 nhóm từ liên tiếp, mỗi cảnh có thời lượng bằng nhau.
3. Sửa ghi chú từng cảnh và tải PNG/JPG/WebP. Nội dung cảnh chưa được chèn vào video thành phụ đề. Ảnh được cắt giữa để vừa khung hình.
4. Tải giọng đọc MP3. Tệp ngắn được thêm im lặng, tệp dài được cắt; tốc độ giọng đọc giữ nguyên.
5. Nhấn **Tạo video MP4**, xem trước rồi tải video.

Chế độ demo mặc định dùng ảnh đồ họa tạo tại chỗ và âm thanh im lặng khi chưa tải MP3. Muốn có giọng đọc, tải MP3 của bạn. Tắt demo yêu cầu đủ ảnh cho từng cảnh và một MP3 hợp lệ.

Thay đổi chủ đề, nội dung, thời lượng hoặc tỷ lệ yêu cầu chia lại cảnh. Thay đổi media hoặc ghi chú cảnh sẽ ẩn kết quả cũ để tránh tải nhầm video.

## Streamlit Community Cloud

Đưa repository lên GitHub, vào Streamlit Community Cloud, chọn repository/branch và entrypoint `app.py`, chọn Python 3.12 rồi triển khai. `requirements.txt` cung cấp thư viện Python; `packages.txt` cài FFmpeg và font tiếng Việt. Không cần Secrets hay dịch vụ trả phí. Chưa triển khai thực tế lên Community Cloud trong phiên lập trình; kiểm thử cục bộ không bảo đảm dung lượng và thời gian xử lý trên gói hosting của bạn.

## Kiểm thử

```bash
python -m unittest discover -s tests -v
```

Kiểm thử bao gồm chia cảnh không mất từ, ảnh không hợp lệ, luồng Streamlit và thay đổi đầu vào; xuất MP4 thực bằng FFmpeg với cả ba tỷ lệ và thời lượng; âm thanh demo, MP3 ngắn/dài; xác nhận codec, kích thước, thời lượng bằng FFprobe và giải mã toàn bộ video. Kiểm thử kết xuất cần FFmpeg và có thể mất vài phút. Kiểm thử dùng `streamlit.testing`, chưa thay thế kiểm tra trực quan trên trình duyệt hay kiểm tra triển khai Cloud.

## Cấu trúc và giới hạn

- `app.py`: giao diện và trạng thái phiên Streamlit.
- `studio.py`: chia cảnh, chuẩn hóa ảnh, kiểm tra MP3 và ghép video.
- `tests/test_studio.py`: kiểm thử thuật toán, giao diện và kết xuất.
- `.streamlit/config.toml`: giao diện tối và giới hạn tải tệp.

Xuất H.264/AAC, 24 fps, 720×1280 / 1280×720 / 720×720. Ảnh tối đa 15 MB và 25 triệu điểm ảnh; MP3 tối đa 25 MB; nội dung tối đa 12.000 ký tự. Chỉ ghép cảnh nối tiếp, chưa có hiệu ứng chuyển cảnh hoặc phụ đề. Xử lý FFmpeg có thời gian giới hạn cho từng tác vụ và dùng 2 luồng mã hóa. Phiên bản này dành cho khối lượng nhỏ, chưa có hàng đợi hoặc giới hạn số tác vụ đồng thời giữa các người dùng.

Media được gửi đến máy chủ Streamlit để xử lý. Mỗi lần xuất dùng một thư mục tạm riêng, tự xóa cả khi gặp lỗi; MP4 chỉ giữ trong bộ nhớ của phiên để xem/tải. Không ghi media vào repository hoặc gửi đến API bên ngoài. Nên chỉ tải media bạn có quyền sử dụng.

## Kết quả kiểm thử trong phiên xây dựng

Ngày 09/10/2026: **6 kiểm thử vượt qua** trên Python 3.12.14, Streamlit 1.50.0 và FFmpeg 7.1.5 (Debian), tổng khoảng 31 giây. Có kiểm thử nhấn nút xuất demo qua Streamlit AppTest, xác nhận có dữ liệu MP4 và kết quả bị ẩn khi sửa đầu vào. Máy chủ Streamlit khởi động được và endpoint `/_stcore/health` trả `ok`. Chưa kiểm tra trực quan bằng trình duyệt và chưa triển khai lên Community Cloud.
