# 식품타 서버 앱

기존 식품타 UI에 개인 계정 로그인과 서버 데이터 저장을 연결한 웹 앱입니다.

## 가장 쉬운 실행 방법 (Mac)
1. ZIP을 풀고 `sikpumta_deployable_app` 폴더를 엽니다.
2. `start_mac.command` 파일을 더블 클릭합니다.
3. 처음 실행할 때는 Python 패키지 설치 때문에 시간이 걸릴 수 있습니다. Python 3와 인터넷 연결이 필요합니다.
4. 브라우저에서 `http://127.0.0.1:5000`이 열리면 회원가입 후 사용합니다.
5. 종료하려면 실행된 터미널 창에서 `Control + C`를 누릅니다.

스크립트가 열리지 않으면 터미널에서 폴더로 이동한 뒤 `bash start_mac.command`를 실행하세요.

## 실제 인터넷에 배포하는 방법 (Render)
1. GitHub에 새 저장소를 만듭니다.
2. 이 폴더 안의 파일 전체를 저장소 루트에 올립니다. `app.py`, `render.yaml`, `requirements.txt`가 최상위에 있어야 합니다.
3. https://dashboard.render.com/ 에서 **New + → Blueprint**를 선택하고 저장소를 연결합니다.
4. `render.yaml`의 웹 서비스와 영구 디스크 설정을 확인하고 배포합니다.
5. Render가 제공한 `https://...onrender.com` 주소를 엽니다.
6. `https://...onrender.com/healthz`가 `{"ok":true}`를 반환하는지 확인합니다.
7. 회원가입, 로그아웃, 재로그인 후 시험 기간과 공부 기록이 유지되는지 확인합니다.

배포는 본인의 GitHub/Render 계정 권한이 필요하므로 이 패키지만으로 공개 URL이 자동 생성되지는 않습니다. 공개 배포에서는 HTTPS, 자동 생성 `SECRET_KEY`, 영구 디스크 설정을 유지하세요. `DATABASE_PATH=/var/data/sikpumta.sqlite3`는 Render 영구 디스크에 저장됩니다.

## Docker로 실행
Docker Desktop 설치 후 프로젝트 폴더에서:
```bash
cp .env.example .env
# .env 안의 SECRET_KEY를 길고 임의적인 값으로 바꾸세요.
docker compose up --build
```
그다음 `http://127.0.0.1:5000`에 접속합니다. 종료는 `docker compose down`입니다. 데이터는 Docker 볼륨에 저장됩니다.

## 포함 기능
- 이메일 회원가입/로그인/로그아웃
- 비밀번호 해시 저장
- 사용자별 상태 데이터 저장/불러오기
- 공부 타이머, 카페인 기록, 일정, 시험 기간 등 프런트엔드 상태 동기화
- `/healthz` 헬스 체크
- Render 배포 설정, Dockerfile, Docker Compose, Mac 실행 스크립트

## 공개 배포 전 확인
- 외부 배포는 이 환경에서 사용자의 GitHub/Render 계정에 연결해 완료할 수 없습니다.
- 비밀번호 재설정, 이메일 인증, 요청 제한, 개인정보 처리방침, 백업 정책을 추가 검토하세요.
- 명예의 전당은 현재 기존 화면의 예시 점수입니다. 여러 사용자 간 실제 순위 집계는 별도 구현이 필요합니다.
- 브라우저의 기존 localStorage 데이터는 서버에 저장된 데이터가 없을 때 최초 로그인 시 가져오는 방식입니다.
