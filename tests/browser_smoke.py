import json
from pathlib import Path
import argparse

parser = argparse.ArgumentParser(description="Kiểm thử Chromium cho bộ dựng Pro")
parser.add_argument('--url', default='http://127.0.0.1:8501')
parser.add_argument('--browser-path', default=None)
parser.add_argument('--output-dir', default='work/browser')
args = parser.parse_args()
output = Path(args.output_dir)
output.mkdir(parents=True, exist_ok=True)
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=args.browser_path, headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(args.url, wait_until='networkidle')
    page.get_by_role('heading', name='Biến ý tưởng thành video').wait_for()
    page.get_by_test_id('stSelectbox').filter(has_text='Bộ dựng video').get_by_role('combobox').click()
    page.get_by_role('option', name='Pro · Giai đoạn A', exact=True).click()
    page.get_by_role('heading', name='Dựng video theo cách của bạn').wait_for()
    page.get_by_role('button', name='Chia cảnh Pro', exact=True).wait_for()
    page.wait_for_timeout(500)
    page.screenshot(path=str(output/'giao-dien-pro.png'))
    background = page.get_by_test_id('stApp').evaluate('(el) => getComputedStyle(el).backgroundColor')
    assert background == 'rgb(14, 17, 27)', background
    page.get_by_role('button', name='Chia cảnh Pro', exact=True).click()
    page.get_by_role('button', name='Xuất video Pro MP4', exact=True).wait_for()
    for i in range(1, 4):
        field = page.get_by_role('spinbutton', name=f'Thời lượng cảnh {i} (giây)', exact=True)
        field.fill('1.00')
        field.press('Enter')
        page.wait_for_timeout(400)
    page.get_by_role('button', name='Tạo lại SRT theo timeline', exact=True).click()
    export = page.get_by_role('button', name='Xuất video Pro MP4', exact=True)
    export.click()
    download = page.get_by_role('button', name='Tải video Pro MP4', exact=True)
    download.wait_for(timeout=120000)
    page.get_by_test_id('stVideo').wait_for()
    with page.expect_download() as info:
        download.click()
    info.value.save_as(str(output/'video-pro.mp4'))
    video = page.get_by_test_id('stVideo')
    page.wait_for_function('document.querySelector("video")?.readyState >= 1')
    metadata = video.evaluate('(el) => ({width:el.videoWidth, height:el.videoHeight, duration:el.duration})')
    assert metadata['width'] == 720 and metadata['height'] == 1280
    assert abs(metadata['duration'] - 3) < .1
    video.evaluate('(el) => {el.muted=true; return el.play()}')
    page.wait_for_timeout(500)
    video.evaluate('(el) => el.pause()')
    page.screenshot(path=str(output/'xem-truoc-pro.png'))
    report = {'page_errors': errors, 'download_bytes': (output/'video-pro.mp4').stat().st_size, 'title': page.title(), 'background': background, 'preview': metadata, 'horizontal_overflow': page.evaluate('document.documentElement.scrollWidth > window.innerWidth')}
    print(json.dumps(report, ensure_ascii=False))
    assert not errors
    assert page.get_by_test_id('stException').count() == 0
    assert report['download_bytes'] > 1000
    browser.close()
