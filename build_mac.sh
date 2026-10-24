#!/bin/bash
# ====================================================================
#   SSAKSSAK MOUSE MACRO - macOS .app Builder
#   사용법: chmod +x build_mac.sh && ./build_mac.sh
# ====================================================================
set -e
cd "$(dirname "$0")"

echo "[1/3] PyInstaller 및 의존성 설치..."
python3 -m pip install --upgrade pip pyinstaller
python3 -m pip install -r requirements.txt

echo ""
echo "[2/3] 앱 컴파일... (Pretendard 폰트가 앱 안에 포함됩니다)"
# macOS에서는 --add-data 구분자가 ':' (Windows는 ';')
pyinstaller --noconfirm --onefile --windowed \
    --name "SsakSsakMacro" \
    --osx-bundle-identifier "com.ssakkimchi.macro" \
    --icon "assets/brand/app.icns" --add-data "assets/brand:assets/brand" --add-data "fonts:fonts" \
    app.py

echo ""
echo "[3/3] ad-hoc 코드 서명..."
# 서명이 없으면 macOS가 실행 시마다 다른 앱으로 인식해
# 손쉬운 사용/입력 모니터링 권한을 매번 다시 요구할 수 있다.
codesign --force --deep -s - "dist/SsakSsakMacro.app" || true

echo ""
echo "===================================================================="
echo "  빌드 완료: dist/SsakSsakMacro.app"
echo ""
echo "  첫 실행 시 필요한 권한 (시스템 설정 > 개인정보 보호 및 보안):"
echo "   - 손쉬운 사용(Accessibility): 마우스 클릭 제어"
echo "   - 입력 모니터링(Input Monitoring): F8/F9/F10 전역 단축키"
echo "  앱을 다시 빌드하면 권한을 다시 허용해야 할 수 있습니다."
echo "===================================================================="
