"""설치 파일판(exe)의 새 판 알림과 설치 파일 받기.

홈페이지의 최신 판 정보(latest.json)를 하루에 한 번 읽어, 지금 판보다 새 판이 있으면
화면에 알립니다. [지금 업데이트]를 누르면 설치 파일을 받아 확인값(SHA-256)을 맞춰 보고,
맞으면 실행기(desktop/launcher.py)가 프로그램을 닫은 뒤 설치합니다.

Store 판은 Store 가 업데이트하므로 묻지 않습니다. 개발 중 실행(start.bat)과 공유 서버도
판 번호가 없으므로 묻지 않습니다.

latest.json 형식(FindInside 와 같음):
    {"version": "2026.11.11", "url": "https://jocbo.pages.dev/download/store-v2026.11.11/jocbo-setup.exe",
     "sha256": "64자리 확인값", "notes": "바뀐 점 한두 줄"}
"""
import hashlib
import json
import os
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LATEST_URL = os.getenv('JOCBO_LATEST_URL', 'https://jocbo.pages.dev/latest.json')
# 설치 파일은 이 주소에서만 받습니다.
ALLOWED = tuple(os.getenv('JOCBO_DOWNLOAD_PREFIX', 'https://jocbo.pages.dev/download/').split())
ONE_DAY = 24 * 60 * 60

# 받아서 확인을 마친 설치 파일. 실행기가 이것을 보고 프로그램을 닫은 뒤 설치합니다.
pending = None


def version():
    """이 프로그램의 판 번호. 빌드할 때 version.txt 에 적습니다(desktop/build.py)."""
    try:
        return (ROOT / 'version.txt').read_text(encoding='utf-8').strip()
    except OSError:
        return ''


def channel():
    """실행기가 알려 주는 판 종류: 'exe'(설치 파일판), 'store'(Store 판), ''(그 밖)."""
    return os.getenv('JOCBO_CHANNEL', '')


def parse(text):
    return tuple(int(part) for part in text.split('.')) if re.fullmatch(r'\d+(\.\d+){0,3}', text or '') else None


def newer(candidate, current):
    a, b = parse(candidate), parse(current)
    return bool(a and b and a > b)


def _state_file():
    folder = os.getenv('JOCBO_DATA_DIR')
    return Path(folder) / 'update.json' if folder else None


def _load():
    path = _state_file()
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path else {}
    except (OSError, ValueError):
        return {}


def _save(state):
    path = _state_file()
    if path:
        try:
            path.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
        except OSError:
            pass


def valid(info, current):
    """믿고 받을 수 있는 정보인가: 더 새 판, 허용한 주소, 64자리 확인값."""
    return (isinstance(info, dict) and newer(str(info.get('version', '')), current)
            and str(info.get('url', '')).startswith(ALLOWED)
            and re.fullmatch(r'[0-9a-fA-F]{64}', str(info.get('sha256', ''))) is not None)


def fetch():
    request = urllib.request.Request(LATEST_URL, headers={'User-Agent': 'jocbo-desktop/1.0', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read(65536))


def available(now=None):
    """알릴 새 판이 있으면 그 정보, 없으면 None. 실패하면 조용히 None 입니다."""
    current = version()
    if channel() != 'exe' or not parse(current):
        return None
    now = now or time.time()
    state = _load()
    if 'later' in state and now - state['later'] < ONE_DAY:
        return None
    if 'checked' not in state or now - state['checked'] >= ONE_DAY or not valid(state.get('latest'), current):
        try:
            info = fetch()
        except Exception:
            return None
        state.update(checked=now, latest=info if isinstance(info, dict) else None)
        _save(state)
    info = state.get('latest')
    return info if valid(info, current) else None


def later(now=None):
    """[나중에]: 하루 동안 다시 묻지 않습니다."""
    state = _load()
    state['later'] = now or time.time()
    _save(state)


class UpdateError(Exception):
    pass


def download(info):
    """설치 파일을 받아 확인값을 맞춰 보고, 맞으면 그 경로를 pending 에 둡니다."""
    global pending
    if not valid(info, version()):
        raise UpdateError('새 판 정보가 올바르지 않습니다.')
    folder = Path(os.getenv('JOCBO_DATA_DIR') or ROOT) / 'update'
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob('*.exe'):
        old.unlink(missing_ok=True)
    target = folder / f"jocbo-setup-{info['version']}.exe"
    digest = hashlib.sha256()
    try:
        request = urllib.request.Request(info['url'], headers={'User-Agent': 'jocbo-desktop/1.0'})
        with urllib.request.urlopen(request, timeout=60) as response, open(target, 'wb') as out:
            while chunk := response.read(1 << 20):
                digest.update(chunk)
                out.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise UpdateError('새 판을 받지 못했습니다. 인터넷 연결을 확인한 뒤 다시 눌러 주십시오.')
    if digest.hexdigest().lower() != info['sha256'].lower():
        target.unlink(missing_ok=True)
        raise UpdateError('받은 파일이 올바르지 않아 설치하지 않았습니다. 지금 판을 그대로 씁니다.')
    pending = target
    return target
