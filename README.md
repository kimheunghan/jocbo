# 우리의 족보 — FastAPI 족보·가계도 MVP

한국어 화면에서 회원가입, 로그인, 족보 생성, 인물 관리, 가족 관계, 검색, 가계도, 족보책 미리보기와 인쇄/PDF 저장을 사용할 수 있습니다.

가계도는 기록된 세대를 그대로 줄로 쓰고 부부를 한 묶음으로 배치하며, 카드의 `+` 로 부모·자녀·배우자·형제자매를 그 자리에서 추가합니다. 재혼이면 배우자별로 자녀 선이 갈립니다. 족보책 미리보기는 한 면에 여섯 세대 칸을 두고 세로쓰기 한자로 전통 서책 형식을 재현합니다.

`db/seed.sql` 과 `db/seed.py` 의 예제는 가상 인물입니다. `db/seed_reference_page.py` 는 실제 족보 사진에서 옮긴 기록이므로 **실존 인물의 이름과 생년월일이 들어 있습니다.** 공개 저장소에서 쓸 때는 이 점을 알고 쓰세요.

## 빠른 실행 (Python 3.12 권장)

Windows PowerShell에서 저장소 폴더를 열고:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn backend.main:app --reload
```

macOS / Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn backend.main:app --reload
```

http://127.0.0.1:8000 에서 회원가입 후 로그인합니다. **가상 가족 예제 추가**로 본인 계정에 예제를 만들 수 있습니다. API 문서는 `/docs`입니다. 기본 모드는 `jocbo.db` SQLite 파일을 자동 생성하므로 별도 DB 설치 없이 확인할 수 있습니다.

## PostgreSQL 실행

Docker와 Docker Compose가 있다면:

```sh
docker compose up --build
```

http://127.0.0.1:8000 에 접속합니다. PostgreSQL 17과 앱이 함께 시작되고, DB와 첨부파일은 Docker 볼륨에 보관됩니다. 초기 빈 DB에서 `db/schema.sql`이 적용됩니다. 기본 암호는 로컬 샘플 전용이며 공개 서비스에 그대로 사용하지 마세요.

이미 설치한 PostgreSQL을 사용할 경우 빈 DB를 만든 뒤:

```sh
psql -d jocbo -v ON_ERROR_STOP=1 -f db/schema.sql
```

PowerShell에서 연결 설정 후 앱을 실행합니다:

```powershell
$env:DATABASE_URL='postgresql+psycopg://사용자:비밀번호@localhost:5432/jocbo'
.\.venv\Scripts\python -m uvicorn backend.main:app --reload
```

`.env.example`은 설정 참고용입니다. 앱이 `.env`를 자동으로 읽지는 않으므로 환경변수로 지정하세요. SQLite 데이터가 PostgreSQL로 자동 이관되지는 않습니다.

## 샘플 SQL

선택적으로 `psql -d jocbo -v ON_ERROR_STOP=1 -f db/seed.sql`을 실행합니다. SQLite에서는 `.venv`의 Python으로 `python -m db.seed`를 실행합니다. Compose에서는 `docker compose exec app python -m db.seed`를 사용합니다.

- 데모 로그인: `demo@example.test`
- 데모 비밀번호: `DemoFamily123!`
- seed는 가상 인물 4명, 부모-자녀와 배우자 관계를 생성합니다. 반복 실행 시 중복 삽입을 하지 않습니다.
- 공용 데모 계정은 테스트 환경에서만 사용하세요. 기본 시작 시 자동 생성하지 않습니다.

## 화면과 기능

1. 상단의 **+ 새 족보**를 누르면 레이어 창이 열려 족보를 만들고, 왼쪽에서 족보를 고릅니다. **예제 추가**도 상단에 있습니다.
2. 족보를 고르면 제목 아래에 성씨·본관·파명·권이 가로로 펼쳐지고, 왼쪽 **나의 족보** 아래에 그 족보를 고치는 칸이 이어서 나옵니다. 사이드바와 본문 사이의 세로선을 마우스로 끌면 사이드바 폭이 바뀌고(두 번 누르면 기본값), 그 폭은 브라우저에 기억됩니다.
3. 족보명·성씨·본관·파명을 한자로 적어도 입력칸 아래에 한글 음이 함께 보입니다(`淸道金氏大同譜` → 청도김씨대동보). 왼쪽 위 **한글로 보기**를 누르면 족보 목록·제목·정보줄과 왼쪽 입력칸이 모두 한글로 바뀝니다. 한글로 본 채 저장해도 손대지 않은 칸은 원래 한자 그대로 남습니다.
4. 인물 등록에서 한글명, 한자명, 본관, 세대, 성별, 출생·사망일, 생애 기록을 입력합니다. 본관은 새 인물을 등록할 때 족보의 본관이 기본값으로 들어가며, 혼인으로 들어온 사람은 친가 본관으로 고쳐 입력합니다. 족보책의 배우자 표기(`配天安全氏京愛`)에 쓰입니다.
5. 인물 카드를 누르면 수정·삭제와 파일 업로드를 할 수 있습니다. 삭제 시 관련 관계와 첨부파일도 삭제됩니다.
6. 기준 인물·관계·대상 인물을 선택하여 부모 → 자녀 또는 배우자 관계를 등록합니다. 본인과의 관계, 족보 간 연결, 중복 관계, 조상 순환을 차단합니다.
7. 한글명·한자명·메모를 검색하고 목록, 가계도, 족보책 보기로 전환합니다.
8. 가계도는 기록된 세대를 그대로 줄로 쓰고, 부부를 한 묶음으로 놓아 자녀 선이 부부 사이에서 내려옵니다. 같은 줄 안의 순서는 족보책과 같은 규칙(아버지 순 → 아들 연장자순 → 딸)입니다.
9. 가계도 카드에 마우스를 올리면 위·아래·좌·우에 **+** 가 나타나 부모·자녀·배우자·형제자매를 그 자리에서 추가합니다. 인물 등록 창이 관계가 지정된 채 열리고 세대·본관이 미리 채워지며, 저장하면 인물과 관계가 함께 생성됩니다. 기존 인물과 연결할 수도 있습니다.
10. 배우자가 여러 명이면 가계도에서 본인을 가운데 두고 양옆에 배우자를 놓으며, 각 혼인의 자녀 선이 따로 내려옵니다. 자녀를 추가할 때 **다른 부모**를 골라 어느 배우자와의 자녀인지 지정합니다.
11. 가계도 위의 **표시 항목**에서 세대·한자명·본관·출생일·사망일·나이·사진·기록/생애·성별 색을 켜고 끕니다. 사진은 인물에 첨부한 PNG·JPG 중 첫 장을 쓰며, 선택값은 브라우저에 기억됩니다.
12. 족보책 미리보기는 한 면에 6개 세대 칸을 그리고, 다음 면은 앞 면의 마지막 세대를 다시 첫 칸에 올려 이어붙입니다. 기록이 없는 세대도 칸을 비워 그려 가로·세로 선이 면 전체에 이어집니다. 이름은 성씨를 떼고 적고, 날짜는 `一九五四年甲午五月二十九日生`처럼 간지를 붙인 한자로 표기합니다.
13. **족보책 인쇄 / PDF**를 누르고 브라우저의 **PDF로 저장**을 선택합니다. 검색을 해제하고 선택한 족보 전체를 출력합니다. 전통 서책을 참고한 세대 구분·세로 한자명·생애 기록 형식이며 특정 문중의 편집 규격을 보증하지 않습니다.

## 구조

```text
backend/main.py        FastAPI API, 사용자 인증, 데이터 모델
frontend/index.html    화면 구조
frontend/style.css     색·글꼴·여백 규칙 (한지/먹 기준)
frontend/ux.css        가계도·족보책·대화상자 세부 규칙
frontend/app.js        화면 동작, 가계도 배치, 족보책 조판
frontend/hanjaeum.json 한글 음 → 한자 후보 사전
db/schema.sql          PostgreSQL DDL
db/seed.sql            가상 데이터
db/seed.py             선택적 seed 실행기
db/seed_reference_page.py  淸道金氏大同譜 卷之九 116·618쪽 판독 기록 (실제 인물)
db/migrations/         번호순 SQL 변경 파일
uploads/               비공개 첨부파일 (Git 제외)
tests/test_api.py      API 통합 테스트
compose.yaml           PostgreSQL + 앱 실행
```

## 족보 사진 가져오기

`db/seed_reference_page.py` 는 淸道金氏大同譜 卷之九 외오산 116쪽(21~26세)·618쪽(26~31세) 사진에서 판독한 기록을 1번 족보에 넣습니다.

```powershell
.\.venv\Scripts\python -m db.seed_reference_page
```

- 이름·세대·부모 관계는 큰 글자에서 옮겼고, 사진으로 판독되지 않는 소주(小註)는 비운 채 각 인물 메모에 "판독 미확정"으로 적어 두었습니다.
- 원본 날짜는 음력입니다. 앱의 날짜 칸이 받는 형식에 맞춰 ISO(`YYYY-MM-DD`)로 옮겼으므로 양력 환산값이 아닙니다.
- 족보책 화면은 저장된 날짜에서 간지를 계산해 `一九五四年甲午五月二十九日生` 형태로 표기합니다.
- 같은 이름이 있으면 덮어쓰므로 여러 번 실행해도 중복이 생기지 않습니다.

## 파일 저장과 인증

첨부파일 본문은 `uploads/` 또는 `UPLOAD_DIR` 환경변수 경로에 저장하고 DB에는 원래 이름·저장 키·소유 인물을 기록합니다. PNG/JPG/PDF만 최대 5MB로 제한하고 파일 시그니처를 확인합니다. 다운로드는 로그인 및 족보 소유자 확인 후에만 가능합니다. 업로드 폴더를 공개 정적 경로로 노출하지 않습니다. DB와 첨부파일 디렉터리를 함께 백업해야 합니다.

비밀번호는 사용자별 salt와 scrypt로 해시하며, 세션은 임의 토큰의 해시와 만료 시각을 DB에 저장합니다. 쿠키는 HttpOnly, SameSite=Strict이고 24시간 만료입니다. HTTPS 배포 시 `COOKIE_SECURE=1`을 설정하세요.

초기 MVP에는 이메일 인증·비밀번호 재설정·로그인 시도 제한·다중 사용자 공동편집·백신 검사·음력 날짜·대규모 가계도 자동 배치가 없습니다. 인터넷 공개 운영 전에는 인증 강화, HTTPS, 요청 크기/속도 제한, 백업, 파일 검사 등을 구성해야 합니다. 본인 소유의 족보만 접근할 수 있습니다.

## 테스트

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

기본 테스트는 임시 SQLite DB를 사용합니다. `TEST_DATABASE_URL`을 **테스트용 PostgreSQL DB**로 지정하면 같은 API 시나리오를 PostgreSQL에서 실행합니다. 테스트 데이터가 삽입되므로 운영 DB를 지정하지 마세요. GitHub Actions는 PostgreSQL DDL·seed 두 번 실행·SQLite/PostgreSQL API 테스트를 수행합니다.

수동 확인: 회원가입 → 로그인 → 샘플 추가 → 인물 등록/수정/삭제 → 관계 등록 → 검색 → 가계도 → 족보책 → 인쇄/PDF. 업로드한 사진과 `jocbo.db`는 `.gitignore`로 제외됩니다. 다만 `db/seed_reference_page.py`에는 실존 인물의 이름과 생년월일이 들어 있으므로, 공개 저장소에 두는 것이 맞는지 확인하고 쓰세요.
