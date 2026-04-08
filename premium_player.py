from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import vlc
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QSizePolicy,
)


MUSIC_DIR = "/home/kush/Music"
PLAYLIST_FILE = os.path.expanduser("~/.local/share/music-player/playlists.json")
QUEUE_FILE = os.path.expanduser("~/.local/share/music-player/queue.json")
LIKED_FILE = os.path.expanduser("~/.local/share/music-player/liked.json")
RECENT_FILE = os.path.expanduser("~/.local/share/music-player/recent.json")
SESSION_FILE = os.path.expanduser("~/.local/share/music-player/session.json")
APP_NAME = "Kush's Music"
ICON_PATH = "/home/kush/music-player/assets/icon.png"
LIKED_PLAYLIST_NAME = "❤️ Liked Songs"
RECENT_PLAYLIST_NAME = "🕒 Recently Played"


@dataclass(frozen=True)
class Track:
    path: str
    title: str
    artist: str
    album: str

    @property
    def display_name(self) -> str:
        if self.artist:
            return f"{self.title} - {self.artist}"
        return self.title


def format_time(ms: int) -> str:
    if ms is None or ms < 0:
        return "0:00"
    s = ms // 1000
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


def safe_load_json(path: str, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def safe_write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def read_track_tags(path: str) -> Tuple[str, str, str]:
    # Keep it resilient; MP3 tags might be missing.
    title = ""
    artist = ""
    album = ""
    try:
        audio = EasyID3(path)
        title = audio.get("title", [""])[0] or ""
        artist = audio.get("artist", [""])[0] or ""
        album = audio.get("album", [""])[0] or ""
    except Exception:
        pass

    if not title:
        # Fallback to filename
        title = os.path.splitext(os.path.basename(path))[0]
    return title, artist, album


def read_art_pixmap(path: str, size: int = 250) -> Optional[QPixmap]:
    # VLC/Qt don't provide embedded cover extraction; mutagen ID3 can.
    try:
        audio = ID3(path)
        for tag in audio.values():
            if tag.FrameID == "APIC":
                pix = QPixmap()
                pix.loadFromData(tag.data)
                return pix.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
    except Exception:
        pass
    return None


class MiniPlayer(QWidget):
    seekRequested = pyqtSignal(int)

    def __init__(self, parent: "PremiumMusicPlayer"):
        super().__init__(parent)
        self._parent = parent
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("miniRoot")

        self._user_seeking = False

        root = QFrame(self)
        root.setObjectName("miniCard")
        v = QVBoxLayout(root)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(10)

        self.thumb = QLabel()
        self.thumb.setFixedSize(42, 42)
        self.thumb.setScaledContents(True)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        self.miniTitle = QLabel("Nothing Playing")
        self.miniTitle.setObjectName("miniTitle")
        self.miniTitle.setWordWrap(False)
        self.miniArtist = QLabel("")
        self.miniArtist.setObjectName("miniArtist")
        text.addWidget(self.miniTitle)
        text.addWidget(self.miniArtist)

        btns = QVBoxLayout()
        btns.setSpacing(6)

        self.prev_btn = QPushButton("⏮")
        self.play_btn = QPushButton("▶")
        self.next_btn = QPushButton("⏭")
        for b in (self.prev_btn, self.play_btn, self.next_btn):
            b.setObjectName("miniBtn")
            b.setFixedWidth(46)
            b.setFixedHeight(30)

        self.prev_btn.clicked.connect(self._parent.play_previous)
        self.play_btn.clicked.connect(self._parent.toggle_play)
        self.next_btn.clicked.connect(self._parent.play_next)

        btns.addWidget(self.prev_btn, alignment=Qt.AlignmentFlag.AlignRight)
        btns.addWidget(self.play_btn, alignment=Qt.AlignmentFlag.AlignRight)
        btns.addWidget(self.next_btn, alignment=Qt.AlignmentFlag.AlignRight)

        row.addWidget(self.thumb)
        row.addLayout(text, 1)
        row.addLayout(btns)

        self.progress = QSlider(Qt.Orientation.Horizontal)
        self.progress.setObjectName("miniProgress")
        self.progress.setRange(0, 0)
        self.progress.sliderPressed.connect(self._on_seek_start)
        self.progress.sliderReleased.connect(self._on_seek_end)
        self.progress.sliderMoved.connect(self._on_seek_preview)

        v.addLayout(row)
        v.addWidget(self.progress)
        self._apply_style()

    def _apply_style(self) -> None:
        # A frosted/blur-ish look using translucent cards + glass borders.
        self.setStyleSheet(
            """
            QWidget#miniRoot { background: transparent; }
            QFrame#miniCard {
                background: rgba(18, 18, 24, 185);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 14px;
            }
            QLabel#miniTitle {
                color: #f3f3f5;
                font-size: 12.5px;
                font-weight: 700;
            }
            QLabel#miniArtist {
                color: rgba(243,243,245,0.72);
                font-size: 11px;
            }
            QPushButton#miniBtn {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.08);
                color: #f3f3f5;
                border-radius: 10px;
            }
            QPushButton#miniBtn:hover {
                background: rgba(29,185,84,0.20);
                border-color: rgba(29,185,84,0.30);
            }
            QSlider#miniProgress::groove:horizontal {
                height: 7px;
                background: rgba(255,255,255,0.12);
                border-radius: 6px;
            }
            QSlider#miniProgress::handle:horizontal {
                background: #1db954;
                width: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            """
        )

    def _on_seek_start(self) -> None:
        self._user_seeking = True

    def _on_seek_preview(self, val: int) -> None:
        # Keep the thumb responsive; commit on sliderReleased.
        if self._user_seeking:
            self.progress.setValue(val)

    def _on_seek_end(self) -> None:
        self._user_seeking = False
        self.seekRequested.emit(self.progress.value())

    def update_mini(
        self,
        track: Optional[Track],
        is_playing: bool,
        ms: int,
        total_ms: int,
    ) -> None:
        if track is None:
            self.miniTitle.setText("Nothing Playing")
            self.miniArtist.setText("")
        else:
            self.miniTitle.setText(track.title)
            self.miniArtist.setText(track.artist)

        self.play_btn.setText("⏸" if is_playing else "▶")

        if total_ms > 0:
            self.progress.setRange(0, total_ms)

        if not self._user_seeking:
            if total_ms > 0:
                self.progress.setValue(ms)

        # Thumbnail: best-effort; avoid blocking by not re-reading on every tick.
        if track is not None:
            # The parent will set thumbnail when track changes.
            pass


class TrackListRow(QWidget):
    def __init__(self, index: int, text: str, liked: bool, on_like_clicked):
        super().__init__()
        self._base_index_text = f"{index}."
        self.index_label = QLabel(self._base_index_text)
        self.index_label.setFixedWidth(26)
        self.index_label.setStyleSheet("color: rgba(243,243,245,0.62); font-weight: 600;")

        self.like_btn = QPushButton("♥" if liked else "♡")
        self.like_btn.setObjectName("trackLikeBtn")
        self.like_btn.setToolTip("Like / Unlike")
        self.like_btn.clicked.connect(on_like_clicked)

        self.like_opacity = QGraphicsOpacityEffect(self.like_btn)
        self.like_btn.setGraphicsEffect(self.like_opacity)
        self.like_opacity.setOpacity(0.0)

        self.like_anim = QPropertyAnimation(self.like_opacity, b"opacity", self)
        self.like_anim.setDuration(140)
        self.like_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.text_label = QLabel(text)
        self.text_label.setStyleSheet("color: rgba(243,243,245,0.95);")
        self.text_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(8)
        layout.addWidget(self.index_label, 0)
        layout.addWidget(self.text_label, 1)
        layout.addWidget(self.like_btn, 0)

    def enterEvent(self, event):
        self.index_label.setText("▶")
        self.index_label.setStyleSheet("color: rgba(29,185,84,0.96); font-weight: 700;")
        self.like_anim.stop()
        self.like_anim.setStartValue(self.like_opacity.opacity())
        self.like_anim.setEndValue(1.0)
        self.like_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.index_label.setText(self._base_index_text)
        self.index_label.setStyleSheet("color: rgba(243,243,245,0.62); font-weight: 600;")
        self.like_anim.stop()
        self.like_anim.setStartValue(self.like_opacity.opacity())
        self.like_anim.setEndValue(0.0)
        self.like_anim.start()
        super().leaveEvent(event)


class WaveformWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(28)
        self.phase = 0.0
        self.active = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(90)

    def set_active(self, active: bool) -> None:
        self.active = active
        self.update()

    def _tick(self) -> None:
        if self.active:
            self.phase += 0.38
        else:
            self.phase += 0.08
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        bars = 22
        bar_w = max(2, w // (bars * 2))
        gap = bar_w
        x = 4
        base_amp = h * (0.34 if self.active else 0.12)
        for i in range(bars):
            amp = abs(math.sin(self.phase + i * 0.44)) * base_amp + 3
            bar_h = int(amp)
            y = (h - bar_h) // 2
            alpha = 210 if self.active else 120
            p.setBrush(QColor(29, 185, 84, alpha))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(x, y, bar_w, bar_h, 2, 2)
            x += bar_w + gap
            if x > w - 6:
                break


class PremiumMusicPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1300, 780)
        self.setObjectName("appRoot")
        # Keep the main window opaque for readability/premium feel.
        # (We still use translucent "glass" panels inside the app.)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # ----- Identity (icon) -----
        app = QApplication.instance()
        if app is not None:
            app.setApplicationName(APP_NAME)
            app.setOrganizationName("home-kush")
        self._try_set_icon()

        # ----- VLC -----
        self.player = vlc.MediaPlayer()
        self._current_track: Optional[Track] = None
        self._transition_anim: Optional[QPropertyAnimation] = None
        self._art_cache: Dict[str, QPixmap] = {}

        # ----- Data -----
        # library[folder] = list[Track]
        self.library: Dict[str, List[Track]] = {}
        self.view_tracks: List[Track] = []
        self.view_base_tracks: List[Track] = []
        self.view_kind: str = "library"  # or "playlist"
        self.current_folder: str = ""
        self.current_playlist_name: Optional[str] = None
        self.playlists: Dict[str, List[str]] = {}  # name -> list[path]
        self.liked_paths: set[str] = set()
        self.recent_paths: List[str] = []

        # ----- Playback state -----
        self.queue: List[Track] = []
        self.current_queue_track_path: Optional[str] = None
        self.history: List[Track] = []
        self.history_pos: int = -1
        self._last_highlighted_path: Optional[str] = None
        self._last_saved_state_pos: int = -1
        self._last_state_track_path: Optional[str] = None
        self._last_state_position: int = 0
        self._last_state_was_playing: bool = False

        # ----- UI -----
        self._build_ui()
        self._load_playlists()
        self._load_music()
        self._load_liked()
        self._load_recent()
        self._load_queue()
        self._load_state()
        self._apply_styles()
        self._maybe_set_initial_view()
        self._restore_last_state_ui()

        # Smooth UI animations timer
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self._update_progress)
        self.progress_timer.start(250)
        self._set_volume(80)
        self._setup_shortcuts()

        # Mini-player disabled (user requested no mini-player).
        self.mini_player = None

    def _try_set_icon(self) -> None:
        # Best-effort: if icon exists, set it (never fail startup).
        try:
            if os.path.exists(ICON_PATH):
                icon = QIcon(ICON_PATH)
                self.setWindowIcon(icon)
                app = QApplication.instance()
                if app is not None:
                    app.setWindowIcon(icon)
        except Exception:
            # Never fail startup due to missing icon.
            pass

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(14)

        # ----- Sidebar -----
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 12, 12, 12)
        side_layout.setSpacing(10)

        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Search songs (title/artist)…")
        self.search.textChanged.connect(self._filter_tracks)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("tabs")

        # Library tab
        self.library_tab = QWidget()
        lib_layout = QVBoxLayout(self.library_tab)
        lib_layout.setContentsMargins(0, 0, 0, 0)
        lib_layout.setSpacing(8)
        self.folder_list = QListWidget()
        self.folder_list.setObjectName("listGlass")
        self.folder_list.itemClicked.connect(self._on_folder_selected)
        lib_layout.addWidget(self.folder_list)
        self.tabs.addTab(self.library_tab, "Library")

        # Playlists tab
        self.playlists_tab = QWidget()
        pl_layout = QVBoxLayout(self.playlists_tab)
        pl_layout.setContentsMargins(0, 0, 0, 0)
        pl_layout.setSpacing(8)

        self.playlist_list = QListWidget()
        self.playlist_list.setObjectName("listGlass")
        self.playlist_list.itemClicked.connect(self._on_playlist_selected)
        pl_layout.addWidget(self.playlist_list)

        self.new_playlist_btn = QPushButton("➕ New Playlist")
        self.new_playlist_btn.setObjectName("primaryBtn")
        self.new_playlist_btn.clicked.connect(self._create_playlist)

        pl_layout.addWidget(self.new_playlist_btn)
        self.tabs.addTab(self.playlists_tab, "Playlists")

        side_layout.addWidget(self.search)
        side_layout.addWidget(self.tabs, 1)

        # ----- Main panel -----
        main = QFrame()
        main.setObjectName("main")
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        # Now playing card
        now = QFrame()
        now.setObjectName("nowCard")
        now_layout = QHBoxLayout(now)
        now_layout.setContentsMargins(12, 12, 12, 12)
        now_layout.setSpacing(14)

        self.art_wrap = QFrame()
        self.art_wrap.setObjectName("artWrap")
        art_wrap_layout = QVBoxLayout(self.art_wrap)
        art_wrap_layout.setContentsMargins(0, 0, 0, 0)
        self.art = QLabel("No Art")
        self.art.setObjectName("art")
        self.art.setFixedSize(250, 250)
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art.setStyleSheet("color: rgba(255,255,255,0.62); font-weight: 650;")
        art_wrap_layout.addWidget(self.art)

        self.fade_effect = QGraphicsOpacityEffect(self.art)
        self.fade_effect.setOpacity(1.0)
        self.art.setGraphicsEffect(self.fade_effect)
        art_glow = QGraphicsDropShadowEffect(self.art_wrap)
        art_glow.setBlurRadius(28)
        art_glow.setOffset(0, 0)
        art_glow.setColor(QColor(29, 185, 84, 120))
        self.art_wrap.setGraphicsEffect(art_glow)

        meta = QVBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(10)
        self.title = QLabel("Nothing Playing")
        self.title.setObjectName("trackTitle")
        self.artist = QLabel("")
        self.artist.setObjectName("trackArtist")
        self.subtitle = QLabel("Pick a song to start. Use right-click to add to Queue / Playlist.")
        self.subtitle.setObjectName("trackSub")
        self.subtitle.setWordWrap(True)
        self.waveform = WaveformWidget()

        # Meta fade effects for premium transitions.
        self.title_fade = QGraphicsOpacityEffect(self.title)
        self.title_fade.setOpacity(1.0)
        self.title.setGraphicsEffect(self.title_fade)
        self.artist_fade = QGraphicsOpacityEffect(self.artist)
        self.artist_fade.setOpacity(1.0)
        self.artist.setGraphicsEffect(self.artist_fade)
        self.subtitle_fade = QGraphicsOpacityEffect(self.subtitle)
        self.subtitle_fade.setOpacity(1.0)
        self.subtitle.setGraphicsEffect(self.subtitle_fade)

        top_meta = QHBoxLayout()
        self.profile_chip = QLabel("👤 Kush")
        self.profile_chip.setObjectName("profileChip")
        top_meta.addStretch(1)
        top_meta.addWidget(self.profile_chip, 0, Qt.AlignmentFlag.AlignRight)
        meta.addLayout(top_meta)
        meta.addWidget(self.title)
        meta.addWidget(self.artist)
        meta.addWidget(self.subtitle)
        meta.addWidget(self.waveform)

        meta.addStretch(1)

        self.play_controls = QHBoxLayout()
        self.prev = QPushButton("⏮")
        self.play = QPushButton("▶")
        self.next = QPushButton("⏭")
        self.like_now_btn = QPushButton("♡")
        self.like_now_btn.setObjectName("likeNowBtn")
        self.like_now_btn.setToolTip("Like / Unlike this track")
        self.like_now_btn.clicked.connect(self._toggle_current_track_like)
        for b in (self.prev, self.play, self.next):
            b.setObjectName("iconBtn")

        self.prev.clicked.connect(self.play_previous)
        self.play.clicked.connect(self.toggle_play)
        self.next.clicked.connect(self.play_next)

        self.play_controls.addWidget(self.prev)
        self.play_controls.addWidget(self.play)
        self.play_controls.addWidget(self.next)
        self.play_controls.addWidget(self.like_now_btn)
        self.volume_label = QLabel("Vol")
        self.volume_label.setObjectName("timeLabel")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("progress")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(120)
        self.volume_slider.valueChanged.connect(self._set_volume)
        self.play_controls.addWidget(self.volume_label)
        self.play_controls.addWidget(self.volume_slider)

        meta.addLayout(self.play_controls)

        now_layout.addWidget(self.art_wrap)
        now_layout.addLayout(meta, 1)

        main_layout.addWidget(now)

        header_row = QHBoxLayout()
        self.list_header_label = QLabel("Tracks")
        self.list_header_label.setObjectName("queueTitle")
        self.song_count_label = QLabel("0 songs")
        self.song_count_label.setObjectName("timeLabel")
        header_row.addWidget(self.list_header_label)
        header_row.addStretch(1)
        header_row.addWidget(self.song_count_label)
        main_layout.addLayout(header_row)

        # Track list + quick actions
        self.track_list = QListWidget()
        self.track_list.setObjectName("listGlass")
        self.track_list.itemClicked.connect(self.play_selected)
        self.track_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.track_list.customContextMenuRequested.connect(self._track_context_menu)
        self.track_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.track_list.setSpacing(4)

        main_layout.addWidget(self.track_list, 2)

        # Progress / seeking + time
        progRow = QHBoxLayout()
        progRow.setContentsMargins(0, 0, 0, 0)
        progRow.setSpacing(10)
        self.elapsed = QLabel("0:00")
        self.elapsed.setObjectName("timeLabel")
        self.total = QLabel("0:00")
        self.total.setObjectName("timeLabel")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName("progress")
        self.slider.setRange(0, 0)

        self._user_seeking = False
        self.slider.sliderPressed.connect(self._on_seek_start)
        self.slider.sliderReleased.connect(self._on_seek_end)

        progRow.addWidget(self.elapsed)
        progRow.addWidget(self.slider, 1)
        progRow.addWidget(self.total)

        main_layout.addLayout(progRow)

        outer.addWidget(sidebar, 1)
        outer.addWidget(main, 3)

        # ----- Queue panel -----
        queue_panel = QFrame()
        queue_panel.setObjectName("queuePanel")
        queue_layout = QVBoxLayout(queue_panel)
        queue_layout.setContentsMargins(12, 12, 12, 12)
        queue_layout.setSpacing(10)

        self.queue_title = QLabel("Queue (0)")
        self.queue_title.setObjectName("queueTitle")
        queue_layout.addWidget(self.queue_title)

        self.queue_list = QListWidget()
        self.queue_list.setObjectName("listGlass")
        self.queue_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.queue_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.queue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue_list.customContextMenuRequested.connect(self._queue_context_menu)
        self.queue_list.itemDoubleClicked.connect(self.play_queue_item)
        self.queue_list.model().rowsMoved.connect(self._on_queue_rows_moved)
        queue_layout.addWidget(self.queue_list, 1)

        qbtns = QHBoxLayout()
        self.play_queue_btn = QPushButton("Play")
        self.play_queue_btn.setObjectName("primaryBtnSmall")
        self.play_queue_btn.clicked.connect(self.play_selected_queue_item)

        self.remove_queue_btn = QPushButton("Remove")
        self.remove_queue_btn.setObjectName("ghostBtnSmall")
        self.remove_queue_btn.clicked.connect(self.remove_selected_queue_item)

        qbtns.addWidget(self.play_queue_btn)
        qbtns.addWidget(self.remove_queue_btn)

        queue_layout.addLayout(qbtns)

        self.clear_queue_btn = QPushButton("Clear Queue")
        self.clear_queue_btn.setObjectName("ghostBtn")
        self.clear_queue_btn.clicked.connect(self.clear_queue)
        queue_layout.addWidget(self.clear_queue_btn)

        outer.addWidget(queue_panel, 1)

        # Hide mini-player toggle in this iteration; you can show it on demand.
        # Mini-player will appear after first play.

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                font-family: "Segoe UI", "Inter", system-ui, -apple-system, Arial, sans-serif;
            }
            QMainWindow#appRoot {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(10,10,14,255), stop:1 rgba(22,22,30,255));
            }
            QWidget#root {
                background: transparent;
            }
            QFrame#sidebar, QFrame#main, QFrame#queuePanel {
                background: rgba(18,18,24,220);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 18px;
            }
            QFrame#main { padding: 0px; }
            QFrame#nowCard {
                background: rgba(255,255,255,0.07);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 18px;
            }
            QPushButton {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.10);
                color: #f3f3f5;
                border-radius: 14px;
                padding: 8px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(29,185,84,0.18);
                border: 1px solid rgba(29,185,84,0.35);
            }
            QPushButton:pressed {
                background: rgba(29,185,84,0.35);
            }

            QWidget#root QLineEdit#search {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 12px;
                padding: 10px;
                color: #f3f3f5;
            }

            QTabWidget#tabs::pane {
                border: none;
            }
            QTabWidget#tabs::tab-bar {
                left: 0px;
            }
            QTabWidget#tabs::tab {
                background: rgba(255,255,255,0.04);
                color: rgba(243,243,245,0.80);
                padding: 8px 10px;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QTabWidget#tabs::tab:selected {
                background: rgba(29,185,84,0.22);
                border: 1px solid rgba(29,185,84,0.35);
                color: #f3f3f5;
            }
            QTabBar::tab {
                background: rgba(255,255,255,0.05);
                color: rgba(243,243,245,0.8);
                padding: 8px 14px;
                border-radius: 10px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: rgba(29,185,84,0.25);
                color: #ffffff;
            }
            QTabBar::tab:hover {
                background: rgba(255,255,255,0.12);
            }

            QListWidget#listGlass {
                background: transparent;
                border: none;
                color: rgba(243,243,245,0.95);
                outline: none;
            }
            QListWidget#listGlass::item {
                padding: 10px 10px;
                border-radius: 12px;
                margin: 1px 0px;
            }
            QListWidget#listGlass::item:hover {
                background: rgba(255,255,255,0.07);
            }
            QListWidget#listGlass::item:selected {
                background: rgba(29,185,84,0.95);
                color: rgba(0,0,0,0.95);
            }

            QLabel#trackTitle {
                color: #f3f3f5;
                font-size: 22px;
                font-weight: 800;
            }
            QLabel#trackArtist {
                color: rgba(243,243,245,0.70);
                font-size: 14px;
                font-weight: 650;
            }
            QLabel#trackSub {
                color: rgba(243,243,245,0.60);
                font-size: 12.5px;
            }
            QLabel#profileChip {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 14px;
                padding: 6px 10px;
                color: rgba(243,243,245,0.95);
                font-weight: 650;
            }

            QPushButton#iconBtn, QPushButton#primaryBtn, QPushButton#primaryBtnSmall, QPushButton#ghostBtn, QPushButton#ghostBtnSmall {
                border-radius: 16px;
                padding: 10px 14px;
                font-weight: 800;
            }
            QPushButton#likeNowBtn {
                background: rgba(255,255,255,0.07);
                border: 1px solid rgba(255,255,255,0.10);
                color: rgba(243,243,245,0.95);
                border-radius: 16px;
                min-width: 52px;
                padding: 9px 14px;
                font-size: 16px;
            }
            QPushButton#likeNowBtn:hover {
                background: rgba(255,77,109,0.20);
                border-color: rgba(255,77,109,0.35);
            }

            QPushButton#iconBtn {
                background: rgba(255,255,255,0.07);
                border: 1px solid rgba(255,255,255,0.10);
                color: #f3f3f5;
                padding: 9px 14px;
                min-width: 52px;
            }
            QPushButton#iconBtn:hover {
                background: rgba(29,185,84,0.20);
                border-color: rgba(29,185,84,0.30);
            }
            QPushButton#primaryBtn {
                background: rgba(29,185,84,0.95);
                border: 1px solid rgba(29,185,84,0.95);
                color: rgba(0,0,0,0.92);
            }
            QPushButton#primaryBtnSmall {
                background: rgba(29,185,84,0.95);
                border: 1px solid rgba(29,185,84,0.95);
                color: rgba(0,0,0,0.92);
                padding: 9px 12px;
                border-radius: 14px;
            }
            QPushButton#ghostBtn {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.10);
                color: rgba(243,243,245,0.86);
                padding: 10px 14px;
            }
            QPushButton#ghostBtnSmall {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.10);
                color: rgba(243,243,245,0.86);
                padding: 9px 12px;
                border-radius: 14px;
            }
            QPushButton#ghostBtn:hover, QPushButton#ghostBtnSmall:hover {
                border-color: rgba(29,185,84,0.30);
                background: rgba(29,185,84,0.12);
            }
            QPushButton#trackLikeBtn {
                background: transparent;
                border: none;
                color: rgba(243,243,245,0.88);
                font-size: 15px;
                min-width: 28px;
                max-width: 28px;
            }
            QPushButton#trackLikeBtn:hover {
                color: rgba(255,77,109,0.95);
            }

            QSlider#progress::groove:horizontal {
                height: 8px;
                background: rgba(255,255,255,0.12);
                border-radius: 5px;
            }
            QSlider#progress::sub-page:horizontal {
                background: #1db954;
                border-radius: 5px;
            }
            QSlider#progress::add-page:horizontal {
                background: rgba(255,255,255,0.12);
                border-radius: 5px;
            }
            QSlider#progress::handle:horizontal {
                background: #1db954;
                width: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
            QSlider#progress:hover::groove:horizontal {
                background: rgba(255,255,255,0.20);
            }

            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.28);
                border-radius: 4px;
                min-height: 28px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255,255,255,0.45);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
                border: none;
                height: 0px;
            }

            QLabel#timeLabel {
                color: rgba(243,243,245,0.70);
                font-size: 12.5px;
                font-weight: 650;
                min-width: 42px;
            }

            QLabel#queueTitle {
                color: rgba(243,243,245,0.80);
                font-size: 14px;
                font-weight: 800;
            }

            QLabel#art {
                border-radius: 18px;
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.12);
            }
            QFrame#artWrap {
                background: transparent;
            }
            """
        )

    def _maybe_set_initial_view(self) -> None:
        if self.folder_list.count() > 0:
            self.current_folder = self.folder_list.item(0).text()
            self._on_folder_selected(self.folder_list.item(0))
        self._refresh_playlist_list()

    def _load_music(self) -> None:
        self.library.clear()
        if not os.path.exists(MUSIC_DIR):
            self.folder_list.clear()
            self.folder_list.addItem("Music folder not found: " + MUSIC_DIR)
            return

        for root, _, files in os.walk(MUSIC_DIR):
            mp3s = [f for f in files if f.lower().endswith(".mp3")]
            if not mp3s:
                continue
            folder = os.path.basename(root)
            self.library.setdefault(folder, [])

            for f in mp3s:
                path = os.path.join(root, f)
                title, artist, album = read_track_tags(path)
                self.library[folder].append(Track(path=path, title=title, artist=artist, album=album))

        # Populate folders
        self.folder_list.clear()
        for folder in sorted(self.library.keys()):
            self.folder_list.addItem(folder)

    def _load_playlists(self) -> None:
        raw = safe_load_json(PLAYLIST_FILE, default={})
        if isinstance(raw, dict) and "playlists" in raw:
            self.playlists = raw.get("playlists", {}) or {}
        elif isinstance(raw, dict):
            # Backward compat: old schema was {name: [paths...]}
            self.playlists = {k: v for k, v in raw.items() if isinstance(v, list)}
        else:
            self.playlists = {}

        self._refresh_playlist_list()

    def _refresh_playlist_list(self) -> None:
        self.playlist_list.clear()
        self.playlist_list.addItem(LIKED_PLAYLIST_NAME)
        self.playlist_list.addItem(RECENT_PLAYLIST_NAME)
        for name in sorted(self.playlists.keys()):
            self.playlist_list.addItem(name)

    def _save_playlists(self) -> None:
        safe_write_json(PLAYLIST_FILE, {"version": 2, "playlists": self.playlists})

    def _load_liked(self) -> None:
        raw = safe_load_json(LIKED_FILE, default={})
        liked_paths: List[str] = []
        if isinstance(raw, dict):
            arr = raw.get("liked", [])
            if isinstance(arr, list):
                liked_paths = [p for p in arr if isinstance(p, str)]
        elif isinstance(raw, list):
            liked_paths = [p for p in raw if isinstance(p, str)]

        valid = set()
        for p in liked_paths:
            if self._track_by_path(p) is not None:
                valid.add(p)
        self.liked_paths = valid
        self._save_liked()
        self._update_now_like_button()

    def _save_liked(self) -> None:
        safe_write_json(LIKED_FILE, {"version": 1, "liked": sorted(self.liked_paths)})

    def _load_recent(self) -> None:
        raw = safe_load_json(RECENT_FILE, default={})
        paths: List[str] = []
        if isinstance(raw, dict):
            arr = raw.get("recent", [])
            if isinstance(arr, list):
                paths = [p for p in arr if isinstance(p, str)]
        elif isinstance(raw, list):
            paths = [p for p in raw if isinstance(p, str)]

        valid: List[str] = []
        seen = set()
        for p in paths:
            if p in seen:
                continue
            if self._track_by_path(p) is None:
                continue
            seen.add(p)
            valid.append(p)
        self.recent_paths = valid[:100]
        self._save_recent()

    def _save_recent(self) -> None:
        safe_write_json(RECENT_FILE, {"version": 1, "recent": self.recent_paths[:100]})

    def _load_state(self) -> None:
        raw = safe_load_json(SESSION_FILE, default={})
        if not isinstance(raw, dict):
            return
        track = raw.get("last_track")
        pos = raw.get("position", 0)
        was_playing = raw.get("was_playing", False)
        if isinstance(track, str):
            self._last_state_track_path = track
        if isinstance(pos, int):
            self._last_state_position = max(0, pos)
        self._last_state_was_playing = bool(was_playing)

    def _save_state(self, track_path: str, position: int, was_playing: bool = False) -> None:
        safe_write_json(
            SESSION_FILE,
            {
                "version": 1,
                "last_track": track_path,
                "position": max(0, int(position)),
                "was_playing": bool(was_playing),
            },
        )

    def _restore_last_state_ui(self) -> None:
        if not self._last_state_track_path:
            return
        track = self._track_by_path(self._last_state_track_path)
        if track is None:
            return
        self._current_track = track
        self.player.set_media(vlc.Media(track.path))
        self.player.pause()
        self.title.setText(track.title)
        self.artist.setText(track.artist)
        self.subtitle.setText(track.album or "")
        self.elapsed.setText(format_time(self._last_state_position))
        self.slider.setValue(self._last_state_position)
        self.play.setText("▶")
        pix = self._art_cache.get(track.path)
        if pix is None:
            pix = read_art_pixmap(track.path, size=250)
            if pix is not None:
                self._art_cache[track.path] = pix
        if pix:
            self.art.setPixmap(pix)
            self.art.setText("")
        else:
            self.art.setPixmap(QPixmap())
            self.art.setText("No Art")
        self._sync_highlight_to_current_track()
        self._update_now_like_button()
        if self._last_state_was_playing:
            self.player.play()
            self.play.setText("⏸")
            QTimer.singleShot(200, lambda: self.player.set_time(self._last_state_position))

    def _push_recent(self, path: str) -> None:
        if not path:
            return
        self.recent_paths = [p for p in self.recent_paths if p != path]
        self.recent_paths.insert(0, path)
        self.recent_paths = self.recent_paths[:100]
        self._save_recent()

    def _recent_tracks(self) -> List[Track]:
        tracks: List[Track] = []
        for p in self.recent_paths:
            t = self._track_by_path(p)
            if t is not None:
                tracks.append(t)
        return tracks

    def _is_liked(self, path: str) -> bool:
        return path in self.liked_paths

    def _liked_tracks(self) -> List[Track]:
        raw = safe_load_json(LIKED_FILE, default={})
        if isinstance(raw, dict):
            ordered_paths = raw.get("liked", [])
        elif isinstance(raw, list):
            ordered_paths = raw
        else:
            ordered_paths = []
        if not isinstance(ordered_paths, list):
            ordered_paths = []
        tracks: List[Track] = []
        for p in ordered_paths:
            if not isinstance(p, str):
                continue
            t = self._track_by_path(p)
            if t is not None:
                tracks.append(t)
        if tracks:
            return tracks
        # fallback if file order missing
        return [t for t in (self._track_by_path(p) for p in self.liked_paths) if t is not None]

    def _toggle_like(self, path: str) -> None:
        if not path:
            return
        if path in self.liked_paths:
            self.liked_paths.remove(path)
        else:
            self.liked_paths.add(path)
        self._save_liked()
        self._update_now_like_button()
        if self.current_playlist_name == LIKED_PLAYLIST_NAME:
            self.view_base_tracks = self._liked_tracks()
            self.view_tracks = list(self.view_base_tracks)
        self._render_track_list()

    def _toggle_current_track_like(self) -> None:
        if self._current_track is None:
            return
        self._toggle_like(self._current_track.path)

    def _update_now_like_button(self) -> None:
        if not hasattr(self, "like_now_btn"):
            return
        liked = self._current_track is not None and self._is_liked(self._current_track.path)
        self.like_now_btn.setText("♥" if liked else "♡")
        if liked:
            self.like_now_btn.setStyleSheet(
                "background: rgba(255,77,109,0.22); border:1px solid rgba(255,77,109,0.40); color:#ff4d6d;"
            )
        else:
            self.like_now_btn.setStyleSheet("")

    def _load_queue(self) -> None:
        raw = safe_load_json(QUEUE_FILE, default={})
        paths: List[str] = []
        current_path: Optional[str] = None
        if isinstance(raw, dict):
            queue_paths = raw.get("queue", [])
            if isinstance(queue_paths, list):
                paths = [p for p in queue_paths if isinstance(p, str)]
            cp = raw.get("current_queue_track_path")
            if isinstance(cp, str):
                current_path = cp

        self.queue = self._tracks_from_paths(paths)
        self.current_queue_track_path = current_path
        self._render_queue_list()

    def _save_queue(self) -> None:
        payload = {
            "version": 1,
            "queue": [t.path for t in self.queue],
            "current_queue_track_path": self.current_queue_track_path,
        }
        safe_write_json(QUEUE_FILE, payload)

    def _create_playlist(self) -> None:
        name, ok = QInputDialog.getText(self, "Playlist", "Enter name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self.playlists:
            QMessageBox.information(self, "Playlist", "Playlist already exists.")
            return
        self.playlists[name] = []
        self._save_playlists()
        self._refresh_playlist_list()
        # auto-select
        self._select_playlist_by_name(name)

    def _select_playlist_by_name(self, name: str) -> None:
        matches = self.playlist_list.findItems(name, Qt.MatchFlag.MatchExactly)
        if matches:
            self._on_playlist_selected(matches[0])

    def _on_folder_selected(self, item: QListWidgetItem) -> None:
        folder = item.text()
        if folder not in self.library:
            return
        self.current_folder = folder
        self.view_kind = "library"
        tracks = self.library.get(folder, [])
        self.current_playlist_name = None
        self.view_base_tracks = list(tracks)
        self.view_tracks = list(self.view_base_tracks)
        self._render_track_list()

    def _on_playlist_selected(self, item: QListWidgetItem) -> None:
        name = item.text()
        if name == LIKED_PLAYLIST_NAME:
            self.current_playlist_name = name
            tracks = self._liked_tracks()
            self.view_kind = "playlist"
            self.view_base_tracks = list(tracks)
            self.view_tracks = list(self.view_base_tracks)
            self._render_track_list()
            return
        if name == RECENT_PLAYLIST_NAME:
            self.current_playlist_name = name
            tracks = self._recent_tracks()
            self.view_kind = "playlist"
            self.view_base_tracks = list(tracks)
            self.view_tracks = list(self.view_base_tracks)
            self._render_track_list()
            return

        if name not in self.playlists:
            return
        self.current_playlist_name = name
        paths = self.playlists.get(name, [])
        tracks = self._tracks_from_paths(paths)
        self.view_kind = "playlist"
        self.view_base_tracks = list(tracks)
        self.view_tracks = list(self.view_base_tracks)
        self._render_track_list()

    def _tracks_from_paths(self, paths: List[str]) -> List[Track]:
        # Best-effort: we already built a local index. Prefer using that index.
        by_path = {t.path: t for v in self.library.values() for t in v}
        tracks: List[Track] = []
        for p in paths:
            if p in by_path:
                tracks.append(by_path[p])
        return tracks

    def _filter_tracks(self, _text: str = "") -> None:
        q = self.search.text().strip().lower()
        if not self.view_base_tracks and not q:
            return

        all_tracks = list(self.view_base_tracks)
        if not q:
            self.view_tracks = list(all_tracks)
            self._render_track_list()
            return

        filtered = []
        for t in all_tracks:
            blob = f"{t.title} {t.artist} {t.album}".lower()
            if q in blob:
                filtered.append(t)
        self.view_tracks = filtered
        self._render_track_list()

    def _render_track_list(self) -> None:
        self.track_list.clear()
        self.song_count_label.setText(f"{len(self.view_tracks)} songs")
        if self.view_kind == "library":
            self.list_header_label.setText(f"Library • {len(self.view_tracks)} songs")
        elif self.current_playlist_name:
            self.list_header_label.setText(f"{self.current_playlist_name} • {len(self.view_tracks)} songs")
        else:
            self.list_header_label.setText(f"Tracks • {len(self.view_tracks)} songs")
        if not self.view_tracks:
            empty = QListWidgetItem("🎵 No songs found\nTry adding music to your folder")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.track_list.addItem(empty)
            return

        for i, t in enumerate(self.view_tracks, start=1):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, t.path)
            item.setToolTip(f"{t.title}\n{t.artist}\n{t.album}")
            self.track_list.addItem(item)
            row = TrackListRow(
                i,
                t.display_name,
                self._is_liked(t.path),
                on_like_clicked=lambda _=False, p=t.path: self._toggle_like(p),
            )
            self.track_list.setItemWidget(item, row)

        # Keep selection in sync
        self._sync_highlight_to_current_track()

    def _sync_highlight_to_current_track(self) -> None:
        if not self._current_track:
            return
        current_path = self._current_track.path
        if self._last_highlighted_path == current_path:
            return
        for i in range(self.track_list.count()):
            item = self.track_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == current_path:
                self.track_list.setCurrentItem(item)
                self.track_list.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
                self._last_highlighted_path = current_path
                return

        # If current track isn't in this view (e.g. queue contains it), do nothing.

    def _track_context_menu(self, pos: QPoint) -> None:
        item = self.track_list.itemAt(pos)
        if not item:
            return
        track_path = item.data(Qt.ItemDataRole.UserRole)
        track = self._track_by_path(track_path)
        if not track:
            return

        menu = QMenu(self)
        add_queue = menu.addAction("Add to Queue")
        play_next = menu.addAction("Play Next")
        like_action = menu.addAction("Unlike" if self._is_liked(track.path) else "Like")
        add_playlist = menu.addAction("Add to Playlist…")

        action = menu.exec(self.track_list.mapToGlobal(pos))
        if action == add_queue:
            self.enqueue_track(track)
        elif action == play_next:
            self.enqueue_track(track, play_next=True)
        elif action == like_action:
            self._toggle_like(track.path)
        elif action == add_playlist:
            self._add_track_to_playlist(track)

    def _queue_context_menu(self, pos: QPoint) -> None:
        item = self.queue_list.itemAt(pos)
        if not item:
            return
        idx = self.queue_list.row(item)

        menu = QMenu(self)
        play_now = menu.addAction("Play from Queue")
        remove = menu.addAction("Remove")
        clear = menu.addAction("Clear Queue")
        action = menu.exec(self.queue_list.mapToGlobal(pos))
        if action == play_now:
            self.play_queue_at(self.queue_list.row(item))
        elif action == remove:
            self.remove_queue_at(int(idx))
        elif action == clear:
            self.clear_queue()

    def _track_by_path(self, path: str) -> Optional[Track]:
        if not path:
            return None
        for tracks in self.library.values():
            for t in tracks:
                if t.path == path:
                    return t
        return None

    def enqueue_track(self, track: Track, play_next: bool = False) -> None:
        if play_next:
            self.queue.insert(0, track)
        else:
            self.queue.append(track)
        self._render_queue_list()
        self._save_queue()

    def _add_track_to_playlist(self, track: Track) -> None:
        names = list(self.playlists.keys())
        if not names:
            create_first = QMessageBox.question(
                self,
                "Playlists",
                "No playlists found. Create one first?",
            )
            if create_first != QMessageBox.StandardButton.Yes:
                return
            self._create_playlist()
            names = list(self.playlists.keys())
            if not names:
                return

        name, ok = QInputDialog.getItem(self, "Playlist", "Choose:", names, 0, False)
        if not ok or not name:
            return
        self.playlists[name].append(track.path)
        self._save_playlists()

    def _render_queue_list(self) -> None:
        self.queue_list.clear()
        self.queue_title.setText(f"Queue ({len(self.queue)})")
        if not self.queue:
            empty = QListWidgetItem("🎧 Your queue is empty\nStart adding songs")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.queue_list.addItem(empty)
            return
        for t in self.queue:
            label = t.display_name
            is_current = self.current_queue_track_path == t.path
            if is_current:
                label = "▶ " + label
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, t.path)
            item.setToolTip(t.path)
            if is_current:
                item.setBackground(QColor(29, 185, 84, 80))
            self.queue_list.addItem(item)

    def play_selected(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        track = self._track_by_path(path)
        if not track:
            return
        # Spotify-ish: selecting a song plays it immediately, queue starts fresh.
        self.queue.clear()
        self.current_queue_track_path = None
        self._render_queue_list()
        self._save_queue()
        self._play_track(track, add_to_history=True, from_queue=False)

    def toggle_play(self) -> None:
        if self.player.is_playing():
            self.player.pause()
            self.play.setText("▶")
        else:
            # If nothing has been loaded yet, attempt to play last known track.
            if self._current_track is None and self.view_tracks:
                self._play_track(self.view_tracks[0], add_to_history=True, from_queue=False)
            else:
                self.player.play()
            self.play.setText("⏸")

    def _on_seek_start(self) -> None:
        self._user_seeking = True

    def _on_seek_end(self) -> None:
        self._user_seeking = False
        self.seek(self.slider.value())

    def seek(self, ms: int) -> None:
        try:
            self.player.set_time(int(ms))
        except Exception:
            pass

    def play_next(self) -> None:
        if self.queue:
            track = self.queue.pop(0)
            self.current_queue_track_path = track.path
            self._render_queue_list()
            self._save_queue()
            self._play_track(track, add_to_history=True, from_queue=True)
            return

        # If user pressed previous before, and we have a forward history, use it.
        if self.history_pos < len(self.history) - 1:
            self.history_pos += 1
            track = self.history[self.history_pos]
            self._play_track(track, add_to_history=False, from_queue=False)
            return

        # Otherwise, move within current view.
        if self._current_track:
            cur_idx = self._index_in_view(self._current_track.path)
            if cur_idx is not None and cur_idx < len(self.view_tracks) - 1:
                self._play_track(self.view_tracks[cur_idx + 1], add_to_history=True, from_queue=False)

    def play_previous(self) -> None:
        self.current_queue_track_path = None
        self._render_queue_list()
        self._save_queue()
        # Spotify-ish: previous uses history stack if available.
        if self.history_pos > 0:
            self.history_pos -= 1
            track = self.history[self.history_pos]
            self._play_track(track, add_to_history=False, from_queue=False)
            return

        # Fallback: move within view.
        if self._current_track:
            cur_idx = self._index_in_view(self._current_track.path)
            if cur_idx is not None and cur_idx > 0:
                self._play_track(self.view_tracks[cur_idx - 1], add_to_history=True, from_queue=False)

    def _index_in_view(self, path: str) -> Optional[int]:
        for i, t in enumerate(self.view_tracks):
            if t.path == path:
                return i
        return None

    def play_queue_item(self, item: QListWidgetItem) -> None:
        idx = self.queue_list.row(item)
        if idx < 0:
            return
        self.play_queue_at(idx)

    def play_selected_queue_item(self) -> None:
        item = self.queue_list.currentItem()
        if not item:
            return
        idx = self.queue_list.row(item)
        if idx < 0:
            return
        self.play_queue_at(idx)

    def play_queue_at(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.queue):
            return

        # Play the selected queue item now, and skip everything before it.
        # Spotify-ish behavior: jumping to an item in the queue skips ahead.
        track = self.queue[idx]
        self.queue = self.queue[idx + 1 :]
        self.current_queue_track_path = track.path
        self._render_queue_list()
        self._save_queue()
        self._play_track(track, add_to_history=True, from_queue=True)

    def play_queue_item_safe(self, idx: int) -> None:
        # Backward-compatible alias; keep for any older callers.
        if idx < 0 or idx >= len(self.queue):
            return
        self.play_queue_at(idx)

    def remove_queue_at(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.queue):
            return
        removed = self.queue[idx]
        self.queue.pop(idx)
        if self.current_queue_track_path == removed.path:
            self.current_queue_track_path = None
        self._render_queue_list()
        self._save_queue()

    def remove_selected_queue_item(self) -> None:
        item = self.queue_list.currentItem()
        if not item:
            return
        idx = self.queue_list.row(item)
        if idx < 0:
            return
        self.remove_queue_at(idx)

    def clear_queue(self) -> None:
        self.queue.clear()
        self.current_queue_track_path = None
        self._render_queue_list()
        self._save_queue()

    def _on_queue_rows_moved(self, *_args) -> None:
        # Rebuild queue in the new visual order after drag-and-drop.
        ordered: List[Track] = []
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            path = item.data(Qt.ItemDataRole.UserRole)
            track = self._track_by_path(path)
            if track is not None:
                ordered.append(track)
        self.queue = ordered
        self._save_queue()

    def _fade_to_new_track(self, new_track: Track, from_queue: bool) -> None:
        # Fade art card quickly for smooth premium transitions.
        self.subtitle.setText("Loading…")

        old_opacity = self.fade_effect.opacity()

        fade_out_group = QParallelAnimationGroup(self)
        for eff in (self.fade_effect, self.title_fade, self.artist_fade, self.subtitle_fade):
            anim = QPropertyAnimation(eff, b"opacity")
            anim.setDuration(180)
            anim.setStartValue(old_opacity)
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
            fade_out_group.addAnimation(anim)

        fade_in_group = QParallelAnimationGroup(self)
        for eff in (self.fade_effect, self.title_fade, self.artist_fade, self.subtitle_fade):
            anim = QPropertyAnimation(eff, b"opacity")
            anim.setDuration(220)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            fade_in_group.addAnimation(anim)

        seq = QSequentialAnimationGroup(self)
        seq.addAnimation(fade_out_group)
        seq.addAnimation(fade_in_group)

        def on_out_started():
            # Ensure fade-out begins immediately even if effects were altered.
            pass

        def on_out_finished():
            self._set_media_and_play(new_track, add_to_history=True, from_queue=from_queue)

        fade_out_group.stateChanged.connect(lambda *_: on_out_started())
        fade_out_group.finished.connect(on_out_finished)

        self._transition_anim = seq  # keep reference alive for whole sequence
        seq.start()

    def _play_track(self, track: Track, add_to_history: bool, from_queue: bool) -> None:
        if add_to_history:
            if self.history_pos < len(self.history) - 1:
                self.history = self.history[: self.history_pos + 1]
            if self.history_pos == -1 or self.history[self.history_pos].path != track.path:
                self.history.append(track)
                self.history_pos = len(self.history) - 1

        self._current_track = track

        # Update selection + mini-player immediately (so highlight feels responsive),
        # while audio loads during fade.
        self._sync_highlight_to_current_track()

        # Fade animation for premium effect.
        self._fade_to_new_track(track, from_queue=from_queue)

    def _set_media_and_play(self, track: Track, add_to_history: bool, from_queue: bool) -> None:
        # Note: add_to_history is handled outside; keep signature for clarity.
        try:
            self.player.stop()
        except Exception:
            pass

        media = vlc.Media(track.path)
        self.player.set_media(media)
        self.player.play()
        self.play.setText("⏸")

        # Update meta
        self.title.setText(track.title)
        self.artist.setText(track.artist)
        self.subtitle.setText(track.album or "")

        # Update art
        pix = self._art_cache.get(track.path)
        if pix is None:
            pix = read_art_pixmap(track.path, size=250)
            if pix is not None:
                self._art_cache[track.path] = pix
        if pix:
            self.art.setPixmap(pix)
            self.art.setText("")
        else:
            self.art.setPixmap(QPixmap())
            self.art.setText("No Art")

        # Ensure track highlight is in sync.
        self._sync_highlight_to_current_track()
        self._update_now_like_button()
        self._push_recent(track.path)
        self._save_state(track.path, 0, was_playing=True)

    def _set_volume(self, value: int) -> None:
        self.volume_slider.setToolTip(f"{int(value)}%")
        try:
            self.player.audio_set_volume(int(value))
        except Exception:
            pass

    def _seek_rel(self, delta_ms: int) -> None:
        try:
            cur = int(self.player.get_time() or 0)
            self.player.set_time(max(0, cur + delta_ms))
        except Exception:
            pass

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Space"), self, activated=self.toggle_play)
        QShortcut(QKeySequence("Ctrl+Right"), self, activated=self.play_next)
        QShortcut(QKeySequence("Ctrl+Left"), self, activated=self.play_previous)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search.setFocus)
        QShortcut(QKeySequence("Left"), self, activated=lambda: self._seek_rel(-5000))
        QShortcut(QKeySequence("Right"), self, activated=lambda: self._seek_rel(5000))

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            if self.track_list.count() > 0:
                row = self.track_list.currentRow()
                if row < 0:
                    row = 0
                row = row - 1 if event.key() == Qt.Key.Key_Up else row + 1
                row = max(0, min(row, self.track_list.count() - 1))
                self.track_list.setCurrentRow(row)
                self.track_list.scrollToItem(self.track_list.item(row), QAbstractItemView.ScrollHint.PositionAtCenter)
                event.accept()
                return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self.track_list.currentItem()
            if item and item.flags() != Qt.ItemFlag.NoItemFlags:
                self.play_selected(item)
                event.accept()
                return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if self._current_track is not None:
            try:
                pos = int(self.player.get_time() or 0)
            except Exception:
                pos = 0
            self._save_state(self._current_track.path, pos, was_playing=bool(self.player.is_playing()))
        super().closeEvent(event)

    def _sync_mini_player(self) -> None:
        # Mini-player disabled.
        return

    def _place_mini_player(self) -> None:
        # Mini-player disabled.
        return

    def _update_progress(self) -> None:
        if self.player is None:
            return

        is_playing = self.player.is_playing()
        self.play.setText("⏸" if is_playing else "▶")
        self.waveform.set_active(bool(is_playing))

        try:
            length = int(self.player.get_length() or 0)
            pos = int(self.player.get_time() or 0)
        except Exception:
            return

        if length > 0:
            self.slider.setRange(0, length)
            self.total.setText(format_time(length))

        if not self._user_seeking and length > 0:
            self.slider.setValue(pos)
        self.elapsed.setText(format_time(pos))
        if self._current_track is not None and abs(pos - self._last_saved_state_pos) >= 5000:
            self._save_state(self._current_track.path, pos, was_playing=bool(is_playing))
            self._last_saved_state_pos = pos

        # mini-player disabled

    # (Queue playback methods are defined earlier.)


def run() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("kush-music-player")
    app.setDesktopFileName("kush-music-player")
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))
    win = PremiumMusicPlayer()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()

