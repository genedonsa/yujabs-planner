# 유잡스 주간 기획 프로그램 (yt-planner)

유료 커뮤니티 회원이 자기 컴퓨터에서 돌리는 프로그램이다. 회원이 **내 채널 URL, 롤모델 채널 URL, 내 썸네일 템플릿**을 넣으면, 같은 버티컬 분야에서 최근 잘된 레퍼런스 영상을 찾아 **요약 카드형 기획안**을 만든다.

자세한 요구사항은 `SPEC.md`. 이 파일은 작업 원칙만 담는다.

## 꼭 지킬 원칙
- **운영비 0**: 서버 없음. 강사(커뮤니티 운영자) 명의의 API 키·유료 서비스 없음. 모든 처리는 회원 컴퓨터에서.
- **회원은 왕초보**: 구글 개발자 콘솔, API 키 발급, 터미널 명령을 요구하지 않는다. 설치 → 실행 → 칸 채우기 → 버튼 하나.
- **데이터 수집은 API 키 없이**: `yt-dlp`(파이썬 패키지)로 채널 영상 목록·조회수·설명란·자막·댓글을 가져온다. 유튜브 변경으로 깨질 수 있으니 수집 코드는 `planner/collect.py` 한 곳에 모으고, yt-dlp 버전을 올리기 쉽게 둔다.
- **회원 전용 암호 (대표가 매달 직접 바꿈)**: 대표의 구글 시트 '유잡스 기획 앱 — 이번 달 암호 확인용'(ID 1j6b4rW6bva9s5KMJ9fZceuME0oqxjp4HSpMtn1osjn8) A2 칸에 암호의 지문(SHA-256, `planner/access.py`의 SALT 포함)만 둔다. 앱은 실행할 때마다 그 칸을 읽어 비교한다. 대표가 칸을 바꾸면 옛 암호는 다음 실행부터 막힌다. 지문은 `tools/make_password.py 새암호`로 만든다. 암호 원문은 어디에도 저장하지 않는다.
- **기획안 규칙** (강사가 정한 것, `prompts/plan_prompt.md`에 반영됨)
  - 제목과 썸네일 문구는 레퍼런스 원본을 한국어로 옮긴다. 썸네일 스타일(글씨 위치·폰트·색·이미지 배치)만 회원 템플릿을 따른다.
  - 원본 분석은 '원본 대사(시간 포함, 원문 한 줄 + 번역) → 한 줄 요약 → 왜 먹혔나 → 내 채널에서는' 순서의 문장으로 쓴다. 화살표·줄임말 요약 금지.
  - 원문은 한 줄 이내로만 인용한다. 본인 주장 수치는 '본인 주장'으로 표시한다. 없는 경험을 지어내지 않고, 회원 경험이 들어갈 자리는 '내 경험 넣기' 칸으로 비워 둔다.

## 구조
```
app.py                 실행 진입점 (로컬 웹 화면을 띄우고 브라우저를 연다)
planner/collect.py     yt-dlp 수집 (채널 영상·검색·자막·댓글·썸네일)
planner/discover.py    내 채널·롤모델 제목에서 키워드를 뽑아 레퍼런스 후보 검색
planner/surge.py       채널 평균 대비 배수 계산, 후보 순위
planner/bundle.py      '분석 자료 묶음'(마크다운) + 기획안 요청문 생성
planner/thumbnail.py   회원 템플릿으로 '우리 썸네일 시안' 이미지 합성
planner/access.py      회원 암호 확인 (대표 시트의 지문과 비교)
desktop.py             데스크톱 앱 진입점 (pywebview 창 + ui/index.html)
ui/index.html          앱 화면 (ui/mock.js는 브라우저 미리보기 전용)
prompts/plan_prompt.md Claude에게 줄 기획안 작성 지시문 (요약 카드형)
tools/make_password.py 대표용: 새 암호의 지문 출력
tests/                 수집 없이 돌아가는 단위 테스트
```

## 작업 순서 (Claude Code에서)
1. `pip install -r requirements.txt` 후 `python -m pytest tests` 통과 확인 (수집 없이 도는 부분).
2. `planner/collect.py`를 실제 유튜브로 테스트: `python -m planner.collect --channel https://www.youtube.com/@유튜브-잡스` (이 함수들은 클라우드에서 유튜브 접속 없이 작성돼 아직 실제로 돌려 보지 않았다. 첫 실행에서 필드 이름·자막 형식을 확인하고 고칠 것.)
3. `python app.py`로 화면을 띄워 전체 흐름 확인.
4. PyInstaller로 맥 앱 빌드. 윈도우는 `.github/workflows`에 무료 GitHub Actions 빌드를 추가.

## 알려진 할 일 (v1 마무리 전)
- 썸네일 시안 배경: 지금은 원본 썸네일을 배경으로 써서 원본 글씨가 비친다. 원본 영상에서 글씨 없는 장면 한 컷을 뽑아 배경으로 쓰도록 바꿀 것(yt-dlp 스토리보드 이미지 또는 짧은 구간 다운로드 + ffmpeg).
- 폰트: `assets/BlackHanSans-Regular.ttf`는 자주 쓰는 한글 2,350자만 들어 있는 버전이다. 구글 폰트의 전체 TTF로 교체할 것(OFL, 배포 가능).
- 화면(app.py)은 기능 확인용 최소 화면이다. 왕초보 기준으로 다듬을 것(설정 저장 확인, 진행 표시, 폴더 열기 버튼).
- `planner/collect.py` 실제 유튜브 테스트, 검색 채널 수(최대 25)와 소요 시간 조정.
- PyInstaller 빌드(맥), GitHub Actions(윈도우), 회원용 설치 안내 문서.
