"""
싹싹김치 매크로 (SsakSsak Macro)
Native PySide6 Desktop Application — Windows / macOS

UI: 싹싹김치 디자인 시스템 (라이트 카드-온-그레이, 플랫, Pretendard, 김치 주황 #E85D2C).

macOS 참고: pynput 전역 단축키/마우스 제어는 시스템 설정 > 개인정보 보호 및 보안에서
'손쉬운 사용'과 '입력 모니터링' 권한을 앱(또는 터미널/Python)에 허용해야 동작한다.
"""
import sys
import os
import time
import logging
import threading
import subprocess
import webbrowser
from logging.handlers import RotatingFileHandler
from datetime import datetime

IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"

if IS_WINDOWS:
    import ctypes

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSpinBox, QComboBox, QTabWidget,
    QRadioButton, QCheckBox, QTextEdit, QDateTimeEdit,
    QFrame, QSlider, QScrollArea, QSizePolicy, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QDateTime, QSize, QRectF, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QColor, QPalette, QPainter, QPen, QDesktopServices

from pynput import keyboard
from pynput.mouse import Button, Controller as MouseController


# ─── SsakSsak Design System — tokens ───
ACCENT          = "#e85d2c"   # 김치 주황 (primary)
ACCENT_HOVER    = "#d9521f"
ACCENT_PRESSED  = "#c2481b"
ACCENT_SOFT     = "#fdeee5"
BG              = "#f4f5f7"    # 페이지 배경
BG_2            = "#fafbfc"    # inset surfaces
CARD            = "#ffffff"
BORDER          = "#e5e7eb"
BORDER_STRONG   = "#d1d5db"
TEXT            = "#111827"
TEXT_2          = "#1f2328"
MUTED           = "#6b7280"
SUBTLE          = "#9ca3af"
SUCCESS         = "#059669"
SUCCESS_SOFT    = "#ecfdf5"
DANGER          = "#dc2626"
DANGER_SOFT     = "#fef2f2"
WARNING         = "#d97706"
INFO            = "#2f6feb"
INFO_SOFT       = "#eff6ff"
DISABLED_BG     = "#d6dbe4"

# ─── 버전 / 자동 업데이트 ───
# 배포 시 APP_VERSION 과 릴리스 태그를 맞출 것 (CI 가 tag==APP_VERSION 검증).
APP_VERSION = "1.0.1"
# 이 앱의 공개 저장소 루트에 둔 version.json. CI 가 태그 릴리스 때 자동 갱신한다.
VERSION_INFO_URL = "https://raw.githubusercontent.com/gyqls051-arch/ssakssak-mouse-macro/main/version.json"

from ssak_update import check_for_update
from ssak_installer import Client as UpdateClient, Config as UpdateConfig

# 플랫폼별 폴백 폰트 (Pretendard 번들 로드 실패 시)
if IS_MACOS:
    FALLBACK_SANS = "Apple SD Gothic Neo"
    MONO_FAMILY = "Menlo"
else:
    FALLBACK_SANS = "Malgun Gothic"
    MONO_FAMILY = "Consolas"

FONT_SANS = f"'Pretendard', '{FALLBACK_SANS}', 'Segoe UI', sans-serif"
FONT_MONO = f"'{MONO_FAMILY}', 'D2Coding', monospace"


# ─── Safety limits (폭주 클릭 방지) ───
# 반복 클릭 간격의 합리적 하한. 1ms는 사실상 시스템을 마비시킬 수 있어 막는다.
MIN_INTERVAL_MS = 10
# 무한 반복 모드에서도 적용되는 안전 상한. 둘 중 하나라도 도달하면 자동 정지한다.
MAX_RUNTIME_SECONDS = 60 * 60        # 최대 실행 시간 (1시간)
MAX_TOTAL_CLICKS = 1_000_000         # 최대 총 클릭 횟수


# ─── Sleep Prevention (Windows: SetThreadExecutionState / macOS: caffeinate) ───
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

# macOS: caffeinate 자식 프로세스가 살아있는 동안 절전이 막힌다.
_caffeinate_proc = None

def prevent_sleep():
    """OS가 절전 모드로 들어가지 않도록 방지"""
    global _caffeinate_proc
    if IS_WINDOWS:
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
        )
    elif IS_MACOS:
        if _caffeinate_proc is None or _caffeinate_proc.poll() is not None:
            # -d 디스플레이, -i 유휴, -m 디스크, -s 시스템(AC 전원) 절전 방지
            _caffeinate_proc = subprocess.Popen(["/usr/bin/caffeinate", "-dims"])

def allow_sleep():
    """절전 방지 해제"""
    global _caffeinate_proc
    if IS_WINDOWS:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    elif IS_MACOS:
        if _caffeinate_proc is not None:
            _caffeinate_proc.terminate()
            _caffeinate_proc = None


# ─── Resource / Font loading ───
def resource_path(rel):
    """소스 실행 / PyInstaller onefile(_MEIPASS) 양쪽에서 동작하는 경로."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

def load_app_fonts():
    """번들된 Pretendard TTF를 등록한다. 하나라도 등록되면 True."""
    loaded = False
    for weight in ("Regular", "Medium", "SemiBold", "Bold", "Black"):
        path = resource_path(os.path.join("fonts", f"Pretendard-{weight}.ttf"))
        if os.path.exists(path):
            if QFontDatabase.addApplicationFont(path) != -1:
                loaded = True
    return loaded


# ─── File Logging ───
def _log_dir():
    """사용자별 앱데이터 폴더를 우선 사용.
    Windows: %LOCALAPPDATA%\\SsakSsakMacro / macOS: ~/Library/Logs/SsakSsakMacro.
    실패하면 EXE/스크립트 옆으로 폴백한다."""
    if IS_MACOS:
        d = os.path.expanduser('~/Library/Logs/SsakSsakMacro')
    else:
        base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA')
        if base:
            d = os.path.join(base, 'SsakSsakMacro')
        else:
            d = os.path.dirname(os.path.abspath(sys.argv[0]))
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = os.path.dirname(os.path.abspath(sys.argv[0]))
    return d


def setup_logging():
    log_dir = _log_dir()
    log_path = os.path.join(log_dir, 'macro_log.txt')
    handler = RotatingFileHandler(
        log_path, maxBytes=512 * 1024, backupCount=3, encoding='utf-8'
    )
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
    ))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # 중복 핸들러 방지 (재호출 대비)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    logging.info('=== 싹싹김치 매크로 시작 ===')
    return log_path


# ─── Signal Bridge (thread-safe UI updates) ───
class SignalBridge(QObject):
    log_signal = Signal(str, str)          # message, type
    status_signal = Signal(str)            # status text
    coord_locked_signal = Signal(int, int) # x, y
    countdown_tick = Signal(float, float)  # remaining, total
    click_done_signal = Signal(str)        # info
    interval_count_signal = Signal(int, int)  # done, max
    reset_ring_signal = Signal()           # ask GUI thread to clear the ring
    release_sleep_signal = Signal()        # ask GUI thread to release sleep prevention
    update_signal = Signal(dict)           # ssak_update 결과 → GUI 스레드로 marshal


# ─── Pill Toggle (keeps the QCheckBox API: isChecked / setChecked / toggled) ───
class ToggleSwitch(QCheckBox):
    _TRACK_W = 38
    _TRACK_H = 22
    _GAP = 10

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self):
        fm = self.fontMetrics()
        tw = fm.horizontalAdvance(self.text())
        return QSize(self._TRACK_W + self._GAP + tw + 6,
                     max(self._TRACK_H + 6, fm.height() + 6))

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        th = self._TRACK_H
        ty = (self.height() - th) / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(ACCENT) if on else QColor(BORDER_STRONG))
        p.drawRoundedRect(QRectF(0, ty, self._TRACK_W, th), th / 2, th / 2)
        d = th - 6
        kx = (self._TRACK_W - d - 3) if on else 3
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(kx, ty + 3, d, d))
        if self.text():
            p.setPen(QColor(TEXT) if on else QColor(MUTED))
            p.setFont(self.font())
            tx = self._TRACK_W + self._GAP
            p.drawText(QRectF(tx, 0, self.width() - tx, self.height()),
                       Qt.AlignVCenter | Qt.AlignLeft | Qt.TextWordWrap, self.text())
        p.end()


# ─── Circular Countdown Widget ───
class CountdownRing(QWidget):
    def __init__(self):
        super().__init__()
        self.progress = 0.0
        self.remaining_text = "00:00.0"
        self.setFixedSize(148, 148)

    def set_progress(self, p, text):
        self.progress = max(0.0, min(1.0, p))
        self.remaining_text = text
        self.repaint()

    def reset(self):
        self.progress = 0.0
        self.remaining_text = "00:00.0"
        self.repaint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2
        radius = min(w, h) // 2 - 10

        # Background ring
        pen = QPen(QColor(BORDER), 8)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(cx - radius, cy - radius, radius * 2, radius * 2, 0, 360 * 16)

        # Progress ring (fresh green, sweeps clockwise from 12 o'clock)
        if self.progress > 0:
            pen2 = QPen(QColor(ACCENT), 8)
            pen2.setCapStyle(Qt.RoundCap)
            painter.setPen(pen2)
            span = int(self.progress * 360 * 16)
            painter.drawArc(cx - radius, cy - radius, radius * 2, radius * 2, 90 * 16, -span)

        # Center text
        painter.setPen(QColor(TEXT))
        font = QFont(MONO_FAMILY, 13, QFont.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self.remaining_text)
        painter.end()


# ─── Main Window ───
class MacroWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("싹싹김치 매크로")
        self.setMinimumSize(540, 640)
        self.resize(600, 900)

        self.mouse = MouseController()
        self.bridge = SignalBridge()
        self.macro_stop = threading.Event()
        self.macro_thread = None
        self.locked_coords = None  # (x, y)
        self._sleep_prevented = False
        self._sync_lock = False

        self._setup_style()
        self._build_ui()
        self._connect_signals()
        self._start_hotkey_listener()
        self._start_live_cursor_timer()
        logging.info('GUI 초기화 완료')

    # ─── SsakSsak light theme ───
    def _setup_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {BG}; }}
            QScrollArea#scroll {{ border: none; background: {BG}; }}
            QWidget#page {{ background: {BG}; }}
            QWidget {{ color: {TEXT}; font-family: {FONT_SANS}; font-size: 13px; }}

            /* ===== Cards ===== */
            QFrame#card {{
                background: {CARD};
                border: 1px solid {BORDER};
                border-radius: 16px;
            }}
            QFrame#brand {{ background: #0f0f0f; border-radius: 16px; }}

            QLabel#cardTitle {{ font-size: 15px; font-weight: 600; color: {TEXT}; }}
            QLabel#hint      {{ font-size: 12px; color: {MUTED}; }}
            QLabel#fieldLabel{{ font-size: 13px; font-weight: 600; color: {TEXT}; }}
            QLabel#paneDesc  {{ font-size: 13px; color: {MUTED}; }}

            /* ===== Coordinate boxes ===== */
            QFrame#coordBox  {{ background: {BG_2}; border: 1px solid {BORDER}; border-radius: 12px; }}
            QLabel#coordLabel{{ font-size: 12px; font-weight: 600; color: {MUTED}; }}
            QLabel#coordVal  {{ font-family: {FONT_MONO}; font-size: 18px; font-weight: 700; color: {TEXT}; }}

            /* ===== Tabs (segmented control) ===== */
            QTabWidget::pane {{ border: none; background: transparent; top: 6px; }}
            QTabBar {{
                background: {BG};
                border: 1px solid {BORDER};
                border-radius: 10px;
                padding: 4px;
            }}
            QTabBar::tab {{
                background: transparent;
                color: {MUTED};
                font-size: 13px;
                font-weight: 600;
                padding: 8px 18px;
                border: 1px solid transparent;
                border-radius: 8px;
                margin: 0 2px;
            }}
            QTabBar::tab:hover {{ color: {TEXT}; }}
            QTabBar::tab:selected {{
                background: {CARD};
                color: {TEXT};
                border: 1px solid {BORDER};
            }}

            /* ===== Inputs ===== */
            QSpinBox, QDateTimeEdit {{
                background: {CARD};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 8px 10px;
                color: {TEXT};
                font-family: {FONT_MONO};
                font-size: 14px;
                font-weight: 600;
                selection-background-color: {ACCENT};
                selection-color: #ffffff;
            }}
            QComboBox {{
                background: {CARD};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 8px 12px;
                color: {TEXT};
                font-family: {FONT_SANS};
                font-size: 14px;
                font-weight: 600;
            }}
            QSpinBox:focus, QComboBox:focus, QDateTimeEdit:focus {{ border: 1px solid {ACCENT}; }}
            QSpinBox:disabled {{ background: {BG}; color: {SUBTLE}; }}
            QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; border: none; background: transparent; }}
            QComboBox::drop-down {{ border: none; width: 22px; }}
            QComboBox QAbstractItemView {{
                background: {CARD};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 8px;
                outline: none;
                selection-background-color: {ACCENT_SOFT};
                selection-color: {TEXT};
            }}
            QDateTimeEdit::drop-down {{ border: none; width: 22px; }}

            /* ===== Slider ===== */
            QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
            QSlider::handle:horizontal {{
                width: 16px; height: 16px; margin: -7px 0;
                border-radius: 9px; background: {ACCENT}; border: 2px solid #ffffff;
            }}

            /* ===== Radios ===== */
            QRadioButton {{ spacing: 6px; color: {MUTED}; font-size: 13px; }}
            QRadioButton:checked {{ color: {TEXT}; }}
            QRadioButton::indicator {{ width: 15px; height: 15px; }}

            /* ===== Buttons ===== */
            QPushButton {{
                border-radius: 999px;
                padding: 13px 18px;
                font-weight: 600;
                font-size: 15px;
            }}
            QPushButton#startBtn {{ background: {ACCENT}; color: #ffffff; border: 1px solid transparent; }}
            QPushButton#startBtn:hover {{ background: {ACCENT_HOVER}; }}
            QPushButton#startBtn:pressed {{ background: {ACCENT_PRESSED}; }}
            QPushButton#startBtn:disabled {{ background: {DISABLED_BG}; color: #ffffff; }}
            QPushButton#stopBtn {{ background: {CARD}; border: 1px solid {BORDER}; color: {DANGER}; }}
            QPushButton#stopBtn:hover {{ background: {DANGER_SOFT}; border: 1px solid {DANGER}; }}
            QPushButton#stopBtn:disabled {{ color: {SUBTLE}; }}

            /* ===== Console / log ===== */
            QTextEdit#logBox {{
                background: {BG_2};
                border: 1px solid {BORDER};
                border-radius: 12px;
                font-family: {FONT_MONO};
                font-size: 12px;
                color: {TEXT_2};
                padding: 8px 10px;
            }}
            QPushButton#clearBtn {{
                background: transparent; border: none; padding: 2px 4px;
                color: {MUTED}; font-size: 12px; font-weight: 500;
            }}
            QPushButton#clearBtn:hover {{ color: {TEXT}; }}

            /* ===== Hotkey guide ===== */
            QLabel#kbd {{
                background: {BG};
                border: 1px solid {BORDER_STRONG};
                border-radius: 8px;
                padding: 3px 8px;
                font-family: {FONT_MONO};
                font-size: 12px;
                font-weight: 600;
                color: {TEXT};
            }}
            QLabel#keyDesc {{ color: {TEXT_2}; font-size: 13px; }}
            QLabel#clockBox {{
                background: {ACCENT_SOFT};
                border-radius: 12px;
                padding: 11px 14px;
                color: {TEXT};
                font-size: 13px;
            }}

            /* ===== Scrollbars ===== */
            QScrollBar:vertical {{ width: 8px; background: transparent; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; border-radius: 4px; min-height: 28px; }}
            QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)

    # ─── Card helpers ───
    def _card(self):
        frame = QFrame()
        frame.setObjectName("card")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)
        return frame, lay

    def _card_header(self, title, hint=None):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        t = QLabel(title)
        t.setObjectName("cardTitle")
        row.addWidget(t)
        if hint:
            row.addStretch()
            h = QLabel(hint)
            h.setObjectName("hint")
            row.addWidget(h)
        return row

    @staticmethod
    def _fmt_coord(x, y):
        em = f'<span style="color:{SUBTLE};font-weight:500;">'
        return (f'{em}X</span> {x}&nbsp;&nbsp;&nbsp;&nbsp;'
                f'{em}Y</span> {y}')

    # ─── Build UI ───
    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setObjectName("scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setCentralWidget(scroll)

        page = QWidget()
        page.setObjectName("page")
        scroll.setWidget(page)

        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 20, 18, 28)

        # ===== Brand header (the one loud surface) =====
        brand = QFrame()
        brand.setObjectName("brand")
        bl = QVBoxLayout(brand)
        bl.setContentsMargins(24, 22, 24, 18)
        bl.setSpacing(12)

        mark = QLabel(f'<span style="color:#f4f5f7;">싹싹</span>'
                      f'<span style="color:{ACCENT};">김치</span>')
        mark_font = QFont()
        mark_font.setFamily("Pretendard")
        mark_font.setPointSize(28)
        mark_font.setWeight(QFont.Black)
        mark_font.setItalic(True)
        mark_font.setLetterSpacing(QFont.AbsoluteSpacing, 1)
        mark.setFont(mark_font)
        mark.setAlignment(Qt.AlignCenter)
        bl.addWidget(mark)

        sub_row = QHBoxLayout()
        sub_row.setContentsMargins(0, 0, 0, 0)
        sub_row.setSpacing(12)
        sub_row.addStretch()
        line_l = QFrame(); line_l.setFixedSize(26, 3)
        line_l.setStyleSheet("background:#f4f5f7; border-radius:2px;")
        sub_row.addWidget(line_l)
        sub = QLabel("MOUSE MACRO")
        sub_font = QFont(); sub_font.setFamily("Pretendard"); sub_font.setPointSize(9)
        sub_font.setWeight(QFont.Bold); sub_font.setLetterSpacing(QFont.AbsoluteSpacing, 5)
        sub.setFont(sub_font)
        sub.setStyleSheet("color:#c9cdd4;")
        sub_row.addWidget(sub)
        line_r = QFrame(); line_r.setFixedSize(26, 3)
        line_r.setStyleSheet("background:#f4f5f7; border-radius:2px;")
        sub_row.addWidget(line_r)
        sub_row.addStretch()
        bl.addLayout(sub_row)
        layout.addWidget(brand)

        # ===== Coordinate card =====
        coord_card, cc = self._card()
        cc.addLayout(self._card_header("마우스 좌표", "F8 키로 현재 위치 고정"))

        coord_grid = QHBoxLayout()
        coord_grid.setSpacing(12)

        self.live_box = self._coord_box("현재 커서 위치", self._fmt_coord(0, 0))
        self.live_coord = self.live_box.findChild(QLabel, "coordVal")
        coord_grid.addWidget(self.live_box)

        self.lock_box = self._coord_box("클릭할 위치", self._fmt_coord("—", "—"))
        self.lock_coord = self.lock_box.findChild(QLabel, "coordVal")
        coord_grid.addWidget(self.lock_box)
        cc.addLayout(coord_grid)

        self.use_locked_cb = ToggleSwitch("고정한 좌표에 클릭해요 (끄면 현재 커서 위치에 클릭해요)")
        self.use_locked_cb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        cc.addWidget(self.use_locked_cb)
        layout.addWidget(coord_card)

        # ===== Mode card =====
        mode_card, mc = self._card()
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # --- Countdown ---
        tab1 = QWidget()
        t1 = QHBoxLayout(tab1)
        t1.setContentsMargins(2, 12, 2, 2)
        t1.setSpacing(22)
        self.countdown_ring = CountdownRing()
        t1.addWidget(self.countdown_ring, alignment=Qt.AlignTop)

        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        lbl_delay = QLabel("딜레이 시간"); lbl_delay.setObjectName("fieldLabel")
        right_col.addWidget(lbl_delay)
        delay_row = QHBoxLayout(); delay_row.setSpacing(10)
        self.delay_h = QSpinBox(); self.delay_h.setRange(0, 99); self.delay_h.setSuffix(" 시간")
        self.delay_m = QSpinBox(); self.delay_m.setRange(0, 59); self.delay_m.setSuffix(" 분")
        self.delay_s = QSpinBox(); self.delay_s.setRange(0, 59); self.delay_s.setValue(5); self.delay_s.setSuffix(" 초")
        for sp in (self.delay_h, self.delay_m, self.delay_s):
            sp.setAlignment(Qt.AlignCenter)
            delay_row.addWidget(sp)
        right_col.addLayout(delay_row)

        self.delay_slider = QSlider(Qt.Horizontal)
        self.delay_slider.setRange(1, 120)
        self.delay_slider.setValue(5)
        right_col.addWidget(self.delay_slider)
        self.slider_cap = QLabel("간편 조절: 5초")
        self.slider_cap.setObjectName("hint")
        right_col.addWidget(self.slider_cap)
        right_col.addStretch()
        t1.addLayout(right_col, 1)
        self.tabs.addTab(tab1, "카운트다운")

        # --- Scheduled ---
        tab2 = QWidget()
        t2 = QVBoxLayout(tab2); t2.setContentsMargins(2, 12, 2, 2); t2.setSpacing(12)
        desc2 = QLabel("정해둔 시각에 정확히 한 번 클릭해요. 정시에 열리는 신청·등록 페이지에 좋아요.")
        desc2.setObjectName("paneDesc"); desc2.setWordWrap(True)
        t2.addWidget(desc2)
        dt_row = QHBoxLayout(); dt_row.setSpacing(12)
        self.schedule_dt = QDateTimeEdit()
        self.schedule_dt.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.schedule_dt.setDateTime(QDateTime.currentDateTime().addSecs(60))
        self.schedule_dt.setCalendarPopup(True)
        dt_row.addWidget(self.schedule_dt, 3)
        self.schedule_ms = QSpinBox(); self.schedule_ms.setRange(0, 999); self.schedule_ms.setSuffix(" ms")
        self.schedule_ms.setAlignment(Qt.AlignCenter)
        dt_row.addWidget(self.schedule_ms, 1)
        t2.addLayout(dt_row)
        self.live_clock_label = QLabel()
        self.live_clock_label.setObjectName("clockBox")
        t2.addWidget(self.live_clock_label)
        t2.addStretch()
        self.tabs.addTab(tab2, "시간 지정")

        # --- Interval ---
        tab3 = QWidget()
        t3 = QVBoxLayout(tab3); t3.setContentsMargins(2, 12, 2, 2); t3.setSpacing(14)
        desc3 = QLabel(
            f"멈추거나 지정한 횟수에 도달할 때까지 계속 클릭해요. "
            f"(안전을 위해 간격 최소 {MIN_INTERVAL_MS}ms, "
            f"무한 모드도 {MAX_RUNTIME_SECONDS // 60}분 또는 {MAX_TOTAL_CLICKS:,}회에서 자동 정지)"
        )
        desc3.setObjectName("paneDesc"); desc3.setWordWrap(True)
        t3.addWidget(desc3)

        intv_row = QHBoxLayout(); intv_row.setSpacing(12)
        lbl_intv = QLabel("클릭 간격"); lbl_intv.setObjectName("fieldLabel")
        intv_row.addWidget(lbl_intv, 1)
        self.interval_val = QSpinBox(); self.interval_val.setRange(1, 999999); self.interval_val.setValue(100)
        self.interval_val.setAlignment(Qt.AlignCenter)
        intv_row.addWidget(self.interval_val, 2)
        self.interval_unit = QComboBox(); self.interval_unit.addItems(["밀리초", "초"])
        intv_row.addWidget(self.interval_unit, 1)
        t3.addLayout(intv_row)

        count_row = QHBoxLayout(); count_row.setSpacing(14)
        lbl_count = QLabel("클릭 횟수"); lbl_count.setObjectName("fieldLabel")
        count_row.addWidget(lbl_count)
        self.radio_infinite = QRadioButton("무한 반복"); self.radio_infinite.setChecked(True)
        self.radio_finite = QRadioButton("지정 횟수")
        self.click_count = QSpinBox(); self.click_count.setRange(1, 999999); self.click_count.setValue(10)
        self.click_count.setEnabled(False); self.click_count.setFixedWidth(96)
        self.click_count.setAlignment(Qt.AlignCenter)
        self.radio_infinite.toggled.connect(lambda c: self.click_count.setEnabled(not c))
        count_row.addWidget(self.radio_infinite)
        count_row.addWidget(self.radio_finite)
        count_row.addWidget(self.click_count)
        count_row.addStretch()
        t3.addLayout(count_row)
        t3.addStretch()
        self.tabs.addTab(tab3, "반복 클릭")

        mc.addWidget(self.tabs)
        layout.addWidget(mode_card)

        # ===== Click type card =====
        click_card, clc = self._card()
        lbl_click = QLabel("마우스 클릭 종류"); lbl_click.setObjectName("fieldLabel")
        clc.addWidget(lbl_click)
        self.click_type = QComboBox()
        self.click_type.addItems(["왼쪽 클릭", "오른쪽 클릭", "왼쪽 더블 클릭"])
        clc.addWidget(self.click_type)
        layout.addWidget(click_card)

        # ===== Action buttons =====
        btn_row = QHBoxLayout(); btn_row.setSpacing(12)
        self.start_btn = QPushButton("예약 · 시작   F9")
        self.start_btn.setObjectName("startBtn")
        self.stop_btn = QPushButton("정지   F10")
        self.stop_btn.setObjectName("stopBtn")
        btn_row.addWidget(self.start_btn, 2)
        btn_row.addWidget(self.stop_btn, 1)
        layout.addLayout(btn_row)

        # ===== Status row =====
        status_card, sc = self._card()
        sc.setContentsMargins(16, 12, 16, 12)
        status_row = QHBoxLayout()
        lbl_status = QLabel("상태"); lbl_status.setObjectName("fieldLabel")
        status_row.addWidget(lbl_status)
        status_row.addStretch()
        self.status_badge = QLabel()
        self.status_badge.setObjectName("statusBadge")
        self._update_status("대기 중 (IDLE)")
        status_row.addWidget(self.status_badge)
        sc.addLayout(status_row)
        layout.addWidget(status_card)

        # ===== Console / log =====
        log_card, lg = self._card()
        log_head = QHBoxLayout(); log_head.setContentsMargins(0, 0, 0, 0)
        lbl_log = QLabel("실시간 로그"); lbl_log.setObjectName("cardTitle")
        lbl_log.setStyleSheet("font-size:13px; font-weight:600;")
        log_head.addWidget(lbl_log)
        log_head.addStretch()
        self.clear_btn = QPushButton("비우기"); self.clear_btn.setObjectName("clearBtn")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        log_head.addWidget(self.clear_btn)
        lg.addLayout(log_head)
        self.log_box = QTextEdit()
        self.log_box.setObjectName("logBox")
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(140)
        # 무한 반복 클릭 시 로그가 끝없이 쌓이지 않도록 최근 N줄만 유지
        self.log_box.document().setMaximumBlockCount(500)
        lg.addWidget(self.log_box)
        layout.addWidget(log_card)
        self._append_log("싹싹김치 매크로를 불러왔어요.", "system")
        if IS_MACOS:
            self._append_log(
                "[macOS] 단축키와 클릭이 동작하려면 시스템 설정 > 개인정보 보호 및 보안에서 "
                "'손쉬운 사용'과 '입력 모니터링' 권한을 이 앱에 허용해 주세요.", "warning"
            )

        # ===== Hotkey guide =====
        keys_card, kc = self._card()
        lbl_keys = QLabel("단축키"); lbl_keys.setObjectName("cardTitle")
        lbl_keys.setStyleSheet("font-size:13px; font-weight:600;")
        kc.addWidget(lbl_keys)
        for key, desc in (("F8", "현재 커서 위치로 좌표 고정"),
                          ("F9", "매크로 예약 · 실행"),
                          ("F10", "매크로 정지")):
            kc.addLayout(self._key_row(key, desc))
        if IS_MACOS:
            mac_hint = QLabel("macOS에서는 Fn 키와 함께 누르거나, 시스템 설정 > 키보드에서 "
                              "'F1, F2 등의 키를 표준 기능 키로 사용'을 켜 주세요.")
            mac_hint.setObjectName("hint")
            mac_hint.setWordWrap(True)
            kc.addWidget(mac_hint)
        layout.addWidget(keys_card)

        # ===== Sister-product promo bar (OFFCUT STUDIO) =====
        ad = QFrame()
        ad.setCursor(Qt.PointingHandCursor)
        ad.setStyleSheet(
            "QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #1b2230,stop:.58 #28324c,stop:1 #3a4470);"
            "border-radius:12px;}"
        )
        al = QHBoxLayout(ad)
        al.setContentsMargins(14, 11, 14, 11)
        al.setSpacing(11)
        badge = QLabel("O")
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ff8a4c,stop:1 #ff5a2e);"
            "color:#fff;border-radius:9px;font-size:17px;font-weight:900;"
        )
        al.addWidget(badge)
        ad_txt = QVBoxLayout()
        ad_txt.setSpacing(2)
        ad_t1 = QLabel('OFFCUT STUDIO  <span style="color:#ffb892;font-size:10px;">자매 제품</span>')
        ad_t1.setTextFormat(Qt.RichText)
        ad_t1.setStyleSheet("color:#fff;font-size:12.5px;font-weight:800;background:transparent;")
        ad_t2 = QLabel("긴 영상, 컷만 쏙쏙 뽑는 프리미어 편집 가속기")
        ad_t2.setStyleSheet("color:#cdd3e2;font-size:11.5px;background:transparent;")
        ad_txt.addWidget(ad_t1)
        ad_txt.addWidget(ad_t2)
        al.addLayout(ad_txt, 1)
        ad_cta = QLabel("보러가기 →")
        ad_cta.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ff8a4c,stop:1 #ff5a2e);"
            "color:#fff;border-radius:13px;padding:7px 14px;font-size:12px;font-weight:700;"
        )
        al.addWidget(ad_cta)
        ad.mouseReleaseEvent = (
            lambda e: QDesktopServices.openUrl(
                QUrl("https://www.offcut.dev/?utm_source=ssakssak_macro&utm_medium=app_banner"))
        )
        layout.addWidget(ad)

        layout.addStretch()

    def _coord_box(self, label, value_html):
        box = QFrame(); box.setObjectName("coordBox")
        v = QVBoxLayout(box); v.setContentsMargins(13, 11, 13, 11); v.setSpacing(6)
        lab = QLabel(label); lab.setObjectName("coordLabel")
        val = QLabel(value_html); val.setObjectName("coordVal"); val.setTextFormat(Qt.RichText)
        v.addWidget(lab); v.addWidget(val)
        return box

    def _key_row(self, key, desc):
        row = QHBoxLayout(); row.setSpacing(12)
        k = QLabel(key); k.setObjectName("kbd"); k.setAlignment(Qt.AlignCenter)
        k.setFixedWidth(40)
        d = QLabel(desc); d.setObjectName("keyDesc")
        row.addWidget(k); row.addWidget(d); row.addStretch()
        return row

    # ─── Connect Signals ───
    def _connect_signals(self):
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.clear_btn.clicked.connect(self.log_box.clear)

        self.delay_slider.valueChanged.connect(self._on_slider)
        for sp in (self.delay_h, self.delay_m, self.delay_s):
            sp.valueChanged.connect(self._sync_slider_from_fields)

        self.bridge.log_signal.connect(self._append_log)
        self.bridge.status_signal.connect(self._update_status)
        self.bridge.coord_locked_signal.connect(self._on_coord_locked)
        self.bridge.countdown_tick.connect(self._on_tick)
        self.bridge.reset_ring_signal.connect(self.countdown_ring.reset)
        self.bridge.release_sleep_signal.connect(self._release_sleep)
        self.bridge.click_done_signal.connect(lambda s: self._append_log(s, "success"))
        self.bridge.interval_count_signal.connect(
            lambda d, m: self._append_log(f"[반복] 클릭 {d} / {'무한' if m == -1 else m}", "normal")
        )
        self._update_installing = False
        self._update_client = UpdateClient(
            UpdateConfig("ssakssak-mouse-macro", "SsakSsakMacro.exe", "portable", "SsakSsak Macro"),
            APP_VERSION, self.bridge.update_signal.emit)
        self.bridge.update_signal.connect(self._on_update_result)
        self._update_client.recover()
        check_for_update(APP_VERSION, VERSION_INFO_URL,
                         lambda d: self.bridge.update_signal.emit(d))

    # ─── Delay slider <-> spinbox sync ───
    def _on_slider(self, v):
        if self._sync_lock:
            self.slider_cap.setText(f"간편 조절: {v}초")
            return
        self._sync_lock = True
        self.delay_h.setValue(0)
        self.delay_m.setValue(v // 60)
        self.delay_s.setValue(v % 60)
        self.slider_cap.setText(f"간편 조절: {v}초")
        self._sync_lock = False

    def _sync_slider_from_fields(self):
        if self._sync_lock:
            return
        total = self.delay_h.value() * 3600 + self.delay_m.value() * 60 + self.delay_s.value()
        if 1 <= total <= 120:
            self._sync_lock = True
            self.delay_slider.setValue(total)
            self._sync_lock = False
            self.slider_cap.setText(f"간편 조절: {total}초")
        else:
            self.slider_cap.setText("간편 조절: 범위 밖")

    # ─── Status Badge ───
    def _set_status_style(self, state):
        styles = {
            "idle":     (BG,           "#374151"),
            "armed":    (ACCENT_SOFT,  ACCENT_PRESSED),
            "clicking": (INFO_SOFT,    INFO),
            "stopped":  (DANGER_SOFT,  DANGER),
            "done":     (SUCCESS_SOFT, SUCCESS),
        }
        bg, fg = styles.get(state, styles["idle"])
        self.status_badge.setStyleSheet(
            f"QLabel#statusBadge {{ background:{bg}; color:{fg}; border-radius:999px; "
            f"padding:5px 13px; font-size:12px; font-weight:600; }}"
        )

    def _update_status(self, text):
        # Substring match on the status string (see CLAUDE.md). Order matters:
        # idle text "대기 중 (IDLE)" also contains "대기", so check IDLE first.
        state = "idle"
        if "IDLE" in text:
            state = "idle"
        elif "중단" in text:
            state = "stopped"
        elif "완료" in text:
            state = "done"
        elif "클릭" in text:
            state = "clicking"
        elif "대기" in text:
            state = "armed"
        self._set_status_style(state)
        self.status_badge.setText(f"●  {text}")

    # ─── Log ───
    def _append_log(self, msg, msg_type="normal"):
        colors = {"system": INFO, "success": SUCCESS, "warning": WARNING,
                  "error": DANGER, "normal": TEXT_2}
        c = colors.get(msg_type, TEXT_2)
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_box.append(
            f'<span style="color:{SUBTLE};">[{ts}]</span> '
            f'<span style="color:{c};">{msg}</span>'
        )

    # ─── Update check (백그라운드 → update_signal → 여기 GUI 스레드) ───
    def _on_update_result(self, d):
        kind = d.get("kind")
        if kind in ("new_version", "force_update"):
            self._update_client.begin(d.get("latest", ""))
        elif kind == "install_ready":
            if self.macro_thread and self.macro_thread.is_alive():
                self._update_client.cancel()
                QMessageBox.information(self, "업데이트 대기", "매크로 실행 중이라 설치를 미뤘습니다. 다음 실행 때 다시 확인합니다.")
                return
            answer = QMessageBox.question(self, "업데이트 준비 완료",
                "새 버전의 서명 검증이 끝났습니다. 지금 앱을 닫고 업데이트할까요?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer == QMessageBox.Yes:
                if self.macro_thread and self.macro_thread.is_alive():
                    self._update_client.cancel()
                    return
                self._update_installing = True
                self.setEnabled(False)
                if not self._update_client.install():
                    self._update_installing = False
                    self.setEnabled(True)
            else:
                self._update_client.cancel()
        elif kind == "install_started":
            self.close()
        elif kind == "install_error":
            self._update_installing = False
            self.setEnabled(True)
            QMessageBox.information(self, "업데이트 보류", d.get("message", "업데이트하지 못했습니다.") +
                                    "\n현재 앱은 계속 사용할 수 있습니다.")

    # ─── Live Cursor Timer ───
    def _start_live_cursor_timer(self):
        self.cursor_timer = QTimer(self)
        self.cursor_timer.timeout.connect(self._update_cursor_pos)
        self.cursor_timer.start(50)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(50)

    def _update_cursor_pos(self):
        pos = self.mouse.position
        self.live_coord.setText(self._fmt_coord(int(pos[0]), int(pos[1])))

    def _update_clock(self):
        if self.tabs.currentIndex() != 1:  # '시간 지정' 탭에서만 보이는 시계라 그 외엔 갱신 생략
            return
        now = datetime.now()
        ts = now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        self.live_clock_label.setText(
            f'현재 로컬 시각&nbsp;&nbsp;&nbsp;'
            f'<span style="font-family:{FONT_MONO};font-weight:700;color:{ACCENT_PRESSED};">{ts}</span>'
        )

    # ─── Coordinate Locking ───
    def _on_coord_locked(self, x, y):
        self.locked_coords = (x, y)
        self.lock_coord.setText(self._fmt_coord(x, y))
        self.lock_box.setStyleSheet(
            f"QFrame#coordBox {{ background:{ACCENT_SOFT}; border:1px solid {ACCENT}; border-radius:12px; }}"
        )
        self.lock_coord.setStyleSheet(
            f"QLabel#coordVal {{ font-family:{FONT_MONO}; font-size:18px; font-weight:700; color:{ACCENT_PRESSED}; }}"
        )
        self.use_locked_cb.setChecked(True)
        self.use_locked_cb.update()
        self._append_log(f"[LOCK] 좌표 고정: X={x}, Y={y}", "system")

    # ─── Countdown Tick ───
    def _on_tick(self, remaining, total):
        if total > 0:
            progress = (total - remaining) / total
        else:
            progress = 1.0
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        seconds = int(remaining % 60)
        tenths = int((remaining % 1) * 10)

        if hours > 0:
            ring_text = f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            ring_text = f"{minutes:02d}:{seconds:02d}.{tenths}"
        self.countdown_ring.set_progress(progress, ring_text)

    # ─── Global Hotkeys via pynput ───
    def _start_hotkey_listener(self):
        def on_press(key):
            try:
                if key == keyboard.Key.f8:
                    pos = self.mouse.position
                    self.bridge.coord_locked_signal.emit(int(pos[0]), int(pos[1]))
                    self.bridge.log_signal.emit("[HOTKEY] F8: 좌표 고정됨", "system")
                elif key == keyboard.Key.f9:
                    self.bridge.log_signal.emit("[HOTKEY] F9: 매크로 시작", "system")
                    QTimer.singleShot(0, self._on_start)
                elif key == keyboard.Key.f10:
                    self.bridge.log_signal.emit("[HOTKEY] F10: 긴급 정지", "system")
                    QTimer.singleShot(0, self._on_stop)
            except Exception as e:
                self.bridge.log_signal.emit(f"[ERROR] Hotkey: {e}", "error")

        self.hotkey_listener = keyboard.Listener(on_press=on_press)
        self.hotkey_listener.daemon = True
        self.hotkey_listener.start()

    # ─── Mouse Click ───
    def _perform_click(self, click_type_str, x=None, y=None):
        if x is not None and y is not None:
            self.mouse.position = (x, y)
            time.sleep(0.005)

        btn = Button.left
        if "오른쪽" in click_type_str or "Right" in click_type_str:
            btn = Button.right

        if "더블" in click_type_str or "Double" in click_type_str:
            self.mouse.click(Button.left, 2)
        else:
            self.mouse.click(btn, 1)

        cx, cy = self.mouse.position
        self.bridge.click_done_signal.emit(f"[딸깍] ({int(cx)}, {int(cy)}) 클릭 완료")

    # ─── Start Macro ───
    def _on_start(self):
        if self._update_installing:
            return
        if self.macro_thread and self.macro_thread.is_alive():
            self._on_stop()
            # 이전 워커가 완전히 끝난 뒤에 플래그를 비워야 중복 클릭 레이스가 안 생겨요.
            self.macro_thread.join(timeout=1.0)

        self.macro_stop.clear()
        tab_idx = self.tabs.currentIndex()
        click_type_str = self.click_type.currentText()
        use_locked = self.use_locked_cb.isChecked()

        tx, ty = None, None
        if use_locked and self.locked_coords:
            tx, ty = self.locked_coords
        elif use_locked and not self.locked_coords:
            self.bridge.log_signal.emit("[ERROR] 좌표 고정 모드이나 고정된 좌표가 없어요. F8을 눌러주세요.", "error")
            return

        if tab_idx == 0:  # Countdown
            h = self.delay_h.value()
            m = self.delay_m.value()
            s = self.delay_s.value()
            total = h * 3600 + m * 60 + s
            if total <= 0:
                self.bridge.log_signal.emit("[ERROR] 카운트다운 시간은 0초보다 커야 해요.", "error")
                return
            self.macro_thread = threading.Thread(
                target=self._worker_countdown, args=(total, click_type_str, tx, ty), daemon=True
            )
        elif tab_idx == 1:  # Scheduled
            dt = self.schedule_dt.dateTime().toPython()
            ms_offset = self.schedule_ms.value()
            target_ts = dt.timestamp() + ms_offset / 1000.0
            if target_ts <= time.time():
                self.bridge.log_signal.emit("[ERROR] 예약 시각은 현재보다 미래여야 해요.", "error")
                return
            self.macro_thread = threading.Thread(
                target=self._worker_scheduled, args=(target_ts, click_type_str, tx, ty), daemon=True
            )
        elif tab_idx == 2:  # Interval
            val = self.interval_val.value()
            unit_idx = self.interval_unit.currentIndex()
            interval_ms = val if unit_idx == 0 else val * 1000
            # 폭주 방지: 간격 하한을 강제한다.
            if interval_ms < MIN_INTERVAL_MS:
                self.bridge.log_signal.emit(
                    f"[알림] 클릭 간격이 너무 짧아 최소 {MIN_INTERVAL_MS}ms로 조정했어요.", "warning"
                )
                interval_ms = MIN_INTERVAL_MS
            max_clicks = -1 if self.radio_infinite.isChecked() else self.click_count.value()
            self.macro_thread = threading.Thread(
                target=self._worker_interval, args=(interval_ms, max_clicks, click_type_str, tx, ty), daemon=True
            )

        self.macro_thread.start()

        # Windows 절전 모드 방지
        prevent_sleep()
        self._sleep_prevented = True
        logging.info('매크로 시작 - 절전 방지 활성화')

    def _on_stop(self):
        self.macro_stop.set()
        self.bridge.status_signal.emit("중단됨 (STOPPED)")
        self.bridge.log_signal.emit("[STATUS] 매크로를 중단했어요.", "error")
        self.countdown_ring.reset()
        self._release_sleep()

    def _release_sleep(self):
        if self._sleep_prevented:
            allow_sleep()
            self._sleep_prevented = False
            logging.info('절전 방지 해제')

    # ─── Workers ───
    def _worker_countdown(self, total, click_type, tx, ty):
        try:
            h = int(total // 3600)
            m = int((total % 3600) // 60)
            s = int(total % 60)
            logging.info(f'카운트다운 시작: {h}시간 {m}분 {s}초 (총 {total}초)')
            self.bridge.status_signal.emit(f"카운트다운 {h}시간 {m}분 {s}초 대기 중...")
            start = time.time()
            target = start + total

            # 긴 타이머는 업데이트 빈도를 줄여서 안정성 확보
            update_interval = 0.5 if total > 600 else 0.1

            while time.time() < target:
                if self.macro_stop.is_set():
                    logging.info('카운트다운 사용자 중단')
                    return
                remaining = max(0, target - time.time())
                self.bridge.countdown_tick.emit(remaining, total)
                time.sleep(update_interval)

            self.bridge.countdown_tick.emit(0, total)
            logging.info('카운트다운 완료 - 클릭 실행')
            self._perform_click(click_type, tx, ty)
            self.bridge.status_signal.emit("완료")
            self.bridge.log_signal.emit("[완료] 카운트다운 클릭을 실행했어요.", "success")
            self.bridge.reset_ring_signal.emit()
        except Exception as e:
            logging.error(f'카운트다운 에러: {e}', exc_info=True)
            self.bridge.log_signal.emit(f"[ERROR] {e}", "error")
        finally:
            # SetThreadExecutionState는 호출 스레드 기준이므로 GUI 스레드에서 해제 요청.
            self.bridge.release_sleep_signal.emit()

    def _worker_scheduled(self, target_ts, click_type, tx, ty):
        try:
            dt_str = datetime.fromtimestamp(target_ts).strftime("%H:%M:%S.%f")[:-3]
            logging.info(f'예약 클릭 시작: {dt_str}')
            self.bridge.status_signal.emit(f"예약 대기 중: {dt_str}")

            while True:
                if self.macro_stop.is_set():
                    logging.info('예약 클릭 사용자 중단')
                    return
                now = time.time()
                remaining = target_ts - now
                if remaining <= 0:
                    break
                if remaining > 0.05:
                    time.sleep(min(remaining - 0.02, 0.5))
                else:
                    while time.time() < target_ts:
                        if self.macro_stop.is_set():
                            return
                    break

            logging.info('예약 시각 도달 - 클릭 실행')
            self._perform_click(click_type, tx, ty)
            actual = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.bridge.status_signal.emit("완료")
            self.bridge.log_signal.emit(f"[완료] 예약 클릭을 실행했어요 ({actual})", "success")
        except Exception as e:
            logging.error(f'예약 클릭 에러: {e}', exc_info=True)
            self.bridge.log_signal.emit(f"[ERROR] {e}", "error")
        finally:
            # SetThreadExecutionState는 호출 스레드 기준이므로 GUI 스레드에서 해제 요청.
            self.bridge.release_sleep_signal.emit()

    def _worker_interval(self, interval_ms, max_clicks, click_type, tx, ty):
        try:
            interval_s = interval_ms / 1000.0
            logging.info(f'반복 클릭 시작: 간격={interval_ms}ms, 횟수={"무한" if max_clicks == -1 else max_clicks}')
            self.bridge.status_signal.emit(f"반복 클릭 중 (매 {interval_ms}ms)")
            clicks = 0
            run_start = time.time()

            while max_clicks == -1 or clicks < max_clicks:
                if self.macro_stop.is_set():
                    logging.info(f'반복 클릭 사용자 중단 ({clicks}회 완료)')
                    return

                # ── 폭주 방지 안전 상한 ── 무한 모드에서도 강제 정지한다.
                if clicks >= MAX_TOTAL_CLICKS:
                    logging.warning(f'반복 클릭 안전 상한 도달: {clicks}회')
                    self.bridge.status_signal.emit("완료")
                    self.bridge.log_signal.emit(
                        f"[완료] 안전 상한({MAX_TOTAL_CLICKS}회)에 도달해 자동 정지했어요.", "warning"
                    )
                    return
                if time.time() - run_start >= MAX_RUNTIME_SECONDS:
                    logging.warning(f'반복 클릭 최대 실행시간 도달: {clicks}회')
                    self.bridge.status_signal.emit("완료")
                    self.bridge.log_signal.emit(
                        f"[완료] 최대 실행시간({MAX_RUNTIME_SECONDS // 60}분)에 도달해 자동 정지했어요.", "warning"
                    )
                    return

                self._perform_click(click_type, tx, ty)
                clicks += 1
                self.bridge.interval_count_signal.emit(clicks, max_clicks)

                sleep_start = time.time()
                while time.time() - sleep_start < interval_s:
                    if self.macro_stop.is_set():
                        return
                    time.sleep(0.01)

            self.bridge.status_signal.emit("완료")
            self.bridge.log_signal.emit(f"[완료] 반복 클릭을 끝냈어요 ({clicks}회)", "success")
            logging.info(f'반복 클릭 완료: {clicks}회')
        except Exception as e:
            logging.error(f'반복 클릭 에러: {e}', exc_info=True)
            self.bridge.log_signal.emit(f"[ERROR] {e}", "error")
        finally:
            # SetThreadExecutionState는 호출 스레드 기준이므로 GUI 스레드에서 해제 요청.
            self.bridge.release_sleep_signal.emit()

    def closeEvent(self, event):
        self.macro_stop.set()
        self._release_sleep()
        if hasattr(self, 'hotkey_listener'):
            self.hotkey_listener.stop()
        logging.info('프로그램 종료')
        event.accept()


def main():
    log_path = setup_logging()

    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")

        # Pretendard (번들). 실패 시 시스템 한글 폰트로 폴백.
        sans = "Pretendard" if load_app_fonts() else FALLBACK_SANS
        app.setFont(QFont(sans, 10))

        # Light palette (SsakSsak)
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(BG))
        palette.setColor(QPalette.WindowText, QColor(TEXT))
        palette.setColor(QPalette.Base, QColor(CARD))
        palette.setColor(QPalette.AlternateBase, QColor(BG))
        palette.setColor(QPalette.Text, QColor(TEXT))
        palette.setColor(QPalette.Button, QColor(CARD))
        palette.setColor(QPalette.ButtonText, QColor(TEXT))
        palette.setColor(QPalette.Highlight, QColor(ACCENT))
        palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        palette.setColor(QPalette.PlaceholderText, QColor(SUBTLE))
        app.setPalette(palette)

        window = MacroWindow()
        window.show()
        # 전체 절대경로(민감정보)는 기록하지 않고 파일명만 남긴다.
        logging.info(f'로그 파일: {os.path.basename(log_path)}')
        sys.exit(app.exec())
    except Exception as e:
        logging.critical(f'치명적 에러: {e}', exc_info=True)
        allow_sleep()
        raise


if __name__ == "__main__":
    main()
