"""Contract fixtures simulate ComfyUI; none of these tests performs AI inference."""
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from PIL import Image
from streamlit.testing.v1 import AppTest

from studio import StudioError
from studio_pro.ai_video.comfy import ComfyClient, NetworkError, VideoJob, safe_file
from studio_pro.ai_video.config import WorkerConfig, load_config
from studio_pro.ai_video.workflows import VideoRequest, load_profiles
from studio_pro.media import render
from studio_pro.models import Scene, RenderSettings
import subprocess

JOB = '12345678-1234-4234-8234-123456789012'
ROOT = Path(__file__).resolve().parents[1]


class Response:
    def __init__(self, data, status=200):
        self.data = data if isinstance(data,bytes) else json.dumps(data).encode()
        self.status_code = status
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def iter_content(self,size):
        for offset in range(0,len(self.data),size): yield self.data[offset:offset+size]


class FixtureTransport:
    """Explicitly a protocol fixture, including real FFmpeg-made MP4, not an AI worker."""
    def __init__(self, profile, output=b''):
        self.profile, self.output = profile, output
        self.stage, self.calls, self.graph, self.upload = 'pending', [], None, None
        self.error = False
    def close(self): pass
    def request(self,method,url,**kwargs):
        route = url.split('127.0.0.1:8188/')[-1]
        self.calls.append((method,route,kwargs))
        if route=='system_stats': return Response({'devices':[{'type':'cuda','vram_total':16*1024**3}]})
        if route=='object_info':
            return Response({n['class_type']:{'input':{'required':{k:['STRING'] for k in n['inputs']}}} for n in self.profile.graph.values()})
        if route=='upload/image':
            name,data,mime=kwargs['files']['image']; self.upload=data
            return Response({'name':name,'subfolder':'studio','type':'input'})
        if route=='prompt':
            self.graph=kwargs['json']['prompt']
            return Response({'prompt_id':JOB,'node_errors':{}})
        if route=='history/'+JOB:
            if self.stage=='failed': return Response({JOB:{'status':{'completed':False,'status_str':'error','messages':[['execution_error',{'exception_message':'DO NOT EXPOSE TOKEN'}]]},'outputs':{}}})
            if self.stage=='done': return Response({JOB:{'status':{'completed':True,'status_str':'success'},'outputs':{self.profile.output_node:{'images':[{'filename':'clip.mp4','subfolder':'studio','type':'output'}]}}}})
            return Response({})
        if route.startswith('history/'): return Response({})
        if route=='queue':
            entry=[0,JOB,{}, {'client_id':JOB},[]]
            return Response({'queue_running':[entry] if self.stage=='running' else [],'queue_pending':[entry] if self.stage=='pending' else []})
        if route=='view': return Response(self.output)
        raise AssertionError(route)


def config():
    return WorkerConfig('http://127.0.0.1:8188','',allow_local=True)


def png():
    stream=io.BytesIO(); Image.new('RGB',(32,32),'green').save(stream,'PNG'); return stream.getvalue()


class AIContracts(unittest.TestCase):
    def setUp(self):
        self.profiles=load_profiles(ROOT/'worker/workflows/catalog.json')

    def test_defaults_urls_and_secret_redaction(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertIsNone(load_config())
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(StudioError): load_config({'worker_url':123})
            with self.assertRaises(StudioError): load_config({'worker_url':'https://worker.example.org','worker_token':123})
        cfg=WorkerConfig('https://worker.example.org','secret-value')
        self.assertNotIn('secret-value',repr(cfg))
        for url in ['http://public.example','https://x:y@public.example','https://public.example/?token=x','https://public.example/../x','https://public.example/#x','https://public.example:wrong','https://public.example:99999']:
            with self.assertRaises(StudioError): WorkerConfig(url,'secret').validate()
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('169.254.169.254',443))]):
            with self.assertRaises(StudioError): cfg.validate(resolve=True)
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443))]): cfg.validate(resolve=True)

    def test_profiles_bindings_quantization_and_i2v(self):
        t2v,i2v=self.profiles
        request=VideoRequest('1:0','t2v','A person walks','blue coat','river','tracking shot',3,'9:16',42)
        graph,seconds=t2v.build(request,JOB)
        self.assertEqual(graph['7']['inputs']['width'],480)
        self.assertEqual(graph['7']['inputs']['length']%4,1)
        self.assertEqual(graph['8']['inputs']['seed'],42)
        self.assertAlmostEqual(seconds,49/16)
        self.assertEqual(t2v.graph['8']['inputs']['seed'],0)
        request.mode='i2v'
        with self.assertRaises(StudioError): i2v.parameters(request)
        request.image=png()
        graph,_=i2v.build(request,JOB,'studio/ref.png')
        self.assertEqual(graph['12']['inputs']['image'],'studio/ref.png')
        for request in [VideoRequest('1:0','t2v',''), VideoRequest('1:0','t2v','walk',seconds=float('nan')),VideoRequest('1:0','t2v','walk',seconds=6)]:
            with self.assertRaises(StudioError): t2v.parameters(request)

    def test_output_paths_and_no_static_fallback(self):
        for name,folder in [('image.png',''),('../clip.mp4',''),('clip.mp4','../private'),('clip.mp4','/etc'),('https://x/clip.mp4','')]:
            with self.assertRaises(StudioError): safe_file({'filename':name,'subfolder':folder,'type':'output'})
        for typ in ['input','temp']:
            with self.assertRaises(StudioError): safe_file({'filename':'clip.mp4','type':typ})
        transport=FixtureTransport(self.profiles[0])
        client=ComfyClient(config(),transport)
        with self.assertRaises(StudioError): client.submit(VideoRequest('1:0','t2v','walk'),self.profiles[0])
        self.assertEqual(transport.calls,[])

    def test_connection_nodes_and_paid_node_detection(self):
        profile=self.profiles[0]
        transport=FixtureTransport(profile)
        client=ComfyClient(config(),transport)
        self.assertFalse(client.connect([profile])['errors'][profile.id])
        schema={n['class_type']:{'input':{'required':{k:['STRING'] for k in n['inputs']}}} for n in profile.graph.values()}
        schema['UNETLoader']['is_api_node']=True
        with patch.object(transport,'request',side_effect=[Response({'devices':[{'type':'cuda','vram_total':1}]}),Response(schema)]):
            self.assertTrue(client.connect([profile])['errors'][profile.id])
        with patch.object(transport,'request',side_effect=[Response({'devices':[]}),Response({})]):
            self.assertFalse(client.connect([profile])['gpu_reported'])


class AIJobTests(unittest.TestCase):
    def setUp(self): self.profile=load_profiles(ROOT/'worker/workflows/catalog.json')[0]

    def test_queue_running_completion_download_and_timeline_render(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'fixture.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=160x96:r=16','-t','1','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True,capture_output=True)
            transport=FixtureTransport(self.profile,path.read_bytes())
            client=ComfyClient(config(),transport)
            job=client.submit(VideoRequest('1:0','t2v','person walking'),self.profile,enabled=True)
            client.poll(job); self.assertEqual(job.state,'queued')
            transport.stage='running'; client.poll(job); self.assertEqual(job.state,'running')
            transport.stage='done'; client.poll(job); self.assertEqual(job.state,'complete')
            client.download(job); self.assertEqual(job.state,'downloaded')
            self.assertEqual(job.data,path.read_bytes())
            result=render([Scene('Clip giao thức thử nghiệm, không phải video AI',1,video=job.data)],RenderSettings(ratio='1:1',burn_subtitles=False))
            self.assertGreater(len(result.video),1000)
            self.assertEqual(sum(m=='POST' and r=='prompt' for m,r,_ in transport.calls),1)
            self.assertTrue(all(c[2]['allow_redirects'] is False for c in transport.calls))

    def test_real_http_transport_roundtrip_not_gpu_inference(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import urlsplit
        profile=self.profile
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'fixture.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=160x96:r=16','-t','1','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True,capture_output=True)
            transport=FixtureTransport(profile,path.read_bytes())
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args): pass
                def handle_request(self,method):
                    if self.headers.get('Authorization') != 'Bearer fixture-token':
                        self.send_response(401);self.end_headers();return
                    kwargs={}
                    if method=='POST':
                        kwargs['json']=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    response=transport.request(method,'http://127.0.0.1:8188'+urlsplit(self.path).path,**kwargs)
                    self.send_response(response.status_code)
                    self.send_header('Content-Length',str(len(response.data)))
                    self.end_headers();self.wfile.write(response.data)
                def do_GET(self): self.handle_request('GET')
                def do_POST(self): self.handle_request('POST')
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                cfg=WorkerConfig(f'http://127.0.0.1:{server.server_port}','fixture-token',allow_local=True)
                # Only loopback test traffic avoids the egress proxy; remote policy stays intact.
                with patch.dict(os.environ,{'NO_PROXY':'127.0.0.1,localhost'}),ComfyClient(cfg) as client:
                    self.assertFalse(client.connect([profile])['errors'][profile.id])
                    job=client.submit(VideoRequest('1:0','t2v','protocol fixture'),profile,enabled=True)
                    transport.stage='done';client.poll(job);client.download(job)
                    self.assertEqual(job.data,path.read_bytes())
            finally:
                server.shutdown();server.server_close();thread.join(timeout=3)

    def test_i2v_upload_is_real_png_and_correct_binding(self):
        profile=load_profiles(ROOT/'worker/workflows/catalog.json')[1]
        transport=FixtureTransport(profile)
        client=ComfyClient(config(),transport)
        client.submit(VideoRequest('1:0','i2v','walk',image=png()),profile,enabled=True)
        self.assertEqual(Image.open(io.BytesIO(transport.upload)).size,(832,480))
        self.assertTrue(transport.graph['12']['inputs']['image'].startswith('studio/'))
        self.assertEqual([r for m,r,k in transport.calls if m=='POST'],['upload/image','prompt'])

    def test_ambiguous_submit_is_not_retried_and_recovers_queue(self):
        transport=FixtureTransport(self.profile)
        client=ComfyClient(config(),transport)
        with patch.object(transport,'request',side_effect=requests.Timeout()):
            job=client.submit(VideoRequest('1:0','t2v','walk'),self.profile,enabled=True)
        self.assertEqual(job.state,'submission_unknown')
        with patch.object(transport,'request',side_effect=[Response({}),Response({'queue_pending':[[0,JOB,{}, {'client_id':job.id},[]]],'queue_running':[]})]) as request:
            client.poll(job)
        self.assertEqual(job.remote_id,JOB)
        self.assertEqual(job.state,'queued')
        self.assertTrue(all(call.args[0]=='GET' for call in request.call_args_list))
        with patch.object(transport,'request',return_value=Response({},502)):
            other=client.submit(VideoRequest('1:0','t2v','walk'),self.profile,enabled=True)
            self.assertEqual(other.state,'submission_unknown')

    def test_worker_errors_timeout_bad_outputs_and_download_limits(self):
        transport=FixtureTransport(self.profile)
        client=ComfyClient(config(),transport)
        job=client.submit(VideoRequest('1:0','t2v','walk'),self.profile,enabled=True)
        transport.stage='failed'; client.poll(job)
        self.assertEqual(job.state,'failed')
        self.assertNotIn('DO NOT EXPOSE',job.message)
        job.state='queued'; job.deadline=0
        before=len(transport.calls); client.poll(job)
        self.assertEqual(job.state,'timed_out'); self.assertEqual(len(transport.calls),before)
        job.deadline=time.time()+100; job.state='queued'
        with patch.object(transport,'request',return_value=Response({JOB:{'status':{'completed':True},'outputs':{'11':{'images':[{'filename':'photo.png'}]}}}})):
            client.poll(job); self.assertEqual(job.state,'failed')
        job.state='complete';job.output={'filename':'clip.mp4','subfolder':'studio','type':'output'}
        with self.assertRaises(StudioError): client.download(job)
        with patch.object(transport,'request',return_value=Response(b'x'*100)),patch('studio_pro.ai_video.comfy.MAX_MEDIA_BYTES',64):
            with self.assertRaisesRegex(StudioError,'giới hạn'): client.download(job)
        with patch.object(transport,'request',return_value=Response({},302)):
            with self.assertRaisesRegex(StudioError,'chuyển hướng'): client._json('GET','system_stats')
        with patch.object(transport,'request',return_value=Response({'token':'sensitive'},401)):
            with self.assertRaisesRegex(StudioError,'xác thực'): client._json('GET','system_stats')
        with patch.object(transport,'request',side_effect=requests.Timeout()):
            job.state='running'; client.poll(job); self.assertEqual(job.state,'running')


class AIUITests(unittest.TestCase):
    def test_no_worker_no_requests_no_fake_output_and_phase_a_intact(self):
        with patch.dict(os.environ,{'AI_VIDEO_WORKER_URL':''}),patch('requests.Session.request') as network:
            app=AppTest.from_file('app.py',default_timeout=120).run()
            app.selectbox(key='studio_editor').set_value('Pro · Giai đoạn A').run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Chưa kết nối GPU worker' in w.value for w in app.warning))
            app.button(key='pro_split').click().run()
            rev=app.session_state['pro_revision']
            app.checkbox(key='pro_clip_only').set_value(True).run()
            self.assertTrue(app.button(key='pro_export').disabled)
            app.radio(key=f'pro_{rev}_0_kind').set_value('Clip từ GPU worker').run()
            self.assertTrue(app.button(key='pro_export').disabled)
            self.assertFalse(app.exception)
            network.assert_not_called()

    def test_ui_connect_submit_receive_apply_clip(self):
        profile=load_profiles(ROOT/'worker/workflows/catalog.json')[0]
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'fixture.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=160x96:r=16','-t','1','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True,capture_output=True)
            transport=FixtureTransport(profile,path.read_bytes())
            env={'AI_VIDEO_WORKER_URL':'http://127.0.0.1:8188','AI_VIDEO_ALLOW_LOCAL':'1','STUDIO_RENDER_PROFILE':'local'}
            with patch.dict(os.environ,env),patch('requests.Session.request',side_effect=transport.request):
                app=AppTest.from_file('app.py',default_timeout=120).run()
                app.selectbox(key='studio_editor').set_value('Pro · Giai đoạn A').run()
                self.assertFalse(app.exception)
                app.checkbox(key='ai_video_enabled').set_value(True).run()
                app.button(key='ai_connect').click().run()
                self.assertFalse(app.exception)
                app.button(key='pro_split').click().run()
                rev=app.session_state['pro_revision'];scene=f'{rev}:0'
                app.text_area(key='ai_action_'+scene).set_value('person walking')
                app.checkbox(key='ai_consent_'+scene).set_value(True)
                next(b for b in app.button if b.label=='Gửi tác vụ sinh video').click().run()
                self.assertFalse(app.exception)
                job=next(iter(app.session_state['ai_video_jobs'].values()))
                transport.stage='done'
                app.button(key='ai_poll_'+job.id).click().run()
                self.assertFalse(app.exception)
                app.button(key='ai_fetch_'+job.id).click().run()
                self.assertFalse(app.exception)
                app.button(key='ai_apply_'+job.id).click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.radio(key=f'pro_{rev}_0_kind').value,'Clip từ GPU worker')
                self.assertEqual(app.number_input(key=f'pro_{rev}_0_seconds').value,1)
                self.assertEqual(app.session_state['ai_timeline_clips'][scene]['data'],path.read_bytes())
