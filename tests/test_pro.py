import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image, ImageDraw, ImageStat
from streamlit.testing.v1 import AppTest

from studio import StudioError, probe
from studio_pro import media, tts
from studio_pro.models import RenderSettings, Scene, dimensions, validate_timeline
from studio_pro.providers import ProviderInfo, require_activation
from studio_pro.subtitles import Cue, make_cues, parse_srt, to_ass, to_srt


def image_bytes():
    image = Image.new('RGB', (720, 720), '#233850')
    draw = ImageDraw.Draw(image)
    for i in range(12):
        draw.rectangle((i*60, i*30, i*60+28, 600), fill=(i*20, 200-i*10, 120))
    buffer = io.BytesIO()
    image.save(buffer, 'PNG')
    return buffer.getvalue()


def audio_file(root, length=1, fmt='wav', frequency=440):
    path = Path(root) / f'tone-{frequency}.{fmt}'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', f'sine=frequency={frequency}:sample_rate=48000', '-t', str(length), str(path)], check=True, capture_output=True)
    return path.read_bytes()


def frame(path, seconds):
    result = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(seconds), '-i', str(path), '-frames:v', '1', '-f', 'image2pipe', '-c:v', 'png', '-threads', '1', '-'], check=True, capture_output=True)
    return Image.open(io.BytesIO(result.stdout)).convert('RGB')


def decode_audio(path):
    import numpy as np
    result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-vn', '-f', 'f32le', '-ac', '1', '-ar', '48000', '-'], check=True, capture_output=True)
    return np.frombuffer(result.stdout, dtype=np.float32)


class ContractTests(unittest.TestCase):
    def test_timeline_resolution_and_guards(self):
        self.assertEqual(dimensions('9:16', '1080p'), (1080, 1920))
        self.assertEqual(dimensions('16:9', '4K'), (3840, 2160))
        self.assertEqual(validate_timeline([Scene('x', 1.23)], RenderSettings()), 30/24)
        with patch.dict(os.environ, {'STUDIO_RENDER_PROFILE': 'cloud', 'STUDIO_ENABLE_4K': '1'}):
            for scenes, settings in [([Scene('x', 1)], RenderSettings(resolution='4K')), ([Scene('x', 31)]*3, RenderSettings()), ([Scene('x', float('nan'))], RenderSettings()), ([Scene('x', 1)], RenderSettings(voice_speed=3)), ([Scene('x', 1, image=b'x', video=b'y')], RenderSettings())]:
                with self.assertRaises(StudioError):
                    validate_timeline(scenes, settings)
        with patch.dict(os.environ, {'STUDIO_RENDER_PROFILE': 'local', 'STUDIO_ENABLE_4K': '1'}):
            RenderSettings(resolution='4K').validate()

    def test_srt_roundtrip_and_safe_ass(self):
        scenes = [Scene('Xin chào Việt Nam. '*12, 3), Scene('Hẹn gặp lại!', 2)]
        cues = make_cues(scenes)
        parsed = parse_srt(to_srt(cues), 5)
        self.assertEqual(parsed[-1].end, 5)
        self.assertGreater(len(parsed), 2)
        for bad in ['1\n00:00:00,000 --> 00:00:06,000\nx', '2\n00:00:00,000 --> 00:00:01,000\nx', '1\n00:60:00,000 --> 01:00:01,000\nx', '1\n00:00:01,000 --> 00:00:01,000\nx', '1\n00:00:00,000 --> 00:00:02,000\nx\n\n2\n00:00:01,000 --> 00:00:03,000\ny']:
            with self.assertRaises(StudioError):
                parse_srt(bad, 5)
        ass = to_ass([Cue(0, 1, r'{\an8} Tiếng Việt \N'+'\nDòng hai')], (720, 720))
        self.assertNotIn(r'{\an8}', ass)
        self.assertIn('Tiếng Việt', ass)
        self.assertIn(r'\NDòng hai', ass)
        self.assertEqual(parse_srt('', 1), [])

    def test_paid_and_network_disabled_by_default(self):
        info = ProviderInfo('paid', 'Future', True, True, ('video',))
        for enabled, consent in [(False, False), (True, False)]:
            with self.assertRaises(StudioError):
                require_activation(info, enabled, consent)
        require_activation(info, True, True)

    def test_tts_disabled_and_fallback_without_live_network(self):
        voice = next(iter(tts.VOICES.values()))
        with patch.object(tts, '_synthesize', new_callable=AsyncMock) as fake:
            with self.assertRaises(StudioError):
                tts.synthesize('Xin chào', voice)
            fake.assert_not_called()
            fake.return_value = b'mocked-audio'
            self.assertEqual(tts.synthesize('Xin chào', voice, enabled=True), b'mocked-audio')
            fake.side_effect = TimeoutError()
            with self.assertRaisesRegex(StudioError, 'MP3/WAV'):
                tts.synthesize('Xin chào', voice, enabled=True)
            with self.assertRaises(StudioError):
                tts.synthesize('x', 'invalid', enabled=True)


class ProMediaTests(unittest.TestCase):
    def test_motions_are_visible_and_static_is_still(self):
        import numpy as np
        for motion in ('static', 'zoom', 'pan', 'ken_burns'):
            with self.subTest(motion=motion), tempfile.TemporaryDirectory() as root:
                result = media.render([Scene('', 1.5, motion, image_bytes())], RenderSettings(ratio='1:1', transition=0, burn_subtitles=False))
                path = Path(root)/'motion.mp4'; path.write_bytes(result.video)
                first, last = np.asarray(frame(path, .1), dtype=float), np.asarray(frame(path, 1.3), dtype=float)
                difference = abs(first-last).mean()
                if motion == 'static':
                    self.assertLess(difference, 1)
                else:
                    self.assertGreater(difference, 2)

    def test_real_subtitle_burn_and_fades(self):
        import numpy as np
        image = image_bytes()
        with tempfile.TemporaryDirectory() as root:
            plain = media.render([Scene('Tiếng Việt: sống xanh', 2, 'static', image)], RenderSettings(ratio='1:1', transition=.25, burn_subtitles=False))
            burn = media.render([Scene('Tiếng Việt: sống xanh', 2, 'static', image)], RenderSettings(ratio='1:1', transition=.25, burn_subtitles=True), srt='1\n00:00:00,000 --> 00:00:02,000\nPhụ đề đã chỉnh sửa\n')
            a, b = Path(root)/'plain.mp4', Path(root)/'burn.mp4'
            a.write_bytes(plain.video); b.write_bytes(burn.video)
            crop = (0, 540, 720, 700)
            difference = abs(np.asarray(frame(a, 1).crop(crop), dtype=float)-np.asarray(frame(b, 1).crop(crop), dtype=float)).mean()
            self.assertGreater(difference, .5)
            self.assertLess(sum(ImageStat.Stat(frame(a, 0)).mean), 10)
            self.assertGreater(sum(ImageStat.Stat(frame(a, 1)).mean), 30)
            self.assertIn('đã chỉnh sửa', burn.srt)
            info = probe(b)
            self.assertAlmostEqual(float(info['format']['duration']), 2, delta=.1)
            self.assertEqual(next(s for s in info['streams'] if s['codec_type']=='audio')['codec_name'], 'aac')

    def test_scene_voice_sync_speed_music_loop_and_volume(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as root:
            tone = audio_file(root, 1)
            music = audio_file(root, .4, frequency=220)
            scenes = [Scene('', 1, 'static', voice=tone), Scene('', 1, 'static')]
            settings = RenderSettings(ratio='1:1', transition=0, voice_speed=2, fade=0, burn_subtitles=False)
            output = media.render(scenes, settings)
            path = Path(root)/'voice.mp4'; path.write_bytes(output.video)
            samples = decode_audio(path)
            rms = lambda a: float(np.sqrt(np.mean(a*a)))
            self.assertGreater(rms(samples[4800:19200]), .02)
            self.assertLess(rms(samples[38400:45600]), .002)
            # The silent second scene must stay silent even with atempo enabled.
            self.assertLess(rms(samples[60000:80000]), .002)
            settings.voice_volume = 0
            silent = media.render(scenes, settings)
            path.write_bytes(silent.video)
            self.assertLess(rms(decode_audio(path)), .0001)
            settings.music_volume = .5
            mixed = media.render(scenes, settings, music=music)
            path.write_bytes(mixed.video)
            self.assertGreater(rms(decode_audio(path)[60000:80000]), .01)
            settings.fade = .5
            faded = media.render(scenes, settings, music=music)
            path.write_bytes(faded.video)
            samples = decode_audio(path)
            self.assertLess(rms(samples[:2400]), rms(samples[24000:28800])*.3)
            self.assertLess(rms(samples[-2400:]), rms(samples[24000:28800])*.3)

    def test_mp4_hold_and_1080p_export(self):
        with tempfile.TemporaryDirectory() as root:
            clip = Path(root)/'input.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=orange:s=160x90:r=24', '-t', '0.5', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(clip)], check=True, capture_output=True)
            result = media.render([Scene('Clip ngắn', 1, video=clip.read_bytes())], RenderSettings(ratio='16:9', resolution='1080p', transition=0, burn_subtitles=False))
            path = Path(root)/'output.mp4'; path.write_bytes(result.video)
            info = probe(path)
            video = next(s for s in info['streams'] if s['codec_type']=='video')
            self.assertEqual((video['width'], video['height']), (1920, 1080))
            self.assertAlmostEqual(float(info['format']['duration']), 1, delta=.1)
            self.assertTrue(result.warnings)
            self.assertGreater(sum(ImageStat.Stat(frame(path, .9)).mean), 100)
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 'null', '-'], check=True, capture_output=True)

    def test_pro_export_supported_durations_and_ratios(self):
        # Real Pro pipeline, in addition to the unchanged legacy integration tests.
        for ratio, duration in [('9:16', 30), ('16:9', 60), ('1:1', 90)]:
            with self.subTest(ratio=ratio, duration=duration), tempfile.TemporaryDirectory() as root:
                scenes = [Scene('Phụ đề tiếng Việt cho cảnh thử nghiệm', 10, 'ken_burns', image_bytes()) for _ in range(duration//10)]
                progress = []
                result = media.render(scenes, RenderSettings(ratio=ratio), progress=lambda p, msg: progress.append(p))
                path = Path(root)/'result.mp4'; path.write_bytes(result.video)
                info = probe(path)
                video = next(s for s in info['streams'] if s['codec_type']=='video')
                self.assertEqual((video['width'], video['height']), dimensions(ratio, '720p'))
                self.assertEqual(video['codec_name'], 'h264')
                self.assertAlmostEqual(float(info['format']['duration']), duration, delta=.1)
                self.assertEqual(progress[-1], 1)
                self.assertEqual(sorted(progress), progress)
                subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 'null', '-'], check=True, capture_output=True)

    def test_invalid_media_cleanup_lock_and_timeout(self):
        for kind in ('audio', 'video'):
            with self.assertRaises(StudioError):
                media.validate_upload(b'not media', kind)
        with tempfile.TemporaryDirectory() as root:
            tone = audio_file(root, 2)
            with self.assertRaises(StudioError):
                media.render([Scene('', 1, voice=tone)], RenderSettings(), narration=tone)
            result = media.render([Scene('', 1)], RenderSettings(burn_subtitles=False), narration=tone)
            self.assertTrue(result.warnings)
        folders, original = [], tempfile.TemporaryDirectory
        def record(*args, **kwargs):
            directory = original(*args, **kwargs)
            folders.append(directory.name)
            return directory
        with patch.object(media.tempfile, 'TemporaryDirectory', side_effect=record), patch.object(media, 'execute', side_effect=StudioError('forced')):
            with self.assertRaises(StudioError):
                media.render([Scene('', 1)], RenderSettings())
        self.assertTrue(folders)
        self.assertTrue(all(not Path(p).exists() for p in folders))
        self.assertTrue(media._RENDER_LOCK.acquire(blocking=False))
        try:
            with self.assertRaisesRegex(StudioError, 'đang dựng'):
                media.render([Scene('', 1)], RenderSettings())
        finally:
            media._RENDER_LOCK.release()
        with patch.object(media.subprocess, 'run', side_effect=subprocess.TimeoutExpired('ffmpeg', 1)):
            with self.assertRaisesRegex(StudioError, 'thời gian'):
                media.execute(['ffmpeg'])


class ProUITests(unittest.TestCase):
    def test_editor_render_reorder_subtitles_and_invalidation(self):
        app = AppTest.from_file('app.py', default_timeout=120).run()
        app.selectbox(key='studio_editor').set_value('Pro · Giai đoạn A').run()
        self.assertFalse(app.exception)
        app.button(key='pro_split').click().run()
        self.assertFalse(app.exception)
        revision = app.session_state['pro_revision']
        for i in range(3):
            app.number_input(key=f'pro_{revision}_{i}_seconds').set_value(1.0)
        app.run()
        self.assertTrue(app.button(key='pro_export').disabled)
        app.button(key='pro_regenerate_srt').click().run()
        app.button(key='pro_export').click().run(timeout=120)
        self.assertFalse(app.exception)
        self.assertGreater(len(app.session_state['pro_result'].video), 1000)
        app.text_area(key='pro_srt_editor').set_value('1\n00:00:00,000 --> 00:00:03,000\nPhụ đề do tôi sửa\n').run()
        self.assertNotIn('pro_result', app.session_state)
        app.number_input(key=f'pro_{revision}_0_order').set_value(2).run()
        self.assertTrue(app.button(key='pro_export').disabled)
        app.number_input(key=f'pro_{revision}_1_order').set_value(1).run()
        app.button(key='pro_regenerate_srt').click().run()
        self.assertFalse(app.button(key='pro_export').disabled)
        app.radio(key='pro_voice_mode').set_value('Giọng theo cảnh').run()
        self.assertTrue(app.button(key=f'pro_{revision}_0_tts').disabled)
        self.assertTrue(app.button(key='pro_export').disabled)
        app.selectbox(key='studio_editor').set_value('Bản cơ bản').run()
        self.assertFalse(app.exception)
        self.assertIn('Chia kịch bản', app.button[0].label)
