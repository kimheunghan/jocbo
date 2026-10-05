"""우리의 족보 - 설치판을 띄웁니다.

서버를 이 프로세스 안에서 돌리고, 엣지나 크롬의 앱 창(주소창·탭 없는 창)으로
화면을 엽니다. 그 창을 닫으면 서버도 함께 멈춥니다.

족보 DB·사진·API 키는 프로그램 폴더가 아니라 %LocalAppData%\\jocbo(Store 판은
jocbo-store)에 둡니다. 새 판을 설치하거나 프로그램을 지워도 족보는 남습니다.
"""
import ctypes
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

APP = Path(__file__).resolve().parent
LOCAL = Path(os.environ.get('LOCALAPPDATA', Path.home()))
# Store 판(build.py --store)은 데모 족보로 시작하는 판이라 족보를 따로 둡니다. 같은 PC 에
# 실제 족보가 든 판(설치판·start.bat)이 있어도 그 족보를 열지 않습니다.
STORE = (APP / 'store.txt').exists()
DATA = LOCAL / ('jocbo-store' if STORE else 'jocbo')
# start.bat 판(8000)과 같이 켜 두어도 서로의 DB 를 열지 않도록 따로 둡니다.
PORT = 8770
URL = f'http://127.0.0.1:{PORT}'
TITLE = '우리의 족보'
# frontend/index.html 의 <title>. 앱 창이 떠 있는지 이 제목으로 찾습니다.
PAGE_TITLE = '우리의 족보 · 가족의 기록'
# 앱 창을 찾지 못하면 이 안내의 [확인]이 종료 단추를 대신합니다.
RUNNING = '우리의 족보가 실행 중입니다.\n\n다 쓰셨으면 [확인]을 누르십시오. 프로그램이 종료됩니다.'


def message(text, buttons=0x40):
    return ctypes.windll.user32.MessageBoxW(None, text, TITLE, buttons)


def demo_born(db):
    """Store 판이 깔아 준 데모 족보에서 시작한 DB 인지. 그 판은 데모 계정이 첫 계정입니다."""
    if not db.exists():
        return False
    import sqlite3
    try:
        with sqlite3.connect(f'file:{db}?mode=ro', uri=True) as c:
            first = c.execute('select email from users order by id limit 1').fetchone()
    except sqlite3.Error:
        return False
    return first == ('demo@example.test',)


def prepare_data():
    """처음 실행이면 족보를 마련합니다.

    설치판은 start.bat 으로 쓰던 족보(문서\\jocbo)가 있으면 그것을 가져옵니다. Store 판은
    다른 판의 족보를 가져오지 않습니다. 가져올 것이 없으면 설치에 들어 있는 족보로
    시작합니다. 이미 있는 족보는 건드리지 않습니다.
    """
    DATA.mkdir(parents=True, exist_ok=True)
    if (DATA / 'jocbo.db').exists():
        return
    if STORE:
        # 예전 Store 판은 %LocalAppData%\\jocbo 에 두었습니다. 그 족보가 데모 족보에서
        # 시작한 것(첫 계정이 데모 계정)일 때만 이어서 씁니다.
        old = LOCAL / 'jocbo'
        source = old if demo_born(old / 'jocbo.db') else None
    else:
        old = Path.home() / 'Documents' / 'jocbo'
        source = old if (old / 'jocbo.db').exists() else None
    if source:
        shutil.copy2(source / 'jocbo.db', DATA / 'jocbo.db')
        if (source / '.env').exists() and not (DATA / '.env').exists():
            shutil.copy2(source / '.env', DATA / '.env')
    else:
        shutil.copy2(APP / 'db' / 'initial.db', DATA / 'jocbo.db')
    for folder in [APP / 'uploads'] + ([source / 'uploads'] if source else []):
        if folder.is_dir():
            shutil.copytree(folder, DATA / 'uploads', dirs_exist_ok=True)
    (DATA / 'uploads').mkdir(exist_ok=True)


def answering():
    try:
        with urllib.request.urlopen(URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def browser():
    """앱 창을 열 크롬, 없으면 엣지. 윈도 10·11에는 엣지가 기본으로 깔려 있습니다.

    크롬이 먼저입니다. 엣지는 회사·학교 계정의 로그인이 끝나면 그 로그인 창을
    앱 창 위에 띄우는데, 그 창이 닫힐 때까지 앱 창을 누를 수도 끌 수도 없습니다.
    """
    bases = [os.environ.get(name) for name in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA')]
    places = [Path(base) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe' for base in bases if base]
    places += [Path(base) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe' for base in bases if base]
    return next((str(p) for p in places if p.exists()), None)


def open_window(path, url=URL):
    """평소 쓰는 브라우저 프로필로 앱 창을 엽니다.

    전용 프로필을 따로 만들면 엣지가 윈도 계정으로 저절로 로그인하며 동기화
    안내를 띄우므로, 프로필은 그대로 두고 창만 앱 창으로 엽니다.
    """
    subprocess.Popen([path, f'--app={url}', '--window-size=1280,860'])


def splash():
    """서버보다 먼저 띄우는 "여는 중" 화면. 서버가 답하면 스스로 족보 화면으로 넘어갑니다."""
    return (APP / 'loading.html').as_uri() + '?to=' + urllib.parse.quote(URL + '/', safe='')


def windows():
    """제목이 화면 제목과 똑같은 창들. 앱 창은 페이지 제목을 그대로 창 제목으로
    씁니다. 보통 탭이면 뒤에 브라우저 이름이 붙어 세지 않습니다."""
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def each(handle, _):
        if user32.IsWindowVisible(handle):
            buffer = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(handle, buffer, 256)
            if buffer.value == PAGE_TITLE:
                found.append(handle)
        return True

    user32.EnumWindows(each, None)
    return found


def windows_open():
    return len(windows())


def bring_forward():
    """이미 떠 있는 창을 앞으로 가져옵니다. 최소화돼 있으면 되살립니다."""
    user32 = ctypes.windll.user32
    for handle in windows():
        if user32.IsIconic(handle):
            user32.ShowWindow(handle, 9)
        user32.SetForegroundWindow(handle)


# 이 실행기가 떠 있는 동안 잡고 있는 표시. 두 번째로 눌린 실행기는 이것을 보고 물러납니다.
_running = None


def already_running():
    global _running
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _running = kernel32.CreateMutexW(None, False, r'Local\jocbo-launcher')
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


def main():
    # 느리게 뜬다고 여러 번 눌러도 하나만 뜹니다. 이미 실행 중이면 그 창을 앞으로 가져옵니다.
    if already_running():
        bring_forward()
        return
    path = browser()
    # 누르자마자 창부터 띄웁니다. 서버가 준비되면 그 창이 족보 화면으로 넘어갑니다.
    if path:
        open_window(path, splash())

    prepare_data()
    os.environ['DATABASE_URL'] = 'sqlite:///' + str(DATA / 'jocbo.db')
    os.environ['UPLOAD_DIR'] = str(DATA / 'uploads')
    os.environ['JOCBO_ENV_FILE'] = str(DATA / '.env')

    sys.path.insert(0, str(APP))
    import uvicorn
    server = uvicorn.Server(uvicorn.Config('backend.main:app', host='127.0.0.1', port=PORT,
                                           log_level='warning', log_config=None))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(240):
        if answering() or not thread.is_alive():
            break
        time.sleep(0.5)
    if not answering():
        message(f'서버를 띄우지 못했습니다.\n\n자세한 내용: {DATA / "jocbo.log"}', 0x10)
        return

    if path:
        # 창이 뜨기를 기다렸다가, 모두 닫히면 끝냅니다. 잠깐 사라지는 순간(새로
        # 고침 등)에 끝나지 않도록 몇 번 연달아 없을 때만 닫힌 것으로 봅니다.
        for _ in range(60):
            if windows_open():
                break
            time.sleep(0.5)
        else:
            message(RUNNING)
        missing = 0
        while missing < 3:
            missing = 0 if windows_open() else missing + 1
            time.sleep(1)
    else:
        webbrowser.open(URL)
        message(RUNNING)
    server.should_exit = True
    thread.join(10)


if __name__ == '__main__':
    DATA.mkdir(parents=True, exist_ok=True)
    # pythonw 로 뜨면 출력할 곳이 없으므로 기록 파일로 보냅니다.
    log = open(DATA / 'jocbo.log', 'a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stderr = log
    print(time.strftime('\n%Y-%m-%d %H:%M:%S 시작'))
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        message(f'오류로 멈췄습니다.\n\n자세한 내용: {DATA / "jocbo.log"}', 0x10)
