# AI Auto Video Studio Pro

Ứng dụng Python/Streamlit/FFmpeg bằng tiếng Việt. Giữ nguyên **bản cơ bản** làm mặc định và bổ sung **Pro · Giai đoạn A** từ mục “Bộ dựng video” trong sidebar. Không cần API key; không có API trả phí được kết nối hoặc tự động gọi. Edge TTS là dịch vụ mạng tùy chọn, mặc định tắt. Mẫu kịch bản, Ollama, thư viện dự án và AI tạo ảnh chưa hỗ trợ. Bản nâng cấp bổ sung kết nối AI video qua GPU worker ngoài; chưa xác minh inference GPU thật. Xem [kế hoạch A–D](docs/PRO_PLAN.md).

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

## Sử dụng bản cơ bản

1. Nhập chủ đề và nội dung; chọn 30, 60 hoặc 90 giây và tỷ lệ 9:16, 16:9 hoặc 1:1.
2. Nhấn **Chia kịch bản thành cảnh**. Kịch bản được chia thành tối đa 3, 6 hoặc 9 nhóm từ liên tiếp, mỗi cảnh có thời lượng bằng nhau.
3. Sửa ghi chú từng cảnh và tải PNG/JPG/WebP. Nội dung cảnh chưa được chèn vào video thành phụ đề. Ảnh được cắt giữa để vừa khung hình.
4. Tải giọng đọc MP3. Tệp ngắn được thêm im lặng, tệp dài được cắt; tốc độ giọng đọc giữ nguyên.
5. Nhấn **Tạo video MP4**, xem trước rồi tải video.

Chế độ demo mặc định dùng ảnh đồ họa tạo tại chỗ và âm thanh im lặng khi chưa tải MP3. Muốn có giọng đọc, tải MP3 của bạn. Tắt demo yêu cầu đủ ảnh cho từng cảnh và một MP3 hợp lệ.

Thay đổi chủ đề, nội dung, thời lượng hoặc tỷ lệ yêu cầu chia lại cảnh. Thay đổi media hoặc ghi chú cảnh sẽ ẩn kết quả cũ để tránh tải nhầm video.

## Sử dụng bộ dựng Pro · Giai đoạn A

1. Trong sidebar chọn **Pro · Giai đoạn A**. Chọn tỷ lệ, 720p/1080p, chuyển cảnh fade qua nền đen và tùy chọn gắn phụ đề.
2. Nhập chủ đề, kịch bản có sẵn, chọn thời lượng ban đầu rồi nhấn **Chia cảnh Pro**. Chia lại cảnh thay thế các chỉnh sửa trước đó.
3. Chọn không có giọng đọc, MP3/WAV toàn video hoặc giọng theo từng cảnh. Chỉnh tốc độ 0,5–2x và âm lượng. Có thể tải nhạc nền, chỉnh âm lượng và fade in/out.
4. Chỉnh lời đọc, vị trí và thời lượng mỗi cảnh (1–60 giây). Vị trí phải khác nhau. Chọn ảnh tĩnh/zoom/pan/Ken Burns; tải ảnh hoặc dùng nền đồ họa. Có thể thay cảnh bằng clip MP4; âm thanh gốc clip bị bỏ, clip ngắn giữ khung hình cuối. Các cảnh nối tiếp không chồng lấn; chuyển cảnh qua nền đen không làm thay đổi mốc âm thanh.
5. Với giọng theo cảnh, tải MP3/WAV hoặc chủ động bật **Cho phép gửi nội dung đến Edge TTS qua mạng**, chọn giọng Hoài My/Nam Minh rồi nhấn **Tạo giọng cảnh** cho cảnh cần đọc. Không gọi TTS khi mở app, đổi cấu hình hoặc nhấn xuất. Lời đọc thay đổi sẽ vô hiệu hóa giọng đã tạo; cần tạo lại hoặc tải file thay thế. Edge TTS không phải offline, có thể bị giới hạn hoặc ngừng khả dụng; app báo lỗi và giữ phương án tải âm thanh. Chưa xác minh giọng Edge TTS live trong môi trường này.
6. Kiểm tra timeline và **Biên tập SRT**: sửa chữ và mốc thời gian trước xuất. Mốc tự sinh là ước lượng theo kịch bản/thời lượng cảnh, không phải nhận dạng giọng nói hay căn chỉnh từng từ. Sau khi đổi timeline, nhấn **Tạo lại SRT theo timeline** (thay thế bản sửa) hoặc tự điều chỉnh và nhấn **Giữ SRT đã sửa cho timeline này**. SRT phải tăng theo thời gian, không chồng lấn, không vượt video. Có thể tải SRT riêng.
7. Nhấn **Xuất video Pro MP4**, xem trước và tải xuống. Thay đổi đầu vào sẽ ẩn kết quả cũ. File tạm được dọn cả khi lỗi. Giọng dài bị cắt theo cảnh/video và cảnh báo sau xuất; giọng ngắn được thêm im lặng. Nhạc ngắn được lặp đến hết video; bộ giới hạn âm thanh giảm nguy cơ clipping khi trộn.

### Kiến trúc A và giới hạn

| Mô-đun | Trách nhiệm |
| --- | --- |
| `app.py` | Entrypoint giữ nguyên, chọn bộ dựng; luồng cơ bản được giữ |
| `studio.py` | Backend cơ bản, không sửa API cũ |
| `studio_pro/ui.py` | Biên tập, dữ liệu phiên, kích hoạt TTS và xuất |
| `studio_pro/models.py` | Cảnh, cấu hình, giới hạn timeline, profile Cloud/local |
| `studio_pro/media.py` | Kiểm tra MP3/WAV/MP4 thật, ảnh, dựng tuần tự, chuyển động, trộn âm thanh, burn subtitle, cleanup |
| `studio_pro/subtitles.py` | Tạo/phân tích SRT, kiểm tra mốc, escape nội dung ASS |
| `studio_pro/tts.py` | Edge TTS tùy chọn, timeout và báo lỗi để dùng file tải lên |
| `studio_pro/providers.py` | Hợp đồng provider script/speech/image/video và kiểm tra kích hoạt/đồng ý chi phí; chưa có adapter trả phí |

- Profile mặc định `cloud`: tối đa 9 cảnh, tổng 90 giây. Profile `local`: tối đa 30 cảnh, tổng 300 giây. Một job Pro chạy đồng thời trên mỗi process; job mới bị từ chối với thông báo chờ. Đây không phải hàng đợi phân tán và bản cơ bản chưa có giới hạn tương tự.
- Ảnh tối đa 15 MB/25 triệu điểm ảnh. MP3/WAV/MP4 tối đa 25 MB/tệp, thời lượng nguồn tối đa 600 giây, clip tối đa 8,3 triệu điểm ảnh. Tổng media cảnh tối đa 150 MB; narration/music riêng mỗi tệp tối đa 25 MB. Chỉ chuẩn hóa và dùng file media, không thực thi nội dung file tải lên. FFprobe/FFmpeg đọc upload với whitelist protocol `file,pipe`, không dùng shell hoặc tên tệp người dùng làm đường dẫn.
- Xuất H.264/AAC 24 fps. 720p: 720×1280, 1280×720 hoặc 720×720; 1080p: 1080×1920, 1920×1080 hoặc 1080×1080. Bộ dựng tuần tự, 2 luồng mã hóa và 1 luồng filter, timeout mỗi bước 240 giây (local 600 giây cho bước dựng video). 1080p tốn CPU/RAM hơn; không bảo đảm mọi tác vụ đều vừa giới hạn hosting miễn phí.
- Phụ đề gắn trực tiếp bằng FFmpeg/libass và DejaVu Sans tiếng Việt. Nội dung SRT được escape khi chuyển ASS để tránh người dùng chèn lệnh định dạng ASS.
- **Chưa có lưu dự án lâu dài/ZIP**. App ghi rõ dữ liệu phiên không bền vững; tải MP4, SRT và các giọng đã tạo trước khi đóng phiên. Module dự án và lưu trữ bền vững thuộc B, không tạo nút giả trong A.

### Chuyển tác vụ sang máy cá nhân/server

Dùng cùng repository và `app.py` trên máy cá nhân hoặc server đủ CPU/RAM, không cần chạy mô hình nặng trên Community Cloud:

```bash
# Linux/macOS: profile local; vẫn dùng 720p/1080p mặc định
STUDIO_RENDER_PROFILE=local streamlit run app.py

# Chỉ chuẩn bị cấu hình 4K, bật có chủ đích trên máy đủ tài nguyên
STUDIO_RENDER_PROFILE=local STUDIO_ENABLE_4K=1 streamlit run app.py
```

PowerShell: đặt `$env:STUDIO_RENDER_PROFILE="local"` (và `$env:STUDIO_ENABLE_4K="1"` nếu cần), rồi chạy `streamlit run app.py`. 4K tương ứng 2160×3840 / 3840×2160 / 2160×2160; mặc định bị khóa trên Cloud. **Chưa kiểm thử render 4K; đây là cấu hình chuẩn bị**, có thể vượt tài nguyên máy. Bản A không có worker. Bản nâng cấp kết nối ComfyUI trên GPU ngoài theo hướng dẫn bên dưới; không chạy mô hình trên máy cấu hình thấp.

### Khóa API và chi phí

A không dùng khóa API. Không có adapter trả phí, vì vậy không phát sinh chi phí dịch vụ do app gọi API. Edge TTS chỉ gửi nội dung qua mạng khi người dùng bật và nhấn tạo giọng. Provider trả phí tương lai phải đọc khóa từ Streamlit Secrets hoặc biến môi trường, không lưu vào project/ZIP, không log và không commit. `.streamlit/secrets.toml`, `.env` và dữ liệu cục bộ đã bị loại khỏi Git. Không đưa khóa thật vào README hoặc file ví dụ.

## Streamlit Community Cloud

Đưa repository lên GitHub, vào Streamlit Community Cloud, chọn repository/branch và entrypoint `app.py`, chọn Python 3.12 rồi triển khai. `requirements.txt` cung cấp thư viện Python; `packages.txt` cài FFmpeg, libass và font tiếng Việt. Không cần Secrets hay dịch vụ trả phí. Chưa triển khai thực tế lên Community Cloud trong phiên lập trình; kiểm thử cục bộ không bảo đảm dung lượng và thời gian xử lý trên gói hosting của bạn.

## Kiểm thử

```bash
python -m unittest discover -s tests -v
```

Kiểm thử bao gồm chia cảnh không mất từ, ảnh không hợp lệ, luồng Streamlit và thay đổi đầu vào; xuất MP4 thực bằng FFmpeg với cả ba tỷ lệ và thời lượng; âm thanh demo, MP3 ngắn/dài; xác nhận codec, kích thước, thời lượng bằng FFprobe và giải mã toàn bộ video. Kiểm thử kết xuất cần FFmpeg và có thể mất vài phút. Kiểm thử dùng `streamlit.testing`, chưa thay thế kiểm tra trực quan trên trình duyệt hay kiểm tra triển khai Cloud.

## Cấu trúc và giới hạn bản cơ bản

- `app.py`: giao diện và trạng thái phiên Streamlit.
- `studio.py`: chia cảnh, chuẩn hóa ảnh, kiểm tra MP3 và ghép video.
- `tests/test_studio.py`: kiểm thử thuật toán, giao diện và kết xuất.
- `.streamlit/config.toml`: giao diện tối và giới hạn tải tệp.

Xuất H.264/AAC, 24 fps, 720×1280 / 1280×720 / 720×720. Ảnh tối đa 15 MB và 25 triệu điểm ảnh; MP3 tối đa 25 MB; nội dung tối đa 12.000 ký tự. Chỉ ghép cảnh nối tiếp, chưa có hiệu ứng chuyển cảnh hoặc phụ đề. Xử lý FFmpeg có thời gian giới hạn cho từng tác vụ và dùng 2 luồng mã hóa. Phiên bản này dành cho khối lượng nhỏ, chưa có hàng đợi hoặc giới hạn số tác vụ đồng thời giữa các người dùng.

Media được gửi đến máy chủ Streamlit để xử lý. Mỗi lần xuất dùng một thư mục tạm riêng, tự xóa cả khi gặp lỗi; MP4 chỉ giữ trong bộ nhớ của phiên để xem/tải. Bản cơ bản không ghi media vào repository hoặc gửi đến API bên ngoài. Pro chỉ gửi prompt/ảnh đến worker khi người dùng chủ động bật và gửi tác vụ; Edge TTS cũng cần kích hoạt riêng. Nên chỉ tải media bạn có quyền sử dụng.

## Kết quả kiểm thử bản cơ bản ban đầu

Ngày 09/10/2026: **6 kiểm thử vượt qua** trên Python 3.12.14, Streamlit 1.50.0 và FFmpeg 7.1.5 (Debian), tổng khoảng 31 giây. Có kiểm thử nhấn nút xuất demo qua Streamlit AppTest, xác nhận có dữ liệu MP4 và kết quả bị ẩn khi sửa đầu vào. Máy chủ Streamlit khởi động được và endpoint `/_stcore/health` trả `ok`. Chưa kiểm tra trực quan bằng trình duyệt và chưa triển khai lên Community Cloud.

## Kết quả xác minh Pro · Giai đoạn A

Ngày 09/10/2026: **17/17 kiểm thử tự động đạt** (khoảng 93 giây), giữ nguyên 6 kiểm thử cơ bản. Đã kiểm tra MP4 Pro thật 30/60/90 giây, ba tỷ lệ, chuyển động, trộn âm thanh/fade, phụ đề tiếng Việt và clip 1080p. Đã thao tác trên Chromium thật để xuất, phát/xem trước và tải MP4 3 giây; dark mode đúng, không có lỗi JavaScript/Streamlit và health endpoint trả `ok`.

Chi tiết, giới hạn và cách chạy lại kiểm thử trình duyệt: [PHASE_A_VALIDATION.md](docs/PHASE_A_VALIDATION.md). **Chưa xác minh Edge TTS live, render 4K hoặc triển khai Community Cloud.**

## AI Video Generator — GPU worker ngoài

Trong Pro, mở **AI Video Generator** để kết nối ComfyUI tự host qua HTTPS + token do chủ worker cấp. Mặc định tắt; không có endpoint thì báo **chưa kết nối**, không giả lập phim AI bằng ảnh chuyển động. Không cài PyTorch/CUDA/model lên Streamlit Cloud hoặc máy GTX 750 Ti 2 GB/RAM 8 GB.

- Text-to-video và image-to-video dùng workflow API tin cậy do chủ worker cấu hình. Có hai profile Wan 2.1 mẫu **chưa chạy GPU**, hỗ trợ thêm workflow LTX qua catalog.
- Nhập hành động, nhân vật, bối cảnh, camera, thời lượng và seed cho từng cảnh. I2V yêu cầu ảnh thật. Kiểm tra kết nối/node/model trước gửi và đồng ý từng tác vụ.
- Theo dõi queue/history, lỗi, hết thời gian; không tự gửi lại khi phản hồi không rõ, không hủy toàn bộ queue. Tải MP4 được kiểm tra FFprobe, xem và đưa vào đúng cảnh với thời lượng nguồn.
- Chọn **Chế độ phim: tất cả cảnh phải là clip MP4** để chặn xuất khi còn cảnh ảnh. Chế độ A vẫn hoạt động mặc định.
- Job/clip hiện lưu trong phiên, chưa phải thư viện dự án bền vững. Tải MP4 và ghi job ID trước khi đóng phiên. Animated titles, kinetic typography và phụ đề động mới ở bước thiết kế, chưa triển khai.

Phần mềm mã nguồn mở miễn phí không bảo đảm GPU luôn miễn phí. Có thể dùng máy GPU ngoài được cấp quyền; Colab miễn phí chỉ đề xuất notebook tương tác xuất/tải clip thủ công, không chạy worker nền qua tunnel. Không tự thuê GPU hay gọi API trả phí.

Xem [hướng dẫn worker, Secrets, Wan/LTX và giới hạn dịch vụ miễn phí](worker/README.md), [kế hoạch kiến trúc/dựng phim](docs/AI_VIDEO_PLAN.md) và [kết quả kiểm thử](docs/AI_VIDEO_VALIDATION.md). **Chưa kiểm thử với GPU worker thực tế hoặc triển khai Streamlit Community Cloud; không tuyên bố đã tạo được phim AI chuyển động thật.**
