import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from streamlit.testing.v1 import AppTest
from studio import SIZES, StudioError, demo_image, prepare_image, probe, render_video, split_script


class PlanningTests(unittest.TestCase):
    def test_split_preserves_words_and_limits(self):
        for duration in (30, 60, 90):
            content = ' '.join(f'từ{i}' for i in range(101))
            scenes = split_script(content, duration)
            self.assertEqual(' '.join(scenes), content)
            self.assertEqual(len(scenes), duration // 10)
        self.assertEqual(split_script('Xin chào', 90), ['Xin', 'chào'])
        for content, duration in [('', 30), ('x', 12), ('x' * 12001, 30)]:
            with self.assertRaises(StudioError):
                split_script(content, duration)

    def test_app_demo_export_and_invalidation(self):
        app = AppTest.from_file('app.py', default_timeout=120).run()
        app.button[0].click().run()
        app.button[1].click().run(timeout=120)
        self.assertFalse(app.exception)
        self.assertGreater(len(app.session_state['video']), 1000)
        self.assertTrue(app.success)
        app.text_area[1].set_value('Ghi chú mới').run()
        self.assertNotIn('video', app.session_state)
        app.toggle[0].set_value(False).run()
        self.assertTrue(app.button[1].disabled)

    def test_image_validation(self):
        with self.assertRaises(StudioError):
            prepare_image(b'not an image', (720, 720))
        buffer = io.BytesIO()
        Image.new('RGBA', (120, 80)).save(buffer, format='PNG')
        result = prepare_image(buffer.getvalue(), (720, 720))
        self.assertEqual(result.mode, 'RGB')
        self.assertEqual(result.size, (720, 720))

    def test_app_scene_flow_and_stale_inputs(self):
        app = AppTest.from_file('app.py').run()
        self.assertFalse(app.exception)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['scenes']), 3)
        app.text_input[0].set_value('Chủ đề mới').run()
        self.assertIn('đã thay đổi', app.warning[0].value)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['revision'], 2)


@unittest.skipUnless(shutil.which('ffmpeg'), 'requires FFmpeg')
class RenderingTests(unittest.TestCase):
    def test_all_ratios_and_durations_with_audio(self):
        for (ratio, size), duration in zip(SIZES.items(), (30, 60, 90)):
            with self.subTest(ratio=ratio, duration=duration), tempfile.TemporaryDirectory() as root:
                root = Path(root)
                audio = None
                if duration != 30:
                    mp3 = root / 'input.mp3'
                    # Both shorter and longer narration relative to target duration.
                    seconds = 2 if duration == 60 else 92
                    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440', '-t', str(seconds), str(mp3)], check=True)
                    audio = mp3.read_bytes()
                data = render_video([demo_image('Sống xanh', i, size) for i in range(3)], audio, duration, ratio, root / 'render')
                path = root / 'result.mp4'
                path.write_bytes(data)
                info = probe(path)
                video = next(s for s in info['streams'] if s['codec_type'] == 'video')
                sound = next(s for s in info['streams'] if s['codec_type'] == 'audio')
                self.assertEqual((video['width'], video['height']), size)
                self.assertEqual(video['codec_name'], 'h264')
                self.assertEqual(sound['codec_name'], 'aac')
                self.assertAlmostEqual(float(info['format']['duration']), duration, delta=.15)
                subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 'null', '-'], check=True, capture_output=True)

    def test_reject_invalid_audio_and_config(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(StudioError):
                render_video([demo_image('Test', 0, (720, 720))], b'fake mp3', 30, '1:1', root)
            with self.assertRaises(StudioError):
                render_video([], None, 30, '1:1', root)


if __name__ == '__main__':
    unittest.main()
