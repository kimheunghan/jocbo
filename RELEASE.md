# 배포 체크리스트

새 버전을 내보낼 때마다 이 순서를 그대로 따릅니다. 하나라도 빠뜨리면 고객이 구 버전을 받거나, 받은 파일에서 버전을 알 수 없게 됩니다.

## 1. 버전 번호 정하기

- 형식은 `2026.10.16`처럼 `연.월.차례`입니다. 직전 버전보다 큰 번호를 씁니다.
- 같은 번호로 Store 판과 MSIX 판을 함께 만듭니다.
  - `store-v<버전>`: 홈페이지에서 내려받는 설치 파일(exe)
  - `msix-v<버전>`: Microsoft Store 제출용 패키지(`jocbo.msix`)
- `v<버전>` 태그(운영자 계정과 실제 족보가 들어 있는 판)는 고객에게 내보내지 않습니다.

## 2. 태그 올리기

```
git tag store-v2026.10.16
git tag msix-v2026.10.16
git push origin store-v2026.10.16 msix-v2026.10.16
```

GitHub Actions가 설치 파일을 만들어 Releases에 올립니다(10분 남짓).

## 3. exe 파일 이름에 버전이 붙는지 확인 (꼭)

- 설치 프로그램의 버전(`AppVersion`)은 태그에서 자동으로 들어갑니다(`desktop/jocbo.iss`의 `JOCBO_VERSION`).
- 고객이 받는 파일 이름은 내려받기 주소(`share/functions/download/[tag]/[file].js`)가 태그를 읽어 `jocbo-setup_v26.10.16.exe`처럼 붙입니다.
- 배포 뒤 아래 명령으로 파일 이름을 확인합니다. `filename=`에 새 버전이 나와야 합니다.

```
curl -sI https://jocbo.pages.dev/download/store-v<버전>/jocbo-setup.exe | findstr /i disposition
```

## 4. 홈페이지 내려받기 주소 바꾸기 (꼭)

- `share/web/landing.html`의 `EXE_URL`을 새 Store 판 주소로 바꿉니다.
  ```
  const EXE_URL = 'https://jocbo.pages.dev/download/store-v<버전>/jocbo-setup.exe';
  ```
- `share/`에서 빌드하고 배포합니다.
  ```
  node build.mjs
  npx wrangler pages deploy dist --project-name jocbo
  ```
- 홈페이지의 "설치 파일 내려받기" 버튼을 직접 눌러, 받은 파일 이름이 `jocbo-setup_v<새 버전>.exe`인지 확인합니다.

## 5. Microsoft Store 제출

- Partner Center에 `msix-v<버전>` Releases의 `jocbo.msix`를 올립니다. 자세한 칸 값은 `store/README.md`를 따릅니다.
- 제출 전에 `store/README.md`의 "인증 기록"을 읽고 같은 사유로 떨어지지 않는지 확인합니다.
- 심사 결과(통과·불합격·사유)는 그 표에 적습니다.

## 6. 변경 기록 남기기 (꼭)

- `CHANGELOG.md` 맨 위에 새 버전, 날짜, 바뀐 점을 적고 커밋해 푸시합니다.
- Store의 "새로운 기능"에 넣은 문구도 같은 곳에 남깁니다.

## 7. 판매 페이지 문구 확인

- 라이선스 키 인식처럼 고객이 반드시 새 버전을 받아야 하는 수정이 들어가면, Lemon Squeezy 상품 설명과 이미지 띠의 버전 번호와 날짜를 함께 바꿉니다.
  - 설치 파일(exe): `v<버전> 이상`
  - MS Store: Store 화면의 `업데이트 날짜 <날짜> 또는 그 이후 판`(Store 화면에는 버전 번호가 나오지 않습니다)
