# 🎧 Kush's Music Player

A **premium desktop music player** built with **Python, PyQt6, and VLC** — designed to feel fast, modern, and intelligent. Inspired by Spotify, built for Linux.

---

## ✨ Features

### 🎵 Core Playback
- Play local MP3 files
- Smooth playback powered by VLC
- Seek bar, volume control, next/previous
- Album art display (embedded ID3 tags)
- Per-track thumbnail in the song list

### 📚 Library & Playlists
- Folder-based music library with automatic scanning
- Custom playlists (create, rename, delete)
- ❤️ Liked Songs (persistent across sessions)
- 🕒 Recently Played (auto-tracked)
- 🔥 Most Played (auto-generated from play counts)

### 🧠 Smart Features
- 🔁 Auto-play — continues intelligently after each track
- 📊 Play count tracking per song
- Smart queue system — Play Next, drag to reorder
- Session restore — resumes your last track and position on startup

### 🔍 Search & Sorting
- Search by title, artist, album, or filename
- Highlighted search matches in results
- Sort by Name, Recently Added, Most Played, or Liked First

### 🎨 UI / UX
- Glassmorphism dark design
- Smooth fade transitions between tracks
- Animated waveform visualizer while playing
- Album art thumbnail per track row
- Column headers in track list
- Clean single-highlight active track
- Subtle hover effect on track rows
- Status feedback messages

### ⚙️ Settings
- Default volume
- Auto-play toggle
- Persistent configuration saved locally

---

## 🛠️ Tech Stack

| Library | Purpose |
|---|---|
| Python 3 | Core language |
| PyQt6 | UI framework |
| python-vlc | Audio playback via libVLC |
| mutagen | MP3 metadata & album art |

---

## 🐧 Installation — Arch Linux

```bash
sudo pacman -S vlc python-pyqt6 python-mutagen
git clone https://github.com/shahkushsudo/music-player.git
cd music-player
pip install python-vlc --break-system-packages
python premium_player.py
```

---

## 🐧 Installation — Other Linux / macOS

```bash
git clone https://github.com/shahkushsudo/music-player.git
cd music-player
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python premium_player.py
```

---

## ⌨️ Keyboard Shortcuts

| Key | Action |
|---|---|
| `Space` | Play / Pause |
| `Ctrl + →` | Next track |
| `Ctrl + ←` | Previous track |
| `↑ / ↓` | Navigate track list |
| `Enter` | Play selected track |
| `Ctrl + F` | Focus search bar |
| `Left` | Seek back 5 seconds |
| `Right` | Seek forward 5 seconds |
| `Escape` | Clear search |
| `Delete` | Remove from queue |

---

## 📁 Data Storage

All app data is stored locally at `~/.local/share/music-player/`

---

## 👨‍💻 Author

**Kush** — [@shahkushsudo](https://github.com/shahkushsudo)

---

## ⭐ Support

If you like this project, give it a ⭐ on GitHub!
