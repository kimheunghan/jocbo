"""우리의 족보 - Microsoft Store 에 올릴 MSIX 패키지(build\\jocbo.msix)를 만듭니다.

먼저 `py -3.12 desktop\\build.py --store` 로 build\\app 을 만든 뒤 돌립니다. Store 판이라
데모 계정과 가상 인물 예제만 들어 있습니다. 서명은 Store 가 올릴 때 대신 합니다.

    py -3.12 desktop\\make_msix.py 2026.10.5

판 번호는 세 마디(연.월.일 등)로 주며, Store 규칙대로 끝에 .0 을 붙입니다.
MakeAppx.exe(Windows SDK)가 필요합니다. GitHub Actions 의 Windows 에는 깔려 있습니다.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'build' / 'app'
HERE = Path(__file__).resolve().parent / 'msix'


def logo(size, width=None):
    """프로그램 아이콘과 같은 "족" 그림. 넓은 타일은 가운데에 둡니다."""
    width = width or size
    img = Image.new('RGBA', (width, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = size / 256
    x0 = (width - size) / 2
    d.rounded_rectangle((x0 + 8 * k, 8 * k, x0 + size - 8 * k, size - 8 * k), radius=48 * k, fill=(122, 38, 32, 255))
    d.rounded_rectangle((x0 + 22 * k, 22 * k, x0 + size - 22 * k, size - 22 * k), radius=36 * k,
                        outline=(214, 178, 110, 255), width=max(1, round(6 * k)))
    font = ImageFont.truetype(str(Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts' / 'malgunbd.ttf'), round(150 * k))
    b = d.textbbox((0, 0), '족', font=font)
    d.text((x0 + (size - (b[2] - b[0])) / 2 - b[0], (size - (b[3] - b[1])) / 2 - b[1]), '족', font=font, fill=(250, 240, 220, 255))
    return img


def icons(assets):
    """Windows 가 화면마다 골라 쓰는 크기의 그림을 모두 만듭니다.

    설치 진행 표시·작업 표시줄·알림은 targetsize 그림(16~256), 시작 메뉴와 타일은
    배율(scale-100~400) 그림을 찾습니다. 맞는 크기가 없으면 빈 칸이나 흐린 그림이
    나옵니다. 어느 그림을 쓸지는 resources.pri 가 알려 줍니다.
    """
    shutil.rmtree(assets, ignore_errors=True)
    assets.mkdir()
    scales = (100, 125, 150, 200, 400)
    tiles = {'StoreLogo': (50, 50), 'Square44x44Logo': (44, 44), 'Square71x71Logo': (71, 71),
             'Square150x150Logo': (150, 150), 'Square310x310Logo': (310, 310), 'Wide310x150Logo': (310, 150)}
    for name, (w, h) in tiles.items():
        logo(h, w).save(assets / f'{name}.png')
        for s in scales:
            logo(round(h * s / 100), round(w * s / 100)).save(assets / f'{name}.scale-{s}.png')
    for size in (16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 256):
        im = logo(size)
        im.save(assets / f'Square44x44Logo.targetsize-{size}.png')
        im.save(assets / f'Square44x44Logo.targetsize-{size}_altform-unplated.png')
        im.save(assets / f'Square44x44Logo.targetsize-{size}_altform-lightunplated.png')


def sdk_tool(name):
    found = sorted(glob.glob(rf'C:\Program Files (x86)\Windows Kits\10\bin\10.*\x64\{name}'))
    if not found:
        sys.exit(f'{name} 를 찾지 못했습니다(Windows SDK 필요).')
    return found[-1]


def makeappx():
    return sdk_tool('makeappx.exe')


def resources():
    """그림 크기별 목록(resources.pri)을 만듭니다. 이것이 없으면 Windows 는 크기를 고르지 못합니다."""
    makepri = sdk_tool('makepri.exe')
    # 프로그램 폴더 전체를 훑으면 파이썬 꾸러미의 ko·en 같은 폴더 이름을 언어로 잘못 읽습니다.
    # 그림과 설명서만 따로 두고 목록을 만듭니다(목록 속 경로는 패키지 기준이라 같습니다).
    stage = ROOT / 'build' / 'pri'
    shutil.rmtree(stage, ignore_errors=True)
    shutil.copytree(APP / 'Assets', stage / 'Assets')
    shutil.copy(APP / 'AppxManifest.xml', stage / 'AppxManifest.xml')
    config = ROOT / 'build' / 'priconfig.xml'
    subprocess.run([makepri, 'createconfig', '/cf', str(config), '/dq', 'ko-KR', '/o'], check=True)
    subprocess.run([makepri, 'new', '/pr', str(stage), '/cf', str(config), '/mn', str(stage / 'AppxManifest.xml'),
                    '/of', str(APP / 'resources.pri'), '/o'], check=True)


def main(version):
    identity = json.loads((HERE / 'identity.json').read_text(encoding='utf-8'))
    if not all(identity.get(key) for key in ('name', 'publisher', 'publisher_display')):
        sys.exit('desktop/msix/identity.json 에 Partner Center 의 제품 ID 세 값을 넣어 주십시오.')
    if not (APP / 'launcher.py').exists():
        sys.exit('build\\app 이 없습니다. 먼저 build.py --store 를 돌리십시오.')
    parts = version.split('.')
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        sys.exit('판 번호는 2026.10.5 처럼 세 마디로 주십시오.')

    manifest = (HERE / 'AppxManifest.xml').read_text(encoding='utf-8')
    for key, value in (('NAME', identity['name']), ('PUBLISHER', identity['publisher']),
                       ('PUBLISHER_DISPLAY', identity['publisher_display']), ('VERSION', version + '.0')):
        manifest = manifest.replace('{{' + key + '}}', value)
    (APP / 'AppxManifest.xml').write_text(manifest, encoding='utf-8')

    icons(APP / 'Assets')
    shutil.copy(Path(__file__).resolve().parent / 'jocbo.ico', APP / 'Assets' / 'jocbo.ico')  # 바탕화면 바로가기 그림
    # 패키지 안은 읽기 전용이라 실행 중에 생기는 캐시는 쓰이지 않습니다. 미리 만든 것도 뺍니다.
    for cache in APP.rglob('__pycache__'):
        shutil.rmtree(cache, ignore_errors=True)

    resources()
    out = ROOT / 'build' / 'jocbo.msix'
    out.unlink(missing_ok=True)
    subprocess.run([makeappx(), 'pack', '/d', str(APP), '/p', str(out), '/o'], check=True)
    print('완료:', out, f'{out.stat().st_size / 1e6:.1f}MB')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '')
