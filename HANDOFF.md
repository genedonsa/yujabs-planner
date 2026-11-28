# 콘봇 작업 현황 (2026-11-27 저녁 기준, 다음에 이어서 할 것)

## 저장소·올리는 방법
- 공개 저장소 genedonsa/yujabs-planner. 이 세션은 git/gh 권한이 없어서 **사용자 크롬으로 GitHub 웹 업로드**(…/upload/main/<폴더> 페이지에 file_upload → 커밋 버튼)로 올린다.
- 올릴 파일은 /mnt/user-data/outputs/up/ 에 폴더별로 복사해 두고 업로드 (planner/, root/, ui/, tests_e2e/, tests_video/, wf/=.github/workflows).
- 결과 확인: raw.githubusercontent.com/genedonsa/yujabs-planner/{e2e-results,video-results}/... (github.com·API는 이 환경에서 막힘, Actions 화면은 크롬으로 봄)

## 이번에 끝난 것 (모두 main에 올라감)
- 영상 만들기 기능: planner/video.py + desktop.py(pick_folder, video_styles, start_video, video_progress) + ui '영상 만들기' 화면 + 빌드에 faster-whisper/ctranslate2/imageio-ffmpeg 포함
  - CI video-test(맥에서 say로 한국어 음성 생성 → 맥·윈도우에서 진짜 받아쓰기 모델로 편집): **통과**. 29.4초→15.6초, "다시" NG·추임새·무음 삭제, 인사말·끝맺음 유지, -14.8 LUFS
  - 고친 것: PyAV 새 버전 오류(소리 직접 읽기), ffmpeg 9의 -filter_complex_script 삭제 대응(-/filter_complex, 옛 버전 fallback), 받아쓰기가 쉼을 낱말에 붙이는 문제(silencedetect로 무음 직접 찾기), "다시" 판단을 '다시 말한 첫 낱말이 앞에 나왔는지'로, 자막 조사·단위 붙이기('방법 을'→'방법을')
- 배포 앱 selftest(v0.2.53, 맥·윈도우): 암호 시트·유튜브 채널 읽기·ffmpeg·받아쓰기 엔진 모두 정상
- **보안**: 공개 저장소 desktop.py selftest에 이번 달 암호 원문이 있었음 → 제거(sheet_ok로 대체). 깃 기록엔 남아 있으니 대표가 암호를 바꾸는 게 안전
- **검색 고장 수정**: yt-dlp에서 ytsearchdate가 없어져 키워드 검색이 전부 실패하고 있었음 → 유튜브 검색 주소 + 업로드 날짜 필터(sp)로 교체 (collect.search_url)
- 실사용 점검(e2e-real): 브라우저 경로 문제 수정, 분석 기록(analyze.log)·검색 확인(probe.txt) 남김. 페르소나 기본값을 한국 요리 채널(롤모델: 엄마의손맛·양장금주부·심방골주부·오늘식탁, 내 채널 @Tooktak)로 변경 (PERSONA=yt 이면 유튜브 교육)
- 키워드 품질: 여러 채널 공통 낱말 우선(shared_keywords), 분야 대표 말(anchor_word)을 검색어 앞에 붙임, 벤치마킹은 같은 분야 제목 2개 이상 + 구독자·평소 조회수 1천 이상만, 검색으로만 찾은 채널은 검색된 영상만 레퍼런스로
- 기획 자료: 유튜브가 영상 페이지를 막아도 아는 정보로 자료를 만들고 화면에 안내
- 릴리스: 세 빌드(맥 Apple·맥 Intel·윈도우)가 모두 성공해야 올라가게 변경 (깃허브 맥 러너 부족으로 v0.2.52에 Apple 맥 파일이 빠졌던 문제)

## 진행 중이던 것 (다음에 바로 확인)
1. 마지막 업로드: collect.py(한국 채널이 영어 번역 제목으로 오는 문제 → 한국어로 한 번 더 물어 원래 제목으로 교체), engine.py(너무 작은 채널 제외). 이 빌드 → e2e-real 결과를 확인할 것
   - 확인할 점: analyze.log의 '키워드:' 줄이 한국어(김치·반찬·레시피 등)로 나오는지, 벤치마킹 채널이 한국 요리 채널인지, 레퍼런스가 요리 영상인지
2. video-test 최신 결과에서 자막 띄어쓰기(방법을/꾸준함입니다/52편이) 확인
3. 최신 릴리스에 CornBot-macOS.zip·macOS-Intel·windows 3개가 다 있는지 확인

## 남은 일
- 영상: 내 스타일 등록, 간단 편집기(자막 고치기), 그래픽·효과음(yujabs-video-edit 스킬 로직)
- 테스트 서버에서 유튜브가 영상 페이지(자막·댓글·내 영상 대본)를 봇 확인으로 막음 → 회원 집 컴퓨터에선 대부분 됨. 실제 맥북에서 한 번 확인 필요
- 설치 가이드 문서(구글 문서 17IaFkiv4brG_h8XGNmqr9pZaebOSVS5lUuwfVHNrCEU)에 '영상 만들기' 기능 한 줄 추가 (문서는 지우지 말고 그 자리에서 고치기)
- 사용자에게 아직 못 받은 결정: 내부 롤모델 시트 활용 방식, 편집 스타일 중앙 관리+복사 방식, 8가지 아이디어 중 넣을 것
- 사용자 지시: "문제없으면 그때 알려줘" — 위 1~3 확인 뒤 정리해서 보고

## 2026-11-27 밤 추가 작업 (맥미니·크롬 못 쓰는 동안, **아직 저장소에 안 올림**)
올릴 파일 전부: /mnt/user-data/outputs/up_next/ (저장소 경로 그대로). 올릴 때 폴더별로 GitHub 웹 업로드. **워크플로(build.yml, video-test.yml)는 마지막에** 올릴 것.
- 화면 전수 점검(점검 서버: scratchpad/audit/server.py + audit.mjs, audit2.mjs — 실제 Api, 가짜 유튜브·받아쓰기·시험용 암호 test-pass-1): 1차 39개·2차 14개 항목 모두 통과
  - 고친 것: 업데이트 팝업이 로그인 뒤 다시 뜸 / 분석 실패 시 제목·빙글이가 '분석 중'으로 남음 / '설정 고치기'→'입력 고치기'(바로 입력 화면) / 틀린 롤모델 주소를 말없이 건너뜀(→ 안내, 전부 틀리면 바로 오류) / 벤치마킹 숫자 표기 / 채널 키워드에 검색어 대신 키워드 / 이미지 못 불러오면 회색 칸 / 영어 오류 문구 → 쉬운 말 / 편집 창이 다른 화면에 남던 문제
- 영상 자막·장면 고치기(새 기능): video.items/place/drop_ranges/load_edit/rerender, Api video_edit_load·video_rerender, 화면 '자막·장면 고치기'
- 업데이트 안전장치: settings 저장을 임시 파일→바꿔치기, 직전 저장본 settings.bak.json 자동 복구, 형식 번호 _schema + migrate(), 암호 원문 대신 password_fp(옛 설정 자동 변환)
- 회귀 방지 테스트: tests/test_ui_contract.py(화면이 부르는 기능·칸·파일이 실제로 있는지), 설정 깨짐·옛 형식 테스트 (총 15개 통과)
- **배포 검문소**: build는 '시험판'(prerelease)으로만 올림 → video-test가 맥 Apple·맥 Intel·윈도우에서 그 시험판 앱을 받아 자체 점검 + 실제 받아쓰기 영상 편집 → 모두 통과해야 promote 잡이 '최신 버전'으로 바꿈. 실패하면 회원은 이전 버전 그대로. (tests/video/gate.py가 판정)
- 설치 가이드 v0.6 초안: docs/install_guide_v0.6.md (새 컴퓨터 기준 준비물·계정·조건, 기능 목록 최신화, 운영자용 칸(암호) 삭제). 구글 문서에는 아직 반영 안 함 — 크롬 연결되면 문서 그 자리에 반영
- 키워드 불용어 보강(맛있·됩니다·담그 등), 한국어 원래 제목 받기, 작은 채널(구독자·평소 조회 1천 미만) 벤치마킹 제외

## 다음에 할 것 (순서대로)
1. GitHub에 up_next 업로드 → build(시험판) → video-test 검문 → promote 확인. e2e-real(요리 페르소나) 키워드가 한국어 명사로 나오는지 확인
2. 구글 문서에 가이드 v0.6 반영 (문서 지우지 말 것)
3. 새 컴퓨터 테스트: CI의 깨끗한 맥·윈도우에서 한 줄 설치 → selftest (env-test.yml이 하고 있음, 시험판 태그로도 돌게 바꾸면 좋음)
4. Claude·ChatGPT 무료로 가이드 따라 하기 테스트 (브라우저 필요)
5. 실제 맥(맥미니/맥북)에서 영상 페이지(자막·댓글) 읽힘 확인 — 사용자가 터미널 한 줄 + 암호 입력 필요

## 2026-11-28 맥미니 작업
- up_next 전부 업로드 완료, 설치 가이드 v0.6 구글 문서에 그 자리 반영(복사 없이 raw.githubusercontent에서 받아 붙여넣기 — 손으로 옮기면 글자 깨짐 주의)
- 맥미니 실사용에서 발견: **긴 영상(자를 곳 수백 개) ffmpeg 메모리 부족** → _render를 40구간씩 조각→이어붙이기→자막·음량 방식으로 변경, 6분/116구간 검증 OK. 오류 전체는 ~/유잡스 기획/영상오류.txt
- build는 paths-ignore docs/**, video-test 음성 만들기는 macos-15-intel(Apple 러너 대기열 문제로 #28 실패 — 검문소가 막아서 회원에겐 안 나감)
- e2e 요리 페르소나: 벤치마킹·레퍼런스 모두 한국 요리 채널로 정상. 분야 말 '쉽고' 같은 형용사 제외, 평소 조회 1천 미만 채널은 레퍼런스 제외 (업로드함)
- 맥미니 콘봇 v0.2.60 설치·암호 완료(사용자), 접근 권한 CornBot 받음. 폴더 접근 요청은 거절됨
- **Claude 연결 결정 대기**: 사용자 "회원 각자 Claude 구독". 규정상 콘봇이 회원의 Claude 로그인을 대신 쓰는 건 금지(code.claude.com/docs/en/legal-and-compliance). 허용되는 방식 = Claude 데스크톱 앱 + MCP(콘봇이 도구로 연결). 예시 화면 캔버스: https://claude.ai/artifact/TJFBGruJ5mdFhDiRbKR6Hs . 무료/Pro에서 데스크톱 확장 되는지 실제 확인 필요
- **할 일 추가(사용자 승인)**: ① 저장소 비공개 전환 + 설치 파일만 공개 저장소(릴리스 전용)로 — 비공개 저장소에서 공개 저장소로 올리려면 사용자가 GitHub 토큰을 만들어 Secrets에 넣어야 함(내가 대신 못 함) ② 기획 지시문(prompts/plan_prompt.md) 보호 — 공개 저장소에 그대로 보임. 앱 안 평문 대신 암호화해서 넣고 암호 확인 뒤에만 풀기

## 2026-11-28 오후: Claude 앱 연결(MCP) 전환 + 학원월드 주간 게시글 흐름
- **MCP 서버** planner/mcp_server.py (표준 라이브러리만, `CornBot --mcp`). 도구 19개: cornbot_status, open_cornbot_window, update_profile, start_analysis/analysis_status, list_references(R1…), list_benchmark_channels, change_keywords, add_benchmark_channel, import_weekly_post(비우면 클립보드 HTML 직접 읽음)/list_weekly_videos(W1…), get_planning_material, save_plan, list_plans, find_folders, make_video/video_status, get_video_lines, edit_video(drop/fix/emphasis/chapters, 끝나면 chapters_at=설명란 챕터 시간)
  - initialize의 instructions에 기획 흐름(내 이야기 묻기 → 자료 → 지시문대로 → save_plan)과 유잡스 편집 규칙(오타·강조 1분당 1개·챕터 2~6개·설명란) 포함
  - 암호: 상태 도구 외엔 check_saved(10분 캐시). 안 맞으면 콘봇 창을 열라고 안내(암호를 대화창에 받지 않음)
  - 윈도우 창 모드 빌드는 GetStdHandle로 표준입출력 직접 열기. 도구 print는 stderr로
- **Claude 앱 자동 등록** planner/claude_link.py: 앱(설치본)을 켤 때마다 claude_desktop_config.json의 mcpServers.cornbot = {command: 앱 실행파일, args:["--mcp"]}. 다른 항목 유지, .cornbot-bak 백업, 임시파일→바꿔치기, 깨진 파일은 안 건드림. 윈도우 스토어판 경로도. 설정 화면 'Claude 앱 연결'에서 상태·다시 연결
- 업데이트(윈도우): 바꿔 끼우기 전에 --mcp 프로세스를 taskkill (파일 잠김 방지), robocopy /R:5 /W:2
- **주간 게시글**: planner/weekly.py(parse: 링크 앞 '2. 채널 — 평소의 3.4배' 머리줄을 그 영상 몫으로, enrich=collect.video_info, weekly.json), planner/clip.py(맥 NSPasteboard public.html / 윈도우 'HTML Format'), 화면 '주간 게시글'(복사한 게시글 가져오기 버튼 + 붙여넣기 칸) → 카드 → 기획하기. engine.plan_material에 '학원월드 주간 게시글 분석' 절, 배수·업로드일 없을 때 '(모름)'
- 영상: 편집 창 줄마다 '꾸미기'(위쪽 강조 문구·챕터 이름) — rerender가 emph/chapter 유지
- selftest에 mcp(실제 앱을 --mcp로 띄워 인사·도구 목록·상태) → gate.py가 mcp 'ok' 아니면 막음
- 테스트 23개(tests/test_mcp.py 추가). e2e-real 재구성: clip 잡 → (맥 self, 윈도우 self, 맥 cook) 화면 전체(주간 게시글·영상·꾸미기 포함) + tests/e2e/mcp_flow.py(Claude가 부르는 순서대로 기획→편집, 실제 유튜브·받아쓰기). self = 내 채널(@유튜브-잡스)을 롤모델에도. 결과 e2e-results/<tag>/
- 가이드 v0.7 초안 docs/install_guide_v0.7.md(.html): 준비물에 Claude 데스크톱 앱·구독(Pro 권장), '3. Claude 앱과 연결하기', 말 예시, 문제 해결
- 확인 필요: 무료 요금제에서 로컬 MCP 되는지, 맥에서 Claude가 띄운 콘봇의 '데스크탑' 폴더 접근 팝업(Claude 이름으로 뜸)

### 2026-11-28 실사용 점검 결과 (사용자 요청: 롤모델에도 내 채널 넣고 기획→영상까지)
- CI e2e-real(맥 Intel·윈도우 = self, 맥 = 요리): 화면 전체 흐름 + Claude 도구(MCP) 흐름 모두 통과. MCP 흐름: 상태→프로필→분석→레퍼런스→주간 게시글(실제 영상)→기획 자료(지시문·게시글 분석·내 이야기·자막·댓글 포함)→기획안 저장→폴더 찾기→영상 만들기(실제 받아쓰기)→자막 줄→오타·강조·챕터·빼기→다시 만들기→챕터 시간
- 배포 앱(v0.2.84) selftest: 맥 Apple·Intel·윈도우 모두 mcp ok (tools=19) → 최신 버전으로 승격됨
- 맥미니: v0.2.84로 앱 안 업데이트(암호 유지), 설정 'Claude 앱 연결' = 연결됨(자동 등록 확인). 예전에 메모리 부족으로 실패한 실제 20분 촬영본(컷편테스트) → 10분 40초, 자막 380줄로 성공(약 8분)
- 발견·수정: ① 롤모델=내 채널일 때 '나보다 작은 채널'만 찾아 벤치마킹 0곳(@유튜브-잡스 구독자 88명) → 내 채널이면 최소 구독자 10만까지 ② 키워드가 '대충·어떤·모은' 같은 말 → 활용형·부사 제외 ③ 유튜브 교육 분야면 조회수·구독자·수익화를 키워드로, 유튜브 얘기 없는 검색 영상(퇴직·여행)은 레퍼런스에서 제외 ④ 자막 '드릴께요'→'드릴게요' ⑤ 벤치마킹 0곳이면 빠진 이유를 화면에 ⑥ video-test 인사말 판정이 받아쓰기 변형(안녕하세여)에 실패하던 것
- 깃허브 Apple 맥 러너가 자주 안 잡힘(build #82·#83 실패) → 실패한 잡만 다시 실행하면 됨. 검문소 덕에 회원에게는 안 나감
- 구글 문서 설치 가이드는 아직 v0.6 (Docs 편집 커넥터 없음 + Claude 앱 연결을 대표가 실제로 확인한 뒤 v0.7 반영 권장). v0.7 초안: docs/install_guide_v0.7.md

## 2026-11-28 밤: 급상승 영상 공용화 · 기준 고정 · 분석 오류 수정 (main 반영)
- 주간 게시글 화면 삭제 → 레퍼런스 맨 위 '급상승 영상'. 원본은 대표 시트(1j6b4r…) '급상승' 탭(gid 777), 열: id|url|title|channel|views|ratio|note|post_date|post_title. 모든 회원이 같은 목록. 오프라인이면 weekly.json 캐시.
- MCP `import_weekly_post` 삭제(도구 18개). Claude는 list_weekly_videos → get_planning_material(W#)로 기획.
- 찾는 기준 7일·1만·3배 고정(DEFAULT_CRITERIA), 설정에서 못 바꿈.
- 'Error -3 decompress' → collect.YoutubeDL가 Accept-Encoding: identity로 다시 시도. v0.2.94에서 edward 분석 정상(벤치 8곳 전부 구독).
- 롤모델=내 채널이면 벤치 상한 max(구독×5, 10만). 유튜브 교육 분야는 키워드·레퍼런스에 유튜브 관련어 필수.
- e2e: drive.mjs·mcp_flow.py가 공용 목록 기준으로 점검(붙여넣기 단계 없음).
- 가이드 구글 문서 v0.7 최종 문구로 덮어씀(같은 문서).
- **남은 것**: 학원월드 새 주간 게시글 → 시트 '급상승' 탭 자동 반영(예약 작업 만들기가 막혀서 사용자 승인 필요. 지금은 '11월 5주차 급상승 영상 16선' 들어 있음). 안 쓰는 planner/clip.py 저장소에서 지우기. 비공개 저장소 전환(토큰 필요).
