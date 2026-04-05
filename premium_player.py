from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import vlc
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QIcon, QPixmap
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
    QAbstractButton,
    QInputDialog,
    QGraphicsOpacityEffect,
    QGraphicsBlurEffect,
)


MUSIC_DIR = "/home/kush/Music"
PLAYLIST_FILE = os.path.expanduser("~/.local/share/music-player/playlists.json")
APP_NAME = "Kush's Music"
ICON_PATH = "/home/kush/music-player/assets/icon.png"


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

        # ----- Data -----
        # library[folder] = list[Track]
        self.library: Dict[str, List[Track]] = {}
        self.view_tracks: List[Track] = []
        self.view_base_tracks: List[Track] = []
        self.view_kind: str = "library"  # or "playlist"
        self.current_folder: str = ""
        self.current_playlist_name: Optional[str] = None
        self.playlists: Dict[str, List[str]] = {}  # name -> list[path]

        # ----- Playback state -----
        self.queue: List[Track] = []
        self.history: List[Track] = []
        self.history_pos: int = -1
        self._last_highlighted_path: Optional[str] = None

        # ----- UI -----
        self._build_ui()
        self._load_playlists()
        self._load_music()
        self._apply_styles()
        self._maybe_set_initial_view()

        # Smooth UI animations timer
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self._update_progress)
        self.progress_timer.start(250)

        # Mini-player disabled (user requested no mini-player).
        self.mini_player = None

    def _try_set_icon(self) -> None:
        # Best-effort: if icon exists, set it (never fail startup).
        try:
            if os.path.exists(ICON_PATH):
                icon = QIcon(ICON_PATH)
                self.setWindowIcon(icon)
                QApplication.instance().setWindowIcon(icon)
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

        self.art = QLabel("No Art")
        self.art.setObjectName("art")
        self.art.setFixedSize(250, 250)
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art.setStyleSheet("color: rgba(255,255,255,0.62); font-weight: 650;")

        self.fade_effect = QGraphicsOpacityEffect(self.art)
        self.fade_effect.setOpacity(1.0)
        self.art.setGraphicsEffect(self.fade_effect)

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

        meta.addWidget(self.title)
        meta.addWidget(self.artist)
        meta.addWidget(self.subtitle)

        meta.addStretch(1)

        self.play_controls = QHBoxLayout()
        self.prev = QPushButton("⏮")
        self.play = QPushButton("▶")
        self.next = QPushButton("⏭")
        for b in (self.prev, self.play, self.next):
            b.setObjectName("controlBtn")

        self.prev.clicked.connect(self.play_previous)
        self.play.clicked.connect(self.toggle_play)
        self.next.clicked.connect(self.play_next)

        self.play_controls.addWidget(self.prev)
        self.play_controls.addWidget(self.play)
        self.play_controls.addWidget(self.next)

        meta.addLayout(self.play_controls)

        now_layout.addWidget(self.art)
        now_layout.addLayout(meta, 1)

        main_layout.addWidget(now)

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

        title = QLabel("Queue")
        title.setObjectName("queueTitle")
        queue_layout.addWidget(title)

        self.queue_list = QListWidget()
        self.queue_list.setObjectName("listGlass")
        self.queue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue_list.customContextMenuRequested.connect(self._queue_context_menu)
        self.queue_list.itemDoubleClicked.connect(self.play_queue_item)
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

            QPushButton#controlBtn, QPushButton#primaryBtn, QPushButton#primaryBtnSmall, QPushButton#ghostBtn, QPushButton#ghostBtnSmall {
                border-radius: 16px;
                padding: 10px 14px;
                font-weight: 800;
            }

            QPushButton#controlBtn {
                background: rgba(255,255,255,0.07);
                border: 1px solid rgba(255,255,255,0.10);
                color: #f3f3f5;
                padding: 9px 14px;
                min-width: 52px;
            }
            QPushButton#controlBtn:hover {
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

            QSlider#progress::groove:horizontal {
                height: 10px;
                background: rgba(255,255,255,0.14);
                border-radius: 6px;
            }
            QSlider#progress::handle:horizontal {
                background: #1db954;
                width: 18px;
                margin: -6px 0;
                border-radius: 9px;
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
        for name in sorted(self.playlists.keys()):
            self.playlist_list.addItem(name)

    def _save_playlists(self) -> None:
        safe_write_json(PLAYLIST_FILE, {"version": 2, "playlists": self.playlists})

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

        for t in self.view_tracks:
            item = QListWidgetItem(t.display_name)
            item.setData(Qt.ItemDataRole.UserRole, t.path)
            item.setToolTip(f"{t.title}\n{t.artist}\n{t.album}")
            self.track_list.addItem(item)

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
        add_playlist = menu.addAction("Add to Playlist…")

        action = menu.exec(self.track_list.mapToGlobal(pos))
        if action == add_queue:
            self.enqueue_track(track)
        elif action == add_playlist:
            self._add_track_to_playlist(track)

    def _queue_context_menu(self, pos: QPoint) -> None:
        item = self.queue_list.itemAt(pos)
        if not item:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None:
            return

        menu = QMenu(self)
        remove = menu.addAction("Remove")
        clear = menu.addAction("Clear Queue")
        action = menu.exec(self.queue_list.mapToGlobal(pos))
        if action == remove:
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

    def enqueue_track(self, track: Track) -> None:
        self.queue.append(track)
        self._render_queue_list()

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
        for i, t in enumerate(self.queue):
            item = QListWidgetItem(t.display_name)
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setToolTip(t.path)
            self.queue_list.addItem(item)

    def play_selected(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        track = self._track_by_path(path)
        if not track:
            return
        # Spotify-ish: selecting a song plays it immediately, queue starts fresh.
        self.queue.clear()
        self._render_queue_list()
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
            self._render_queue_list()
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
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None:
            return
        self.play_queue_at(int(idx))

    def play_selected_queue_item(self) -> None:
        item = self.queue_list.currentItem()
        if not item:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None:
            return
        self.play_queue_at(int(idx))

    def play_queue_at(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.queue):
            return

        # Play the selected queue item now, and skip everything before it.
        # Spotify-ish behavior: jumping to an item in the queue skips ahead.
        track = self.queue[idx]
        self.queue = self.queue[idx + 1 :]
        self._render_queue_list()
        self._play_track(track, add_to_history=True, from_queue=True)

    def play_queue_item_safe(self, idx: int) -> None:
        # Backward-compatible alias; keep for any older callers.
        if idx < 0 or idx >= len(self.queue):
            return
        self.play_queue_at(idx)

    def remove_queue_at(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.queue):
            return
        self.queue.pop(idx)
        self._render_queue_list()

    def remove_selected_queue_item(self) -> None:
        item = self.queue_list.currentItem()
        if not item:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None:
            return
        self.remove_queue_at(int(idx))

    def clear_queue(self) -> None:
        self.queue.clear()
        self._render_queue_list()

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
        pix = read_art_pixmap(track.path, size=250)
        if pix:
            self.art.setPixmap(pix)
            self.art.setText("")
        else:
            self.art.setPixmap(QPixmap())
            self.art.setText("No Art")

        # Ensure track highlight is in sync.
        self._sync_highlight_to_current_track()

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

        # mini-player disabled

    # (Queue playback methods are defined earlier.)


def run() -> None:
    app = QApplication(sys.argv)
    win = PremiumMusicPlayer()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()

