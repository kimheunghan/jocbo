"""우리의 족보 - 설치 파일에 넣을 프로그램 폴더를 build\\app 에 만듭니다.

파이썬(임베디드판)과 꾸러미, 판독 모델까지 모두 넣어서 받는 컴퓨터에는
아무것도 따로 설치하지 않아도 되게 합니다. 그 뒤 jocbo.iss 로 exe 를 만듭니다.

    py -3.12 desktop\\build.py
"""
import io
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


def program():
    for folder in ('backend', 'frontend', 'db'):
        shutil.copytree(ROOT / folder, OUT / folder, ignore=shutil.ignore_patterns('__pycache__'))
    # 샘플 족보가 쓰는 사진만 넣습니다. 이 컴퓨터에서 올린 사진은 넣지 않습니다.
    tracked = subprocess.run(['git', 'ls-files', 'uploads'], cwd=ROOT, check=True,
                             capture_output=True, text=True).stdout.split()
    for name in tracked:
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    shutil.copy2(ROOT / 'desktop' / 'launcher.py', OUT / 'launcher.py')
    shutil.copy2(ROOT / 'desktop' / 'loading.html', OUT / 'loading.html')
    shutil.copy2(ROOT / 'desktop' / 'jocbo.ico', OUT / 'jocbo.ico')
    (OUT / 'db' / 'jocbo.db').unlink(missing_ok=True)


def ocr_models():
    """판독 모델은 처음 판독할 때 꾸러미 폴더로 내려받습니다. 여기서 미리 받아 둡니다."""
    run(str(RUNTIME / 'python.exe'), '-c', 'from backend.readscan import _reader; _reader()', cwd=OUT)
    models = list(SITE.glob('rapidocr/models/*.onnx'))
    if not models:
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
    ocr_models()
    check()
    print('완료:', OUT)
