"""Store 판 바탕화면 바로가기를 고쳐 쓸지 정하는 규칙."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop'))
import launcher  # noqa: E402

AUMID = 'kimheunghan.3981136B17516_e0edtm1ypyj4j!Jocbo'


def test_a_shortcut_into_the_store_folder_is_rewritten():
    # Store 가 설치·업데이트 때 만드는 모양: 판마다 바뀌는 잠긴 폴더를 직접 가리킵니다.
    target = r'C:\Program Files\WindowsApps\kimheunghan.3981136B17516_2026.11.10.0_x64__e0edtm1ypyj4j\python\pythonw.exe'
    assert launcher.needs_fix(target, '-m launcher', AUMID)


def test_a_shortcut_that_opens_the_app_by_name_is_left_alone():
    assert not launcher.needs_fix(r'C:\WINDOWS\explorer.exe', f'shell:AppsFolder\\{AUMID}', AUMID)


def test_the_installer_shortcut_is_left_alone():
    # 설치 파일판(exe)은 늘 같은 폴더에 깔리므로 건드리지 않습니다.
    target = r'C:\Users\someone\AppData\Local\Programs\jocbo\python\pythonw.exe'
    assert not launcher.needs_fix(target, '"C:\\Users\\someone\\AppData\\Local\\Programs\\jocbo\\launcher.py"', AUMID)


def test_outside_a_store_package_nothing_is_touched(monkeypatch):
    calls = []
    monkeypatch.setattr(launcher, 'package_family', lambda: None)
    monkeypatch.setattr(launcher, 'powershell', lambda script: calls.append(script))
    launcher.fix_shortcut()
    assert calls == []


def store(monkeypatch, tmp_path, answer):
    calls = []
    monkeypatch.setattr(launcher, 'DATA', tmp_path)
    monkeypatch.setattr(launcher, 'package_family', lambda: 'kimheunghan.3981136B17516_e0edtm1ypyj4j')
    monkeypatch.setattr(launcher, 'stable_icon', lambda family: tmp_path / 'jocbo.ico')
    monkeypatch.setattr(launcher, 'powershell', lambda script: calls.append(script) or answer)
    return calls


def test_the_store_build_makes_the_desktop_icon_once(monkeypatch, tmp_path):
    # Windows 가 만들던 아이콘 대신, 처음 켜질 때 앱 이름으로 여는 아이콘을 만듭니다.
    calls = store(monkeypatch, tmp_path, 'none')
    launcher.fix_shortcut()
    assert len(calls) == 2 and 'shell:AppsFolder' in calls[1]
    assert (tmp_path / 'desktop-icon-made').exists()


def test_a_deleted_shortcut_is_not_made_again(monkeypatch, tmp_path):
    (tmp_path / 'desktop-icon-made').touch()
    calls = store(monkeypatch, tmp_path, 'none')
    launcher.fix_shortcut()
    assert len(calls) == 1  # 있는지 보기만 하고 만들지 않습니다.


def test_the_installer_icon_is_left_alone_on_a_pc_with_both(monkeypatch, tmp_path):
    calls = store(monkeypatch, tmp_path, r'C:\Users\a\AppData\Local\Programs\jocbo\python\pythonw.exe|"launcher.py"|x.ico,0')
    launcher.fix_shortcut()
    assert len(calls) == 1


def test_an_icon_into_the_store_folder_is_rewritten(monkeypatch, tmp_path):
    target = r'C:\Program Files\WindowsApps\kimheunghan.3981136B17516_2026.11.10.0_x64__e0edtm1ypyj4j\python\pythonw.exe'
    calls = store(monkeypatch, tmp_path, f'{target}|-m launcher|{target},0')
    launcher.fix_shortcut()
    assert len(calls) == 2 and 'explorer.exe' in calls[1]
