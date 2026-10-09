# Kế hoạch AI Auto Video Studio Pro

## Hiện trạng và nguyên tắc

PR #1 đã được merge vào main tại 348c4fa. Đã đọc toàn bộ các file nguồn, cấu hình và kiểm thử; không tìm thấy AGENTS.md áp dụng. Bản cũ có 6 kiểm thử nhưng phụ thuộc trạng thái phiên, chỉ ghép ảnh tĩnh và MP3, chưa có phụ đề/TTS/nhạc nền. Nâng cấp theo PR độc lập; không tự merge hay thay đổi ứng dụng đang triển khai. Giữ entrypoint app.py và studio.py cùng giao diện mặc định hiện tại. Bộ dựng Pro được chọn riêng từ sidebar.

## Giai đoạn A — bộ dựng miễn phí (PR hiện tại)

- Package studio_pro: models (cảnh/cấu hình/giới hạn), media (FFmpeg), subtitles (SRT/ASS), tts (Edge TTS), providers (hợp đồng mở rộng), ui (luồng thao tác A).
- Ảnh tải lên hoặc nền đồ họa; ảnh tĩnh, zoom, pan, Ken Burns; chuyển cảnh fade qua nền đen, không chồng lấn nên giữ nguyên mốc lời đọc/phụ đề. Chèn MP4; âm thanh gốc MP4 được bỏ có thông báo.
- Chỉnh thứ tự/thời lượng từng cảnh; xuất H.264/AAC 24 fps 720p/1080p. Cấu hình 4K khóa mặc định, chỉ bật ở profile local trên máy/máy chủ đủ tài nguyên; chưa cam kết kiểm thử 4K.
- MP3/WAV toàn video hoặc từng cảnh; tốc độ/âm lượng; Edge TTS tiếng Việt theo từng cảnh, mặc định tắt, gọi qua thao tác riêng. Dịch vụ mạng, không phải offline. Cắt/thêm im lặng theo cảnh; báo cảnh có lời đọc quá dài.
- Nhạc nền lặp đến hết video, âm lượng, fade; phụ đề SRT theo mốc cảnh, sửa trước xuất, tải SRT, gắn trực tiếp bằng libass. Không nhận dạng giọng nói; mốc tự sinh là ước lượng từ kịch bản, không phải word alignment.
- Giới hạn kích thước/loại media thật; chỉ đường dẫn nội bộ sinh bởi ứng dụng, FFmpeg không dùng shell và hạn chế protocol; thư mục tạm tự dọn khi thành công/thất bại. Một tác vụ Pro FFmpeg mỗi process để giảm tải.
- Mẫu kịch bản, Ollama, thư viện dự án và API trả phí chưa được triển khai trong A, không đưa nút giả.

## Giai đoạn B — dashboard, biên tập, lưu dự án

- Dashboard tiếng Việt gồm 10 mục yêu cầu, mẫu kịch bản theo thể loại/giọng văn/đối tượng; timeline trực quan, thao tác di chuyển cảnh và thời lượng.
- Project schema có version, scene ID ổn định, đường dẫn media tương đối, cấu hình và SRT. Export/import ZIP chứa manifest và media, không chứa khóa/API secrets.
- Kiểm tra ZIP trước giải nén: tổng dung lượng, tỷ lệ nén, số file, trùng tên, symlink, đường dẫn tuyệt đối/../, schema và media; ghi nguyên tử và kiểm thử round trip rồi render lại.
- Lưu SQLite + media vào STUDIO_PROJECT_DIR trên ổ bền vững của máy cá nhân/server. Community Cloud không bảo đảm filesystem tồn tại sau restart: ZIP tải xuống là phương án lưu độc lập, không tuyên bố local DB trên Cloud là lưu lâu dài. Nếu cần Cloud nhiều người dùng, bổ sung object storage + xác thực/quyền dự án.

## Giai đoạn C — các nhà cung cấp AI

- Hợp đồng riêng cho script/image/video/speech và thông tin capability/chi phí/network. Tách job ID, polling, timeout/retry/cancellation khỏi UI; kiểm thử bằng fake provider.
- Ollama trên máy cá nhân/server (không chạy mô hình nặng trên Community Cloud). Text/image-to-video thực hiện tại worker riêng; Cloud chỉ gửi job có giới hạn, theo dõi và tải kết quả.
- Mọi provider trả phí mặc định tắt, không gọi mạng trong import/render UI; thông báo giá phụ thuộc nhà cung cấp và cần xác nhận chủ động cho từng công việc. Keys đọc Streamlit Secrets hoặc env, không ghi vào project/log/Git. Chưa có adapter trả phí trong A.

## Giai đoạn D — kiểm thử và triển khai

- Giữ test cũ; thêm FFmpeg integration kiểm tra ảnh chuyển động, thời lượng, audio, phụ đề, clip video, input xấu, cleanup và AppTest Pro.
- Kiểm tra health server, giao diện trình duyệt, tài nguyên ở 720p/1080p; job nặng chuyển sang local/worker. 4K chỉ kiểm thử trên môi trường đủ RAM/CPU.
- Triển khai staging Community Cloud từ branch PR, app.py, Python 3.12; kiểm tra FFmpeg/libass/font, upload/TTS có mạng, render 30/60/90s, tải file, restart và giới hạn RAM. Không đổi site đang hoạt động trước khi staging đạt.
- Phiên này chưa có công cụ/quyền triển khai và URL staging Community Cloud; không tự nhận đã xác minh Cloud. Edge TTS cần kiểm thử live riêng khi dịch vụ và chính sách mạng cho phép.
