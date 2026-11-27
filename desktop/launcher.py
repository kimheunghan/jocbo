"""우리의 족보 - 설치판을 띄웁니다.

서버를 이 프로세스 안에서 돌리고, 엣지나 크롬의 앱 창(주소창·탭 없는 창)으로
화면을 엽니다. 그 창을 닫으면 서버도 함께 멈춥니다.

족보 DB·사진·API 키는 프로그램 폴더가 아니라 %LocalAppData%\\jocbo 에 둡니다.
새 판을 설치하거나 프로그램을 지워도 족보는 남습니다.
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
DATA = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'jocbo'
# start.bat 판(8000)과 같이 켜 두어도 서로의 DB 를 열지 않도록 따로 둡니다.
PORT = 8770
URL = f'http://127.0.0.1:{PORT}'
TITLE = '우리의 족보'
# frontend/index.html 의 <title>. 앱 창이 떠 있는지 이 제목으로 찾습니다.
PAGE_TITLE = '우리의 족보 · 가족의 기록'
# 화면은 20초마다 서버에 신호(/api/alive)를 보냅니다. 최소화한 창은 브라우저가
# 1분에 한 번으로 늦추므로, 이만큼 신호가 없을 때만 창이 닫힌 것으로 봅니다.
# 번역 등으로 창 제목이 바뀌어도 이 신호로 창이 떠 있음을 압니다.
QUIET = 150
# 앱 창을 찾지 못하면 이 안내의 [확인]이 종료 단추를 대신합니다.
RUNNING = '우리의 족보가 실행 중입니다.\n\n다 쓰셨으면 [확인]을 누르십시오. 프로그램이 종료됩니다.'


def message(text, buttons=0x40):
    return ctypes.windll.user32.MessageBoxW(None, text, TITLE, buttons)


def prepare_data():
    """처음 실행이면 족보를 마련합니다.

    start.bat 으로 쓰던 족보(문서\\jocbo)가 있으면 그것을 가져오고, 없으면 설치에
    들어 있는 샘플 족보로 시작합니다. 이미 있는 족보는 건드리지 않습니다.
    """
    DATA.mkdir(parents=True, exist_ok=True)
    if (DATA / 'jocbo.db').exists():
        return
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


# Store 판의 바탕화면 바로가기 이름(desktop/msix/AppxManifest.xml 의 desktop7:Shortcut)과 앱 Id.
SHORTCUT = '우리의 족보.lnk'
APP_ID = 'Jocbo'


def package_family():
    """Store(MSIX) 판으로 떠 있으면 패키지 패밀리 이름, 아니면 None."""
    try:
        length = ctypes.c_uint32(0)
        get = ctypes.windll.kernel32.GetCurrentPackageFamilyName
        if get(ctypes.byref(length), None) != 122:  # ERROR_INSUFFICIENT_BUFFER 가 아니면 패키지 밖
            return None
        buffer = ctypes.create_unicode_buffer(length.value)
        return buffer.value if get(ctypes.byref(length), buffer) == 0 else None
    except (AttributeError, OSError):
        return None


def needs_fix(target, arguments, aumid):
    """바로가기를 앱 이름으로 여는 모양으로 고쳐 써야 하는지.

    Store 판이 만든 바로가기는 C:\\Program Files\\WindowsApps\\<패키지>_<버전>_…\\python\\pythonw.exe
    를 직접 가리킵니다. 그 폴더는 Windows 가 잠가 두어, 바로가기 정보가 조금만 어긋나도
    "액세스할 수 없습니다" 오류가 나고, 폴더 이름은 판마다 바뀝니다. 시작 메뉴처럼
    explorer.exe shell:AppsFolder\\<앱 이름> 으로 열면 늘 지금 깔린 판이 열립니다.
    """
    if target.lower().endswith('\\explorer.exe') and arguments.strip().lower() == f'shell:appsfolder\\{aumid}'.lower():
        return False
    return '\\windowsapps\\' in target.lower()


def fix_shortcut():
    """Store 판이면 바탕화면 바로가기가 업데이트 뒤에도 열리도록 앱 이름으로 여는 모양으로 고칩니다.

    바로가기가 없으면(손님이 지웠으면) 만들지 않습니다. 설치 파일판(exe)의 바로가기는
    고정 폴더를 가리키므로 건드리지 않습니다. 실패해도 프로그램은 그대로 뜹니다.
    """
    family = package_family()
    if not family:
        return
    aumid = f'{family}!{APP_ID}'
    icon = APP / 'Assets' / 'jocbo.ico'
    # 바로가기는 COM(WScript.Shell)으로만 읽고 쓸 수 있어 PowerShell 에 맡깁니다.
    script = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        f"$p=Join-Path $d '{SHORTCUT}';"
        "if(-not(Test-Path -LiteralPath $p)){'none';exit};"
        "$w=New-Object -ComObject WScript.Shell;$s=$w.CreateShortcut($p);"
        "$s.TargetPath+'|'+$s.Arguments"
    )
    found = powershell(script)
    if not found or found == 'none' or '|' not in found:
        return
    target, arguments = found.split('|', 1)
    if not needs_fix(target, arguments, aumid):
        return
    windir = os.environ.get('WINDIR', r'C:\Windows')
    powershell(
        "$d=[Environment]::GetFolderPath('Desktop');"
        f"$p=Join-Path $d '{SHORTCUT}';"
        "$w=New-Object -ComObject WScript.Shell;$s=$w.CreateShortcut($p);"
        f"$s.TargetPath='{windir}\\explorer.exe';"
        f"$s.Arguments='shell:AppsFolder\\{aumid}';"
        "$s.WorkingDirectory='';"
        f"$s.IconLocation='{icon},0';"
        "$s.Save();'ok'"
    )
    print('바탕화면 바로가기를 고쳤습니다:', target, '->', aumid)


def powershell(script):
    """PowerShell 한 줄을 창 없이 돌리고 출력을 돌려줍니다. 실패하면 None."""
    import base64
    encoded = base64.b64encode(('[Console]::OutputEncoding=[Text.Encoding]::UTF8;' + script).encode('utf-16-le')).decode()
    try:
        done = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                              capture_output=True, timeout=30, creationflags=0x08000000)  # CREATE_NO_WINDOW
    except (OSError, subprocess.TimeoutExpired) as error:
        print('PowerShell 실패:', error)
        return None
    if done.returncode:
        print('PowerShell 실패:', done.stderr.decode('utf-8', 'replace')[-500:])
        return None
    return done.stdout.decode('utf-8', 'replace').strip()


def quietly(work):
    """곁가지 일이 실패해도 프로그램은 멈추지 않게 하고, 기록 파일에만 남깁니다."""
    try:
        work()
    except Exception:
        import traceback
        traceback.print_exc()


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
    # 세로가 짧은 노트북(배율 125%)에서도 창 아래가 화면 밖으로 내려가지 않는 크기입니다.
    # 브라우저가 예전 크기를 기억하고 있으면 이 값은 무시되므로, 창이 뜬 뒤 fit_windows()가
    # 화면에 맞춰 다시 잡습니다.
    subprocess.Popen([path, f'--app={url}', '--window-size=1280,806'])


class _Rect(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long), ('right', ctypes.c_long), ('bottom', ctypes.c_long)]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [('size', ctypes.c_ulong), ('monitor', _Rect), ('work', _Rect), ('flags', ctypes.c_ulong)]


# 가로:세로. 왼쪽 목록과 오른쪽 족보 화면이 나란히 서는 모양입니다.
WINDOW_RATIO = 1.6


def fit_size(work_width, work_height):
    """작업 표시줄을 뺀 화면 안에서 가로 90%, 세로 95%를 넘지 않는 16:10 크기."""
    width, height = work_width * 0.9, work_height * 0.95
    if width / height > WINDOW_RATIO:
        width = height * WINDOW_RATIO
    else:
        height = width / WINDOW_RATIO
    return int(width), int(height)


def fit_windows():
    """앱 창을 그 창이 놓인 화면에 맞춰 가로로 넓게(16:10) 가운데에 놓습니다.

    크롬·엣지는 앱 창의 예전 크기를 기억해 두었다가 --window-size 를 무시하고
    그 크기로 엽니다. 그 값이 세로로 긴 모양이면 매번 정사각형에 가까운 창이
    뜨므로, 창이 뜬 뒤 여기서 다시 잡습니다. 최대화해 둔 창은 그대로 둡니다.
    """
    user32 = ctypes.windll.user32
    for handle in windows():
        if user32.IsZoomed(handle) or user32.IsIconic(handle):
            continue
        info = _MonitorInfo(size=ctypes.sizeof(_MonitorInfo))
        monitor = user32.MonitorFromWindow(ctypes.c_void_p(handle), 2)  # MONITOR_DEFAULTTONEAREST
        if not user32.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info)):
            continue
        work = info.work
        width, height = fit_size(work.right - work.left, work.bottom - work.top)
        left = work.left + (work.right - work.left - width) // 2
        top = work.top + (work.bottom - work.top - height) // 2
        # A window stretched to full height (Windows snap) takes the first call as its
        # size to restore to and stays stretched; the next call then applies. So the
        # size is checked and set again until it holds.
        for _ in range(3):
            user32.SetWindowPos(ctypes.c_void_p(handle), None, left, top, width, height, 0x0014)  # NOZORDER|NOACTIVATE
            time.sleep(0.3)
            now = _Rect()
            user32.GetWindowRect(ctypes.c_void_p(handle), ctypes.byref(now))
            if (now.right - now.left, now.bottom - now.top) == (width, height):
                break


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


def in_use():
    """앱 창이 떠 있는지. 제목으로 찾거나, 화면이 최근에 신호를 보냈으면 떠 있습니다."""
    from backend import main as backend
    return windows_open() or time.time() - backend.last_seen < QUIET


def bring_forward():
    """이미 떠 있는 창을 앞으로 가져옵니다. 최소화돼 있으면 되살립니다."""
    user32 = ctypes.windll.user32
    for handle in windows():
        if user32.IsIconic(handle):
            user32.ShowWindow(handle, 9)
        user32.SetForegroundWindow(handle)


def allow_forward():
    """아이콘을 누른 이 실행기가 가진 "앞으로 나올 권리"를 브라우저에도 넘깁니다.
    넘기지 않으면 첫 클릭에 앱 창이 다른 창 뒤에 뜹니다."""
    ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY


# 이 실행기가 떠 있는 동안 잡고 있는 표시. 두 번째로 눌린 실행기는 이것을 보고 물러납니다.
_running = None


def already_running():
    global _running
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _running = kernel32.CreateMutexW(None, False, r'Local\jocbo-launcher')
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


def main():
    # 느리게 뜬다고 여러 번 눌러도 하나만 뜹니다. 이미 실행 중이면 그 창을 앞으로 가져옵니다.
    # 창을 닫은 직후라 서버가 아직 떠 있으면, 앞으로 가져올 창이 없으니 새로 엽니다.
    if already_running():
        if windows():
            bring_forward()
        elif browser():
            allow_forward()
            open_window(browser())
            for _ in range(20):
                if windows():
                    fit_windows()
                    break
                time.sleep(0.5)
        else:
            webbrowser.open(URL)
        return
    path = browser()
    # 누르자마자 창부터 띄웁니다. 서버가 준비되면 그 창이 족보 화면으로 넘어갑니다.
    if path:
        allow_forward()
        open_window(path, splash())
    # 바탕화면 바로가기 고치기는 화면을 기다리게 하지 않도록 따로 돌립니다.
    threading.Thread(target=quietly, args=(fix_shortcut,), daemon=True).start()

    prepare_data()
    os.environ['DATABASE_URL'] = 'sqlite:///' + str(DATA / 'jocbo.db')
    os.environ['UPLOAD_DIR'] = str(DATA / 'uploads')
    os.environ['JOCBO_ENV_FILE'] = str(DATA / '.env')
    os.environ['JOCBO_DATA_DIR'] = str(DATA)
    # 새 판 알림은 설치 파일판만 합니다. Store 판은 Store 가 업데이트합니다.
    os.environ['JOCBO_CHANNEL'] = 'store' if package_family() else 'exe'
    # 지난번 업데이트로 받아 둔 설치 파일은 이제 필요 없습니다.
    for old in (DATA / 'update').glob('*.exe'):
        try:
            old.unlink()
        except OSError:
            pass

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
            if in_use():
                break
            time.sleep(0.5)
        else:
            message(RUNNING)
        # 화면이 늦게 바뀌어 제목이 아직 없으면 잠깐 더 기다렸다가 크기를 맞춥니다.
        for _ in range(10):
            if windows():
                break
            time.sleep(0.5)
        fit_windows()
        # 첫 클릭에 창이 다른 창 뒤에 떴더라도 한 번 앞으로 가져옵니다.
        bring_forward()
        missing = 0
        while missing < 3 and not updating():
            missing = 0 if in_use() else missing + 1
            time.sleep(1)
    else:
        webbrowser.open(URL)
        message(RUNNING)
    server.should_exit = True
    thread.join(10)
    if updating():
        install_update(updating())


def updating():
    """[지금 업데이트]로 받아 확인을 마친 설치 파일. 없으면 None."""
    from backend import update
    return update.pending


def install_update(setup):
    """앱 창을 닫고, 이 실행기가 끝난 뒤 설치 파일을 창 없이 돌립니다.

    설치 파일은 같은 폴더에 덮어 깔고(족보 자료는 %LocalAppData%\\jocbo 에 있어 그대로),
    바탕화면 아이콘을 맞춘 뒤 /RELAUNCH=1 을 보고 프로그램을 다시 켭니다(desktop/jocbo.iss).
    """
    user32 = ctypes.windll.user32
    for handle in windows():
        user32.PostMessageW(ctypes.c_void_p(handle), 0x0010, 0, 0)  # WM_CLOSE
    print('새 판 설치:', setup)
    script = (f"Wait-Process -Id {os.getpid()} -Timeout 60 -ErrorAction SilentlyContinue;"
              "Start-Process -FilePath '" + str(setup).replace("'", "''") + "'"
              " -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/RELAUNCH=1'")
    # 이 실행기가 끝나도 남아 있도록 떼어 내어 돌립니다.
    subprocess.Popen(['powershell', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-Command', script],
                     creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


if __name__ == '__main__':
    # 창 크기를 실제 화면 픽셀로 다룹니다. 이것이 없으면 배율 125% 화면에서
    # 윈도가 좌표를 늘려 잡아 창이 화면보다 커집니다.
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except (AttributeError, OSError):
        pass
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
