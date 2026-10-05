"""우리의 족보 - 설치 파일에 넣을 프로그램 폴더를 build\\app 에 만듭니다.

파이썬(임베디드판)과 꾸러미, 판독 모델까지 모두 넣어서 받는 컴퓨터에는
아무것도 따로 설치하지 않아도 되게 합니다. 그 뒤 jocbo.iss 로 exe 를 만듭니다.

    py -3.12 desktop\\build.py           평소 판 (db/initial.db 와 uploads 를 그대로 넣음)
    py -3.12 desktop\\build.py --store   Microsoft Store 에 올릴 판

Store 판은 저장소의 db/initial.db(실제 계정과 실존 인물 기록)와 uploads(실제 사진)를
넣지 않고, 데모 계정 하나와 가상 인물 예제(金海金氏)만 든 족보를 새로 만들어 넣습니다.
"""
import io
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

PYTHON = '3.12.10'
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build' / 'app'
RUNTIME = OUT / 'python'
SITE = RUNTIME / 'Lib' / 'site-packages'


def run(*args, **kwargs):
    print('>', *args, flush=True)
    subprocess.run(args, check=True, **kwargs)


def python_runtime():
    url = f'https://www.python.org/ftp/python/{PYTHON}/python-{PYTHON}-embed-amd64.zip'
    print('파이썬 내려받는 중:', url, flush=True)
    with urllib.request.urlopen(url) as response:
        zipfile.ZipFile(io.BytesIO(response.read())).extractall(RUNTIME)
    # 임베디드판은 ._pth 에 적힌 곳만 봅니다. 꾸러미 폴더와 프로그램 폴더를 더합니다.
    pth = next(RUNTIME.glob('python*._pth'))
    pth.write_text(pth.read_text().replace('#import site', 'import site') + 'Lib\\site-packages\n..\n')


def packages():
    # 받는 쪽과 같은 파이썬 3.12(64비트)로 받습니다. 바이너리만으로 제한하면 omegaconf 가
    # 소스판뿐인 antlr4 를 피해 옛 판(2.0)으로 내려가 판독이 깨지므로 제한하지 않습니다.
    if sys.version_info[:2] != (3, 12) or sys.maxsize < 2**32:
        sys.exit('파이썬 3.12 64비트로 돌리십시오: py -3.12 desktop\\build.py')
    run(sys.executable, '-m', 'pip', 'install', '--quiet', '--no-compile',
        '--target', str(SITE), '-r', str(ROOT / 'requirements.txt'), '-r', str(ROOT / 'requirements-ocr.txt'))
    # PC 판이 쓰지 않는 것은 뺍니다. 받는 크기와 설치 시간이 줄어듭니다.
    # - OpenCV 의 동영상 처리(FFmpeg, 31MB): 판독은 사진만 다루고, OpenCV 는 이 파일을
    #   동영상을 열 때만 불러옵니다.
    # - psycopg(15MB): PostgreSQL 서버용입니다. PC 판은 SQLite 만 씁니다.
    # 빼고도 족보 사진 42장의 판독 결과가 같고 시험이 모두 통과하는 것을 확인했습니다.
    for path in list(SITE.glob('cv2/opencv_videoio_ffmpeg*.dll')) + list(SITE.glob('psycopg*')):
        print('뺌:', path.name)
        shutil.rmtree(path) if path.is_dir() else path.unlink()


STORE = '--store' in sys.argv
DEMO = ('demo@example.test', 'DemoFamily123!')


def program():
    for folder in ('backend', 'frontend', 'db'):
        shutil.copytree(ROOT / folder, OUT / folder, ignore=shutil.ignore_patterns('__pycache__'))
    # 샘플 족보가 쓰는 사진만 넣습니다. 이 컴퓨터에서 올린 사진은 넣지 않습니다.
    # Store 판은 저장소의 사진도 넣지 않습니다(실제 족보·인물 사진).
    tracked = [] if STORE else subprocess.run(['git', 'ls-files', 'uploads'], cwd=ROOT, check=True,
                                              capture_output=True, text=True).stdout.split()
    (OUT / 'uploads').mkdir(exist_ok=True)
    for name in tracked:
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    shutil.copy2(ROOT / 'desktop' / 'launcher.py', OUT / 'launcher.py')
    shutil.copy2(ROOT / 'desktop' / 'loading.html', OUT / 'loading.html')
    shutil.copy2(ROOT / 'desktop' / 'jocbo.ico', OUT / 'jocbo.ico')
    (OUT / 'db' / 'jocbo.db').unlink(missing_ok=True)


def demo_only():
    """Store 판의 첫 족보: 데모 계정 하나와 그 계정의 가상 인물 예제(金海金氏, 20명)뿐.

    저장소의 db/initial.db 에는 실제 계정과 실존 인물 기록이 들어 있어 빼고, 같은
    자리에 새로 만든 족보를 둡니다. 설치한 PC 는 처음 실행할 때 이것을 복사해 씁니다.
    """
    target = OUT / 'db' / 'initial.db'
    target.unlink(missing_ok=True)
    script = (
        'from backend import main as m\n'
        'from backend.sample import create_sample\n'
        'm.meta.create_all(m.engine)\n'
        'with m.engine.begin() as c:\n'
        f'    uid = c.execute(m.users.insert().values(email={DEMO[0]!r}, '
        f'password_hash=m.password_hash({DEMO[1]!r}), plan="free")).inserted_primary_key[0]\n'
        '    create_sample(c, uid, m.books, m.persons, m.relations)\n')
    env = {**os.environ, 'DATABASE_URL': 'sqlite:///' + target.as_posix(), 'UPLOAD_DIR': str(OUT / 'uploads')}
    run(str(RUNTIME / 'python.exe'), '-c', script, cwd=OUT, env=env)
    import sqlite3
    with sqlite3.connect(target) as c:
        users = c.execute('select email from users').fetchall()
        people = c.execute('select count(*) from persons').fetchone()[0]
    if users != [(DEMO[0],)] or people != 20:
        sys.exit(f'Store 판 족보가 예상과 다릅니다: {users}, 인물 {people}명')
    print('Store 판 족보: 데모 계정 하나, 예제 인물', people, '명')
    # 로그인 화면에 데모 계정을 적어, 처음 받은 사람이 바로 예제를 둘러보게 합니다.
    page = OUT / 'frontend' / 'index.html'
    html = page.read_text(encoding='utf-8')
    card = '최초 이용 시 회원가입 후 로그인'
    if card not in html:
        sys.exit('로그인 화면 안내 자리를 찾지 못했습니다.')
    page.write_text(html.replace(card, f'예제로 둘러보기: {DEMO[0]} / {DEMO[1]}<br>' + card, 1), encoding='utf-8')


def ocr_models():
    """판독 모델은 처음 판독할 때 꾸러미 폴더로 내려받습니다. 여기서 미리 받아 둡니다."""
    # 한자 모델과, 한글(괄호 속 음·경력·주소)을 읽는 한국어 모델을 함께 받습니다.
    run(str(RUNTIME / 'python.exe'), '-c',
        'from backend.readscan import _reader, _korean; _reader(); assert _korean()', cwd=OUT)
    models = list(SITE.glob('rapidocr/models/*.onnx'))
    if not models or not any('korean' in p.name for p in models):
        sys.exit('판독 모델이 받아지지 않았습니다.')
    print('판독 모델:', ', '.join(p.name for p in models))


def check():
    """설치판 파이썬으로 서버 모듈을 실제로 불러 봅니다."""
    run(str(RUNTIME / 'python.exe'), '-c', 'import backend.main, uvicorn, rapidocr, opencc', cwd=OUT)


if __name__ == '__main__':
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    python_runtime()
    packages()
    program()
    if STORE:
        demo_only()
    ocr_models()
    check()
    print('완료:', OUT)
