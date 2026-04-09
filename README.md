# 🎧 Kush's Music Player

A **premium desktop music player** built with **Python, PyQt6, and VLC**, designed to feel fast, modern, and intelligent — inspired by Spotify.

---

## ✨ Features

### 🎵 Core Playback

* Play local music files (MP3)
* Smooth playback powered by VLC
* Seek, volume, next/previous controls

### 📚 Library & Playlists

* Folder-based music library
* Custom playlists
* ❤️ Liked Songs (persistent)
* 🕒 Recently Played
* 🔥 Most Played (auto-generated)

### 🧠 Smart Features

* 🔁 Auto-play (continues music intelligently)
* 📊 Play count tracking
* Smart queue system (Play Next, drag reorder)
* Session restore (resume last track + position)

### 🔍 Search & Sorting

* Search by title, artist, album, filename
* Highlighted matches
* Sort by:

  * Name (A–Z)
  * Recently Added
  * Most Played
  * Liked First

### 🎨 UI / UX

* Modern glassmorphism design
* Smooth transitions & animations
* Hover interactions (play indicator, like button)
* Status feedback messages
* Keyboard shortcuts support

### ⚙️ Settings

* Default volume
* Auto-play toggle
* Persistent configuration

---

## 🖼️ Preview

> *(Add screenshots here later for best impact)*

---

## 🛠️ Tech Stack

* **Python 3**
* **PyQt6** (UI)
* **python-vlc** (audio playback)
* **mutagen** (metadata & tags)

---

## ⚙️ Installation

```bash
git clone https://github.com/shahkushsudo/music-player.git
cd music-player

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

---

## ▶️ Run

```bash
python premium_player.py
```

---

## 📁 Data Storage

App data is stored locally:

```
~/.local/share/music-player/
```

Includes:

* playlists.json
* queue.json
* liked.json
* recent.json
* stats.json
* session.json
* settings.json

---

## ⌨️ Keyboard Shortcuts

| Key      | Action          |
| -------- | --------------- |
| Space    | Play / Pause    |
| Ctrl + → | Next track      |
| Ctrl + ← | Previous track  |
| ↑ / ↓    | Navigate tracks |
| Enter    | Play selected   |
| Ctrl + F | Focus search    |

---


## 👨‍💻 Author

**Kush (shahkushsudo)**
GitHub: https://github.com/shahkushsudo

---

## ⭐ Support

If you like this project, consider giving it a ⭐ on GitHub!
