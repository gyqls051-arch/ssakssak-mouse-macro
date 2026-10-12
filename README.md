# 싹싹김치 매크로 (SsakSsak Macro)

정해진 좌표에 자동으로 마우스 클릭을 보내는 가벼운 데스크톱 매크로.
**Windows + macOS** · 무료 · 싹싹김치 프리웨어 라이선스.

## 기능 — 3가지 모드

| 모드 | 설명 |
|---|---|
| **카운트다운** | N초 뒤에 클릭 (슬라이더로 간편 조절) |
| **예약 클릭** | 정해둔 날짜·시각에 정확히 한 번 클릭 (50ms 이내 정밀도) |
| **반복 클릭** | 일정 간격으로 계속 클릭 (간격·횟수 지정) |

- `F8` 현재 커서 위치 좌표 고정 · `F9` 시작 · `F10` 정지
- 클릭 종류 선택: 좌클릭 / 우클릭 / 더블클릭
- 매크로 실행 중 **절전 자동 방지** (Windows `SetThreadExecutionState` / macOS `caffeinate`)
- 로그 자동 저장: `%LOCALAPPDATA%\SsakSsakMacro\macro_log.txt` (macOS `~/Library/Logs/SsakSsakMacro/`)

## 설치 / 실행

### 배포본
`SsakSsakMacro.exe` (Windows) / `SsakSsakMacro.app` (macOS) — 파이썬 설치 불필요.

> ⚠️ 코드 서명이 없어 처음 실행 시 Windows SmartScreen / macOS Gatekeeper 경고가 뜰 수 있어요.
> Windows: "추가 정보 → 실행" / macOS: 시스템 설정에서 허용.

### 소스로 실행

```bash
pip install -r requirements.txt
python app.py
```

### 빌드

```powershell
.\build.bat        # Windows → dist/SsakSsakMacro.exe
./build_mac.sh     # macOS  → dist/SsakSsakMacro.app (ad-hoc 서명 포함)
```

macOS는 **손쉬운 사용 + 입력 모니터링** 권한을 허용해야 클릭/단축키가 동작합니다
(앱 첫 화면에 안내 표시됨).

## 사용 시 주의

자동 클릭 도구의 사용 책임은 사용자 본인에게 있습니다. 각 서비스의 이용약관·
관련 법규를 확인하고 사용하세요.

## 라이선스

싹싹김치 프리웨어 라이선스 — 무료 사용 가능, 유료 재판매·변조 배포·사칭 금지. [LICENSE](LICENSE)
