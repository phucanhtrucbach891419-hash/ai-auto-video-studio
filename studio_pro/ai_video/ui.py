"""Opt-in remote job manager. No GPU/model dependencies in Streamlit."""
import hashlib
import time
from dataclasses import replace

import streamlit as st

from studio import StudioError
from .comfy import ACTIVE, ComfyClient, resume
from .config import load_config
from .workflows import VideoRequest, load_profiles

STATE_LABELS = {'queued':'Chờ trong hàng đợi','running':'Đang chạy trên worker','submission_unknown':'Chưa rõ worker đã nhận','missing':'Chưa thấy trong queue/history','complete':'Worker đã trả MP4','downloaded':'MP4 đã tải và kiểm tra','failed':'Lỗi worker','timed_out':'Hết thời gian theo dõi','paused':'Đã ngừng theo dõi'}


def apply_job(job, texts, revision):
    try:
        rev, index = map(int, job.scene_id.split(':'))
    except (ValueError, AttributeError) as exc:
        raise StudioError('Mã cảnh không hợp lệ.') from exc
    if rev != revision or not 0 <= index < len(texts) or not job.data or job.state != 'downloaded':
        raise StudioError('Cảnh đã được chia lại hoặc video chưa tải hợp lệ. Chỉ tải MP4 để dùng thủ công.')
    clips = st.session_state.setdefault('ai_timeline_clips', {})
    if sum(len(c['data']) for key,c in clips.items() if key != job.scene_id)+len(job.data) > 150*1024*1024:
        raise StudioError('Tổng clip AI trong phiên tối đa 150 MB.')
    clips[job.scene_id] = {'data':job.data,'job_id':job.remote_id or job.id,'worker':job.worker,'seconds':job.actual_seconds}
    prefix = f'pro_{revision}_{index}'
    # This function runs before scene widgets are instantiated in the full app run.
    st.session_state[prefix+'_kind'] = 'Clip từ GPU worker'
    st.session_state[prefix+'_seconds'] = min(60.0, max(1.0, round(job.actual_seconds*24)/24))
    st.session_state.pop('pro_result', None)


def manager(config, texts, revision, enabled, auto):
    @st.fragment(run_every=5 if auto and enabled else None)
    def view():
        jobs = st.session_state.setdefault('ai_video_jobs', {})
        if not jobs:
            st.caption('Chưa có tác vụ. Ứng dụng không tạo phim AI khi chưa kết nối GPU worker.')
            return
        st.subheader('Quản lý tác vụ')
        for job in list(jobs.values())[::-1]:
            with st.container(border=True):
                if auto and enabled and job.state in ACTIVE:
                    try:
                        with ComfyClient(config) as client:
                            client.poll(job)
                    except StudioError as exc:
                        job.message = str(exc)
                st.markdown(f'**Cảnh {job.scene_id} · {STATE_LABELS[job.state]}**')
                st.code(job.remote_id or job.id, language=None)
                st.caption(job.message)
                st.caption(f'Thời gian từ lúc gửi: {int(max(0,time.time()-job.created))} giây · clip yêu cầu khoảng {job.expected_seconds:.2f} giây')
                if job.state in ACTIVE:
                    st.info('Đang theo dõi queue/history. API polling không cung cấp phần trăm diffusion chính xác; ứng dụng không hiển thị tiến độ giả.')
                controls = st.columns(3)
                if controls[0].button('Cập nhật trạng thái', key='ai_poll_'+job.id, disabled=not enabled or job.state not in ACTIVE):
                    try:
                        with ComfyClient(config) as client:
                            client.poll(job)
                        st.rerun(scope='app')
                    except StudioError as exc:
                        st.error(str(exc))
                if controls[1].button('Ngừng theo dõi', key='ai_pause_'+job.id, disabled=job.state not in ACTIVE):
                    job.state, job.message = 'paused', 'Chỉ ngừng theo dõi trên website. Job GPU vẫn có thể chạy; không gọi interrupt của worker.'
                    st.rerun(scope='app')
                if controls[2].button('Theo dõi lại tác vụ cũ', key='ai_resume_'+job.id, disabled=not enabled or job.state not in ('paused','timed_out','missing','submission_unknown')):
                    resume(job, config.wait_seconds)
                    st.rerun(scope='app')
                if job.state == 'complete':
                    if st.button('Tải MP4 từ worker và kiểm tra', key='ai_fetch_'+job.id, disabled=not enabled):
                        try:
                            if sum(len(j.data or b'') for j in jobs.values()) >= 125*1024*1024:
                                raise StudioError('Bộ nhớ kết quả AI gần giới hạn 150 MB. Tải file về và xóa kết quả cũ trước khi nhận clip mới.')
                            with st.spinner('Đang tải MP4 có giới hạn 25 MB và kiểm tra bằng FFprobe…'):
                                with ComfyClient(config) as client:
                                    client.download(job)
                            st.rerun(scope='app')
                        except StudioError as exc:
                            st.error(str(exc))
                if job.data:
                    st.video(job.data)
                    st.download_button('Tải MP4 về máy', job.data, 'worker-'+job.id+'.mp4','video/mp4',key='ai_save_'+job.id)
                    valid_target = job.scene_id.startswith(str(revision)+':') and int(job.scene_id.split(':')[1]) < len(texts)
                    if st.button('Đưa clip vào cảnh gốc tương ứng', key='ai_apply_'+job.id, disabled=not valid_target):
                        try:
                            st.session_state.ai_pending_apply = job.id
                            st.rerun(scope='app')
                        except StudioError as exc:
                            st.error(str(exc))
                    st.caption('Clip sẽ thay nguồn hình ảnh và thời lượng của cảnh. Có thể chỉnh tiếp trong timeline; cần cập nhật SRT theo timeline mới.')
                if job.state not in ACTIVE and st.button('Xóa bản ghi khỏi phiên', key='ai_remove_'+job.id):
                    del jobs[job.id]
                    st.rerun(scope='app')
        st.caption('Tác vụ nằm trên ComfyUI; danh sách ở phiên web. Tải MP4 trước khi đóng phiên. Không tự retry POST, không xóa hàng đợi hoặc interrupt tác vụ khác.')
    view()


def panel(texts, revision):
    pending = st.session_state.pop('ai_pending_apply', None)
    if pending:
        try:
            job = st.session_state.get('ai_video_jobs', {}).get(pending)
            if not job:
                raise StudioError('Bản ghi tác vụ đã bị xóa.')
            apply_job(job, texts, revision)
        except StudioError as exc:
            st.error(str(exc))
    with st.expander('AI Video Generator · GPU worker bên ngoài', expanded=True):
        st.write('Nhân vật và bối cảnh chuyển động cần mô hình video trên GPU ngoài. Zoom/pan/Ken Burns của bộ dựng A không phải sinh chuyển động AI.')
        try:
            try:
                settings = dict(st.secrets.get('ai_video', {}))
            except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
                settings = {}
            config = load_config(settings)
            profiles = load_profiles(config.catalog) if config else []
        except StudioError as exc:
            st.error(str(exc))
            return
        if not config:
            st.warning('Chưa kết nối GPU worker. Chủ ứng dụng cần cấu hình ai_video trong Streamlit Secrets hoặc AI_VIDEO_WORKER_URL/AI_VIDEO_WORKER_TOKEN. Không có kết quả AI giả lập.')
            st.caption('GTX 750 Ti 2 GB / RAM 8 GB và Streamlit Cloud không chạy mô hình video. Xem hướng dẫn worker trong README. Không có dịch vụ trả phí mặc định.')
            return
        st.text_input('Endpoint worker · do chủ ứng dụng cấu hình', value=config.url, disabled=True, key='ai_worker_endpoint')
        enabled = st.checkbox('Cho phép kết nối và gửi tác vụ đến worker tôi được quyền sử dụng',value=False,key='ai_video_enabled')
        wait = st.number_input('Giới hạn theo dõi tác vụ (giây)',60,7200,config.wait_seconds,60,key='ai_video_wait')
        config = replace(config,wait_seconds=wait)
        st.caption('Không thuê GPU, không gọi API trả phí. Worker có thể tiêu thụ điện/quota do chủ worker cung cấp. Chỉ bật khi có quyền sử dụng; endpoint và token được cấu hình phía server, token không đưa ra trình duyệt.')
        identity = hashlib.sha256((config.identity+'|'+config.token+'|'+'|'.join(p.signature for p in profiles)).encode()).hexdigest()
        if st.button('Kiểm tra kết nối và workflow',disabled=not enabled,key='ai_connect'):
            try:
                with ComfyClient(config) as client:
                    result = client.connect(profiles)
                st.session_state.ai_readiness = {'identity':identity,**result}
                st.success('Đã kiểm tra API ComfyUI. Thông tin CUDA/node chỉ là worker báo; chưa chứng minh sinh video thành công.')
            except StudioError as exc:
                st.session_state.pop('ai_readiness',None)
                st.error(str(exc))
        readiness = st.session_state.get('ai_readiness',{})
        ready = readiness.get('identity') == identity
        if not ready:
            st.info('Chưa kiểm tra kết nối. Nút gửi tác vụ chỉ mở sau khi kiểm tra API, GPU và workflow.')
        jobs = st.session_state.setdefault('ai_video_jobs',{})
        for i,text in enumerate(texts):
            scene_id = f'{revision}:{i}'
            with st.expander(f'Tạo chuyển động thật · cảnh gốc {i+1}'):
                if not profiles:
                    st.warning('Chưa có profile workflow do chủ worker cấu hình.')
                    continue
                profile_id = st.selectbox('Workflow sinh video', [p.id for p in profiles], format_func=lambda key: next(p.label for p in profiles if p.id==key),key='ai_profile_'+scene_id)
                profile = next(p for p in profiles if p.id==profile_id)
                reasons = readiness.get('errors',{}).get(profile_id,[]) if ready else []
                for reason in reasons:
                    st.warning(reason)
                with st.form('ai_form_'+scene_id):
                    action = st.text_area('Hành động cần tạo',max_chars=2000,key='ai_action_'+scene_id,placeholder='A person walks across a bridge, turns and waves. Water flows below and trees move in the wind.')
                    character = st.text_input('Nhân vật / đối tượng',max_chars=500,key='ai_character_'+scene_id)
                    setting = st.text_input('Bối cảnh / ánh sáng',max_chars=500,key='ai_setting_'+scene_id)
                    camera = st.text_input('Chuyển động camera',max_chars=500,key='ai_camera_'+scene_id)
                    seconds = st.number_input('Thời lượng clip AI (giây)',1.0,float(profile.max_seconds),min(3.0,float(profile.max_seconds)),.25,key='ai_seconds_'+scene_id)
                    ratio = st.selectbox('Tỷ lệ clip AI',['16:9','9:16','1:1'],key='ai_ratio_'+scene_id)
                    seed = st.number_input('Seed tái lập',0,2**32-1,0,1,key='ai_seed_'+scene_id)
                    image = st.file_uploader('Ảnh tham chiếu thật · chỉ Image-to-video',type=['png','jpg','jpeg','webp'],key='ai_image_'+scene_id) if profile.mode=='i2v' else None
                    consent = st.checkbox('Gửi mô tả/ảnh của cảnh này đến worker và sử dụng quota GPU được cấp',key='ai_consent_'+scene_id)
                    active = any(j.scene_id==scene_id and j.state in ACTIVE | {'paused','timed_out','complete'} for j in jobs.values())
                    sent = st.form_submit_button('Gửi tác vụ sinh video',disabled=not enabled or not ready or bool(reasons) or active or len(jobs)>=20)
                st.caption('Mô tả gửi nguyên văn, không tự dịch bằng API. Nên dùng mô tả hành động rõ ràng theo workflow đã kiểm chứng. Clip theo quy tắc số frame của mô hình nên thời lượng có thể lệch nhẹ. Tối đa 20 bản ghi/phiên; không tự gửi lại job đang theo dõi hoặc chưa rõ trạng thái.')
                if sent:
                    try:
                        if not consent:
                            raise StudioError('Cần chủ động đồng ý gửi mô tả/ảnh và dùng GPU cho tác vụ này.')
                        request = VideoRequest(scene_id,profile.mode,action,character,setting,camera,seconds,ratio,int(seed),image.getvalue() if image else None)
                        with st.spinner('Đang tải ảnh (nếu có) và gửi workflow một lần…'):
                            with ComfyClient(config) as client:
                                job = client.submit(request,profile,enabled=enabled)
                        jobs[job.id] = job
                        st.rerun()
                    except StudioError as exc:
                        st.error(str(exc))
        auto = st.checkbox('Tự kiểm tra trạng thái mỗi 5 giây',value=False,key='ai_video_auto',disabled=not enabled)
        manager(config,texts,revision,enabled,auto)
