# GPU worker ngoài — phần mềm miễn phí, tài nguyên có điều kiện

**Không cài mô hình video lên GTX 750 Ti 2 GB/RAM 8 GB hoặc Streamlit Community Cloud.** App chỉ gửi request và ghép MP4 trên CPU. Chưa có worker thật trong phiên phát triển; các workflow mẫu chưa được chạy GPU. Không có API trả phí, tài khoản cloud trả phí hay tự động thuê GPU trong repository.

## Kết quả nghiên cứu và chọn mô hình (09/10/2026)

| Lựa chọn | Đánh giá cho yêu cầu hiện tại |
| --- | --- |
| Wan 2.1 T2V 1.3B | Native ComfyUI; mốc VRAM công bố 8,19 GB, ưu tiên thử 480p/clip ngắn trên GPU ngoài có dư bộ nhớ. Không phù hợp 2 GB. Worker 12–16 GB VRAM + RAM host đủ lớn là mục tiêu thử nghiệm, không phải bảo đảm cấu hình mọi workflow. |
| Wan 2.1 I2V 14B | Native ComfyUI, có ảnh conditioning thật. Nặng hơn nhiều; không mặc định coi GPU miễn phí nhỏ đủ chạy. Giảm precision/offload cần nhiều RAM host và kiểm thử riêng. Profile mẫu trong repo chưa chứng minh chạy thành công. |
| LTX-Video 2B/distilled | Ứng viên cho GPU ngoài hạn chế hơn 13B; có T2V/I2V và workflow ComfyUI. Cần chọn đúng checkpoint/version/giấy phép và export workflow API. PR này có adapter generic để nạp profile, chưa có workflow LTX được xác minh GPU. |

Nguồn chính thức: [Wan2.1](https://github.com/Wan-Video/Wan2.1), [ComfyUI Wan native](https://docs.comfy.org/tutorials/video/wan/wan-video), [LTX-Video](https://github.com/Lightricks/LTX-Video). Không đồng nhất LTX-Video 2B đời cũ với LTX-2 mới có audio/video; không suy ra yêu cầu VRAM của checkpoint này từ checkpoint khác. Giấy phép code và weights có thể khác; kiểm tra model card/license của file cụ thể trước khi phát hành phim.

## Phương án miễn phí nào khả thi?

- **Có máy GPU được cho phép dùng miễn phí** (máy của người quen/tổ chức, tài nguyên nghiên cứu hoặc quota được cấp): có thể tự host ComfyUI theo phần bên dưới. Không phải thuê GPU; chi phí điện, đường truyền, DNS và điều kiện chia sẻ thuộc chủ máy. Phần mềm miễn phí không tạo ra GPU miễn phí.
- **Chỉ có Colab miễn phí**: dùng notebook tương tác để sinh clip và tải MP4, rồi tải MP4 thủ công vào Pro. Không hướng dẫn chạy tunnel/ComfyUI web service/API nền trên Colab free. FAQ chính thức hạn chế dùng web UI thay notebook và distributed workers; phiên GPU có thể bị ngắt, quota/GPU không bảo đảm. [Colab FAQ](https://research.google.com/colaboratory/faq.html).
- **Hugging Face ZeroGPU/demos**: theo tài liệu hiện tại, tài khoản miễn phí đã xác minh email và có tuổi trên 30 ngày có thể host tối đa 2 ZeroGPU Spaces; quota miễn phí 5 phút GPU/ngày. Điều kiện/quota có thể thay đổi; cần kiểm tra tài liệu trước triển khai. ZeroGPU dùng Gradio, không phải ComfyUI worker miễn phí luôn chạy. Chưa có adapter cho dịch vụ này, không dùng API demo không được cho phép. [ZeroGPU](https://huggingface.co/docs/hub/spaces-zerogpu).
- Nếu chưa có GPU ngoài hợp lệ, app hiển thị **chưa kết nối**, không sinh clip AI và không dùng Ken Burns để giả kết quả. Không bảo đảm một worker luôn miễn phí có thể cung cấp cho mọi người.

## Tự host ComfyUI trên GPU ngoài đã được cấp quyền

Các bước này **chỉ dành cho máy GPU ngoài**, do chủ worker thực hiện. Không đưa các dependencies dưới đây vào requirements.txt của Streamlit.

1. Kiểm tra NVIDIA driver/GPU với `nvidia-smi`. Cài Python/PyTorch CUDA tương thích theo [hướng dẫn ComfyUI](https://docs.comfy.org/installation/manual_install); tránh chọn CUDA build theo máy GTX 750 Ti của người dùng.
2. Tạo môi trường riêng và cài ComfyUI:

```bash
git clone https://github.com/Comfy-Org/ComfyUI.git
cd ComfyUI
python3 -m venv .venv
source .venv/bin/activate
# Cài PyTorch CUDA theo hướng dẫn chính thức và driver của worker trước.
pip install -r requirements.txt
python main.py --listen 127.0.0.1 --port 8188
```

3. Tải weights theo workflow từ nguồn chính thức, không bật node API trả phí. Wan T2V mẫu cần:

```text
ComfyUI/models/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors
ComfyUI/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors
ComfyUI/models/vae/wan_2.1_vae.safetensors
```

I2V mẫu thay diffusion bằng `wan2.1_i2v_480p_14B_fp16.safetensors` và thêm `models/clip_vision/clip_vision_h.safetensors`. Không phải chỉ tải weights 1.3B là đã có I2V 14B. Weights có thể nhiều GB; kiểm tra disk/RAM của worker và license.

4. Chạy workflow native trong UI ComfyUI trước, tạo clip có người bước đi/đổi tư thế/tương tác, nước/cây chuyển động; dùng CreateVideo → SaveVideo với MP4. Xem toàn bộ clip, ghi model/version/GPU/seed. Schema node có thể thay đổi: workflow đã export và chạy trên worker là nguồn chuẩn. Các đồ thị `.api.json` trong repo là mẫu tự viết chưa chạy GPU, không phải chứng nhận tương thích mọi ComfyUI release.
5. Đưa API sau HTTPS + xác thực, không mở cổng 8188 trực tiếp ra Internet. Có thể dùng Caddy với `Caddyfile.example` trên máy có DNS public/cổng 80/443 phù hợp. Tạo token bằng `openssl rand -hex 32`, lưu trong environment/service secret của worker (`STUDIO_WORKER_TOKEN`) và Streamlit Secrets; không ghi token vào Git. `WORKER_DOMAIN` là hostname DNS của bạn. Certificate TLS phải hợp lệ; client không tắt verify hoặc theo redirect. Cấu hình mẫu chỉ proxy các route client cần, không proxy Manager/userdata/interrupt.
6. Với worker đang có queue/output, chủ worker cần đặt thời gian giữ history và file đủ dài để website tải; dung lượng output cần được chủ worker dọn theo chính sách, app không tự xóa media của worker. Nếu phục vụ nhiều người, cần xác thực người dùng/rate limit/job ownership ở gateway riêng. PR này phù hợp một chủ ứng dụng hoặc nhóm tin cậy, không cung cấp phân quyền đa người dùng trên ComfyUI.

## Cấu hình website Streamlit Community Cloud

Trong quản lý app → Settings → Secrets, thêm (giá trị minh họa, **không commit token thật**):

```toml
[ai_video]
worker_url = "https://gpu-worker.example.org"
worker_token = "TOKEN_TU_CAP_BOI_CHU_WORKER"
catalog = "worker/workflows/catalog.json"
wait_seconds = 1800
```

Hoặc env: `AI_VIDEO_WORKER_URL`, `AI_VIDEO_WORKER_TOKEN`, `AI_VIDEO_CATALOG`, `AI_VIDEO_WAIT_SECONDS`. URL và token chỉ đọc từ server; visitor không thể đổi endpoint tùy ý. App mặc định không gọi mạng khi mở và không gửi job cho đến khi bật, kiểm tra kết nối và đồng ý tác vụ. Hạn chế quyền truy cập app nếu token dùng GPU nhóm riêng; đây không phải API key trả phí.

Streamlit Cloud cần HTTPS hostname public; IP private/metadata, URL có user/password/query/fragment và redirect bị từ chối. Nếu dùng tunnel hợp lệ của **worker ngoài đã được cấp quyền**, nó phải có HTTPS trực tiếp + xác thực, không tự provision dịch vụ trả phí; thay hostname cần cấu hình lại Secrets. Không dùng tunnel để biến Colab free thành dịch vụ nền. Không cài ComfyUI/PyTorch/CUDA trên Cloud.

Chọn Pro → AI Video Generator → bật kết nối → **Kiểm tra kết nối và workflow**. Check chỉ xác nhận API báo CUDA/node/model; không chứng minh inference. Profile thiếu node/input/weights bị chặn. Chọn workflow cho cảnh, nhập hành động/nhân vật/bối cảnh/camera/thời lượng/seed; I2V cần ảnh thật. Tick đồng ý rồi gửi đúng một lần. Theo dõi thủ công/5 giây, tải MP4, xem rồi đưa vào cảnh gốc tương ứng. App cập nhật thời lượng cảnh theo clip; hãy cập nhật SRT trước xuất. Bật “Chế độ phim: tất cả cảnh phải là clip MP4” để không xuất ảnh/nền đồ họa cho cảnh thiếu video.

## Thêm workflow LTX hoặc phiên bản Wan khác

Không cần viết lại client:

1. Chủ worker chạy workflow local đã kiểm chứng, lưu MP4 bằng SaveVideo hoặc VHS_VideoCombine.
2. Export **Workflow (API)** từ ComfyUI. JSON giao diện có `nodes`/`links` không dùng trực tiếp được. Lưu `.api.json` trong thư mục catalog của app (không chứa key hoặc node API).
3. Thêm profile trong `catalog.json`: `id`, `label`, `mode` (`t2v`/`i2v`), `workflow` (file cùng thư mục), `output_node`, `fps`, `frame_step` (4 hoặc 8), `max_seconds` (1–10), `sizes` cho ba tỷ lệ (bội số 16, 128–1280).
4. Bind từng trường dưới dạng `["node_id", "input_name"]`: `prompt`, `seed`, `width`, `height`, `frames`, `fps`, `prefix`, thêm `image` cho I2V. Xem catalog Wan mẫu. Prefix được thay bằng UUID, không phải đường dẫn do visitor nhập. Giữ batch size=1 và sampling steps phù hợp quota.
5. Thay filename/checkpoint tùy worker; kiểm tra lại schema/weights và chạy clip thật. Kiểm tra phần trăm diffusion/WebSocket chưa triển khai; UI chỉ báo queue/running/completed. Không tự dịch prompt hoặc dùng LLM mở rộng có API key.

Profile catalog là cấu hình tin cậy do chủ app triển khai, không phải file upload của visitor. Client chặn tên/metadata node API phổ biến; chủ worker vẫn cần kiểm tra mã custom node vì kiểm tra tên/schema không thể bảo đảm mọi node đều chỉ chạy local.

## Notebook miễn phí: phương án thủ công thay cho worker nền

Nếu được cấp GPU trên Colab, dùng giao diện notebook và chạy inference theo [Quickstart Wan2.1](https://github.com/Wan-Video/Wan2.1#quickstart), không khởi động web UI/tunnel/worker cho website. Chọn T2V 1.3B, độ phân giải 480p, mô tả hành động ngắn, **không bật prompt extension qua Dashscope hoặc API khác**. CPU offload/text encoder trên RAM là việc của máy notebook ngoài, không phải máy người dùng. Có thể OOM, hết disk, lỗi dependencies hoặc bị thu hồi GPU; không có SLA.

Trong notebook, sau khi clone/cài dependencies theo quickstart và tải checkpoint 1.3B đúng thư mục, lệnh inference tham khảo:

```bash
python generate.py --task t2v-1.3B --size '832*480' \
  --ckpt_dir ./Wan2.1-T2V-1.3B --offload_model True --t5_cpu \
  --sample_shift 8 --sample_guide_scale 6 \
  --prompt 'A person walks across a bridge and waves. Trees move in the wind and water flows below. A tracking camera follows the person.'
```

Không phải script được chạy/kiểm chứng trong phiên này. Nếu runtime/weights không phù hợp, dừng và kiểm tra hướng dẫn model thay vì mua GPU/API mặc định. Khi đã có MP4 thật, dùng tính năng download của notebook, tải clip vào nguồn **Clip MP4** của từng cảnh trong app. Phương án này có chuyển động do model khi inference thành công nhưng là luồng thủ công, không phải kết nối AI tự động từ website.

## Giới hạn vận hành

- HTTP connect/read timeout 5/15 giây; stream tối đa 45 giây/lần và 25 MB/MP4. Job tracking 60–7.200 giây. Clip nhận về 1–60 giây và tối đa 8,3 triệu điểm ảnh; workflow mẫu sinh khoảng 1–5 giây, có lượng tử frame.
- Không retry POST khi timeout/5xx; trạng thái không rõ cần tra queue/history, hoặc chủ worker xem history nếu ComfyUI cũ tạo ID khác và job hoàn tất trước khi client phục hồi được ID.
- Hết thời gian/ngừng theo dõi không hủy GPU; website không gọi interrupt/global queue clear. Xóa bản ghi khỏi phiên không xóa worker job/output.
- Danh sách job/clip cache theo phiên (20 records/150 MB), chưa bền vững sau restart. Copy job ID, tải MP4 để lưu; thư viện/project ZIP và ownership đa người dùng chưa thuộc PR này.
- Model có thể sinh chuyển động kém, biến dạng hoặc không bám prompt. MP4 hợp lệ không chứng minh nhân vật tương tác đúng. Cần kiểm tra trực quan trên GPU thật trước khi tuyên bố tạo phim AI.
