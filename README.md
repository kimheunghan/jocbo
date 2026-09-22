# 우리의 족보 — FastAPI 족보·가계도 MVP

한국어 화면에서 회원가입, 로그인, 족보 생성, 인물 관리, 가족 관계, 검색, 가계도, 족보책 미리보기와 인쇄/PDF 저장을 사용할 수 있습니다. 모든 예제는 가상 인물입니다.

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

1. 족보를 만들거나 선택합니다.
2. 인물 등록에서 한글명, 한자명, 세대, 성별, 출생·사망일, 생애 기록을 입력합니다.
3. 인물 카드를 누르면 수정·삭제와 파일 업로드를 할 수 있습니다. 삭제 시 관련 관계와 첨부파일도 삭제됩니다.
4. 기준 인물·관계·대상 인물을 선택하여 부모 → 자녀 또는 배우자 관계를 등록합니다. 본인과의 관계, 족보 간 연결, 중복 관계, 조상 순환을 차단합니다.
5. 한글명·한자명·메모를 검색하고 목록, 가계도, 족보책 보기로 전환합니다.
6. 가계도는 입력된 세대별로 배치하며 부모-자녀는 화살표, 배우자는 점선으로 표시합니다. 세대 번호는 자동 계산하지 않으므로 사용자가 맞춰 입력합니다.
7. **족보책 인쇄 / PDF**를 누르고 브라우저의 **PDF로 저장**을 선택합니다. 검색을 해제하고 선택한 족보 전체를 출력합니다. 전통 서책을 참고한 세대 구분·세로 한자명·생애 기록 형식이며 특정 문중의 편집 규격을 보증하지 않습니다.

## 구조

```text
backend/main.py        FastAPI API, 사용자 인증, 데이터 모델
frontend/              HTML / CSS / JavaScript
db/schema.sql          PostgreSQL DDL
db/seed.sql            가상 데이터
db/seed.py             선택적 seed 실행기
db/migrations/         번호순 SQL 변경 파일
uploads/               비공개 첨부파일 (Git 제외)
tests/test_api.py      API 통합 테스트
compose.yaml           PostgreSQL + 앱 실행
```

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

수동 확인: 회원가입 → 로그인 → 샘플 추가 → 인물 등록/수정/삭제 → 관계 등록 → 검색 → 가계도 → 족보책 → 인쇄/PDF. 실제 개인정보는 저장소에 커밋하지 마세요.
