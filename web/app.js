const LS_PREFIX = 'kushmusic_';

class MusicPlayer {
    constructor() {
        this.files = new Map(); // filename -> File object
        this.library = []; // Array of song metadata objects
        this.displayedLibrary = []; // Array of sorted/filtered song metadata
        this.queue = []; // Array of up-next filenames
        this.context = []; // Current playlist context (filenames)
        this.currentIndex = -1; // Index in context

        this.audio = new Audio();
        this.audio.autoplay = false;

        this.globalMeta = JSON.parse(localStorage.getItem(LS_PREFIX + 'metadata')) || {};
        // { filename: { liked: boolean, playCount: number, addedAt: timestamp } }

        this.session = JSON.parse(localStorage.getItem(LS_PREFIX + 'session')) || {
            volume: 1,
            isShuffle: false,
            isRepeat: false,
            lastFilename: null,
            lastTime: 0
        };

        this.audio.volume = this.session.volume;
        this.isShuffle = this.session.isShuffle;
        this.isRepeat = this.session.isRepeat;

        this.currentSort = 'recently_added';
        this.currentSearch = '';

        this.initDOM();
        this.initEvents();
        this.updatePlayerControls();
    }

    initDOM() {
        this.el = {
            addMusicBtn: document.getElementById('addMusicBtn'),
            fileInput: document.getElementById('fileInput'),
            sidebarList: document.getElementById('sidebarList'),
            likedSidebarList: document.getElementById('likedSidebarList'),
            mainSongList: document.getElementById('mainSongList'),
            queueList: document.getElementById('queueList'),
            queueCount: document.getElementById('queueCount'),

            searchInput: document.getElementById('searchInput'),
            sortSelect: document.getElementById('sortSelect'),

            playerArt: document.getElementById('playerArt'),
            playerTitle: document.getElementById('playerTitle'),
            playerArtist: document.getElementById('playerArtist'),

            btnPrev: document.getElementById('btnPrev'),
            btnPlay: document.getElementById('btnPlay'),
            btnNext: document.getElementById('btnNext'),
            btnShuffle: document.getElementById('btnShuffle'),
            btnRepeat: document.getElementById('btnRepeat'),

            currentTime: document.getElementById('currentTime'),
            totalTime: document.getElementById('totalTime'),
            seekBar: document.getElementById('seekBar'),
            seekProgress: document.getElementById('seekProgress'),

            volumeSlider: document.getElementById('volumeSlider'),
            volumeProgress: document.getElementById('volumeProgress'),

            visualizer: document.getElementById('visualizer'),
            contextMenu: document.getElementById('contextMenu')
        };

        this.el.volumeSlider.value = this.session.volume * 100;
        this.updateVolumeUI();
    }

    initEvents() {
        this.el.addMusicBtn.addEventListener('click', () => this.el.fileInput.click());
        this.el.fileInput.addEventListener('change', (e) => this.handleFilesAdded(e.target.files));

        this.el.searchInput.addEventListener('input', (e) => {
            this.currentSearch = e.target.value.toLowerCase();
            this.renderLibrary();
        });

        this.el.sortSelect.addEventListener('change', (e) => {
            this.currentSort = e.target.value;
            this.renderLibrary();
        });

        this.el.btnPlay.addEventListener('click', () => this.togglePlay());
        this.el.btnPrev.addEventListener('click', () => this.playPrevious());
        this.el.btnNext.addEventListener('click', () => this.playNext());

        this.el.btnShuffle.addEventListener('click', () => {
            this.isShuffle = !this.isShuffle;
            this.session.isShuffle = this.isShuffle;
            this.saveSession();
            this.updatePlayerControls();
            this.showToast(this.isShuffle ? 'Shuffle enabled' : 'Shuffle disabled');
        });

        this.el.btnRepeat.addEventListener('click', () => {
            this.isRepeat = !this.isRepeat;
            this.session.isRepeat = this.isRepeat;
            this.saveSession();
            this.updatePlayerControls();
            this.showToast(this.isRepeat ? 'Repeat enabled' : 'Repeat disabled');
        });

        this.audio.addEventListener('timeupdate', () => this.updateSeekBar());
        this.audio.addEventListener('ended', () => this.handleSongEnd());
        this.audio.addEventListener('loadedmetadata', () => {
            this.el.totalTime.textContent = this.formatTime(this.audio.duration);
        });

        this.el.seekBar.addEventListener('click', (e) => {
            if (!this.audio.duration) return;
            const rect = this.el.seekBar.getBoundingClientRect();
            const pos = (e.clientX - rect.left) / rect.width;
            this.audio.currentTime = pos * this.audio.duration;
        });

        this.el.volumeSlider.addEventListener('input', (e) => {
            this.audio.volume = e.target.value / 100;
            this.session.volume = this.audio.volume;
            this.updateVolumeUI();
            this.saveSession();
        });

        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT') return;
            if (e.code === 'Space') { e.preventDefault(); this.togglePlay(); }
            if (e.code === 'ArrowLeft') {
                e.preventDefault();
                if (e.ctrlKey) {
                    this.playPrevious();
                } else {
                    this.audio.currentTime = Math.max(0, this.audio.currentTime - 5);
                }
            }
            if (e.code === 'ArrowRight') {
                e.preventDefault();
                if (e.ctrlKey) {
                    this.playNext();
                } else {
                    this.audio.currentTime = Math.min(this.audio.duration || 0, this.audio.currentTime + 5);
                }
            }
            if (e.ctrlKey && e.code === 'KeyF') { e.preventDefault(); this.el.searchInput.focus(); }
            if (e.code === 'Escape' && document.activeElement === this.el.searchInput) {
                this.el.searchInput.value = '';
                this.currentSearch = '';
                this.renderLibrary();
                this.el.searchInput.blur();
            }
        });

        document.addEventListener('click', (e) => {
            if (!e.target.closest('#contextMenu')) {
                this.hideContextMenu();
            }
        });

        window.addEventListener('beforeunload', () => {
            if (this.currentSong) {
                this.session.lastFilename = this.currentSong.filename;
                this.session.lastTime = this.audio.currentTime;
                this.saveSession();
            }
        });

        let dragCounter = 0;

        document.addEventListener('dragenter', (e) => {
            e.preventDefault();
            dragCounter++;
            document.getElementById('dragOverlay').classList.add('active');
        });

        document.addEventListener('dragleave', (e) => {
            e.preventDefault();
            dragCounter--;
            if (dragCounter === 0) {
                document.getElementById('dragOverlay').classList.remove('active');
            }
        });

        document.addEventListener('dragover', (e) => {
            e.preventDefault();
        });

        document.addEventListener('drop', (e) => {
            e.preventDefault();
            dragCounter = 0;
            document.getElementById('dragOverlay').classList.remove('active');
            const files = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.mp3'));
            if (files.length > 0) {
                this.handleFilesAdded(files);
            } else {
                this.showToast('Only MP3 files are supported');
            }
        });
    }

    async handleFilesAdded(fileList) {
        let addedCount = 0;
        for (let file of fileList) {
            if (this.files.has(file.name)) continue;
            this.files.set(file.name, file);

            if (!this.globalMeta[file.name]) {
                this.globalMeta[file.name] = { liked: false, playCount: 0, addedAt: Date.now() };
            }

            try {
                const metadata = await this.extractMetadata(file);
                this.library.push(metadata);
                addedCount++;
            } catch (err) {
                console.error('Failed to parse tags for', file.name, err);
                this.library.push({
                    filename: file.name,
                    title: file.name.replace(/\.[^/.]+$/, ""),
                    artist: 'Unknown Artist',
                    albumArt: null,
                    duration: 0
                });
                addedCount++;
            }
        }

        if (addedCount > 0) {
            this.saveGlobalMeta();
            this.renderLibrary();
            this.showToast(`Added ${addedCount} songs to library`);

            // Restore session if we just loaded the previously playing file
            if (this.session.lastFilename && !this.currentSong) {
                const song = this.library.find(s => s.filename === this.session.lastFilename);
                if (song) {
                    this.loadSong(song, false);
                    this.audio.currentTime = this.session.lastTime || 0;
                }
            }
        }
    }

    extractMetadata(file) {
        return new Promise((resolve, reject) => {
            if (!window.jsmediatags) {
                return reject("jsmediatags not loaded");
            }
            window.jsmediatags.read(file, {
                onSuccess: (tag) => {
                    const tags = tag.tags;
                    let albumArt = null;
                    if (tags.picture) {
                        const { data, format } = tags.picture;
                        const base64String = data.reduce((acc, byte) => acc + String.fromCharCode(byte), '');
                        albumArt = `data:${format};base64,${window.btoa(base64String)}`;
                    }
                    resolve({
                        filename: file.name,
                        title: tags.title || file.name.replace(/\.[^/.]+$/, ""),
                        artist: tags.artist || 'Unknown Artist',
                        albumArt: albumArt,
                        duration: 0
                    });
                },
                onError: (error) => {
                    reject(error);
                }
            });
        });
    }

    renderLibrary() {
        this.displayedLibrary = this.library.filter(song => {
            if (!this.currentSearch) return true;
            return song.title.toLowerCase().includes(this.currentSearch) ||
                song.artist.toLowerCase().includes(this.currentSearch);
        });

        this.displayedLibrary.sort((a, b) => {
            const metaA = this.globalMeta[a.filename];
            const metaB = this.globalMeta[b.filename];
            if (this.currentSort === 'recently_added') {
                return metaB.addedAt - metaA.addedAt;
            } else if (this.currentSort === 'name_az') {
                return a.title.localeCompare(b.title);
            } else if (this.currentSort === 'most_played') {
                return metaB.playCount - metaA.playCount;
            }
            return 0;
        });

        this.el.mainSongList.innerHTML = '';
        this.el.sidebarList.innerHTML = '';
        this.el.likedSidebarList.innerHTML = '';

        this.displayedLibrary.forEach((song, index) => {
            const meta = this.globalMeta[song.filename];
            const isActive = this.currentSong && this.currentSong.filename === song.filename;

            // Main list row
            const row = document.createElement('div');
            row.className = `song-row ${isActive ? 'active' : ''}`;
            row.innerHTML = `
                <div class="song-col col-hash">
                    ${isActive && this.isPlaying ? '<span class="icon-play">▶</span>' : index + 1}
                </div>
                <div class="song-col col-title">
                    <div class="song-art" style="${song.albumArt ? `background-image: url('${song.albumArt}')` : ''}">
                        ${!song.albumArt ? '♫' : ''}
                    </div>
                    <div>
                        <div class="song-name">${song.title}</div>
                    </div>
                </div>
                <div class="song-col col-artist">${song.artist}</div>
                <div class="song-col col-duration">
                    <button class="heart-btn ${meta.liked ? 'liked' : ''}" title="${meta.liked ? 'Unlike' : 'Like'}">
                        ${meta.liked ? '♥' : '♡'}
                    </button>
                    <span class="duration-label">${song.duration ? this.formatTime(song.duration) : '--:--'}</span>
                    ${meta.playCount > 0 ? `<span class="play-count">▶ ${meta.playCount}</span>` : ''}
                </div>
            `;

            row.addEventListener('click', (e) => {
                if (e.target.closest('.heart-btn')) {
                    this.toggleLike(song.filename);
                    return;
                }
                document.querySelectorAll('.song-row').forEach(r => r.classList.remove('selected'));
                row.classList.add('selected');
            });

            row.addEventListener('dblclick', (e) => {
                if (!e.target.closest('.heart-btn')) {
                    this.playFromLibrary(index);
                }
            });

            row.addEventListener('contextmenu', (e) => this.showContextMenu(e, song));

            this.el.mainSongList.appendChild(row);

            // Sidebar item
            const sbItem = this.createSidebarItem(song, isActive);
            this.el.sidebarList.appendChild(sbItem);

            // Liked item if liked
            if (meta.liked) {
                const likedItem = this.createSidebarItem(song, isActive);
                this.el.likedSidebarList.appendChild(likedItem);
            }
        });

        const emptyState = document.getElementById('emptyState');
        const libraryCount = document.getElementById('libraryCount');
        if (this.displayedLibrary.length === 0) {
            emptyState.style.display = 'flex';
            this.el.mainSongList.style.display = 'none';
            libraryCount.textContent = '';
        } else {
            emptyState.style.display = 'none';
            this.el.mainSongList.style.display = 'block';
            libraryCount.textContent = `Library • ${this.displayedLibrary.length} song${this.displayedLibrary.length !== 1 ? 's' : ''}`;
        }
    }

    createSidebarItem(song, isActive) {
        const item = document.createElement('div');
        item.className = `sidebar-item ${isActive ? 'active' : ''}`;
        item.innerHTML = `
            <div class="sidebar-art" style="${song.albumArt ? `background-image: url('${song.albumArt}')` : ''}">
                ${!song.albumArt ? '♫' : ''}
            </div>
            <div class="sidebar-info">
                <div class="sidebar-title">${song.title}</div>
                <div class="sidebar-artist">${song.artist}</div>
            </div>
        `;
        item.addEventListener('click', () => {
            const idx = this.displayedLibrary.findIndex(s => s.filename === song.filename);
            if (idx !== -1) this.playFromLibrary(idx);
        });
        return item;
    }

    renderQueue() {
        this.el.queueList.innerHTML = '';
        this.el.queueCount.textContent = `${this.queue.length} song${this.queue.length !== 1 ? 's' : ''}`;
        if (this.queue.length === 0) {
            const empty = document.createElement('div');
            empty.style.cssText = 'text-align:center;color:rgba(255,255,255,0.25);font-size:13px;padding:24px 0;';
            empty.textContent = 'Queue is empty';
            this.el.queueList.appendChild(empty);
            return;
        }
        this.queue.forEach((filename, i) => {
            const song = this.library.find(s => s.filename === filename);
            if (!song) return;
            const item = document.createElement('div');
            item.className = 'queue-item';
            item.innerHTML = `
                <div class="sidebar-art" style="${song.albumArt ? `background-image:url('${song.albumArt}')` : ''}">
                    ${!song.albumArt ? '♫' : ''}
                </div>
                <div class="queue-info">
                    <div class="queue-title">${song.title}</div>
                    <div class="queue-artist">${song.artist}</div>
                </div>
                <button class="queue-remove" title="Remove">✕</button>
            `;
            item.querySelector('.queue-remove').addEventListener('click', (e) => {
                e.stopPropagation();
                this.queue.splice(i, 1);
                this.renderQueue();
                this.showToast('Removed from queue');
            });
            item.addEventListener('click', (e) => {
                if (e.target.closest('.queue-remove')) return;
                this.queue.splice(i, 1);
                this.renderQueue();
                this.loadSong(song, true);
            });
            this.el.queueList.appendChild(item);
        });
    }

    playFromLibrary(index) {
        this.context = this.displayedLibrary.map(s => s.filename);
        this.currentIndex = index;
        this.queue = [];
        this.renderQueue();
        this.loadSong(this.displayedLibrary[index], true);
    }

    loadSong(song, autoPlay = true) {
        if (!song) return;
        this.currentSong = song;
        const file = this.files.get(song.filename);
        if (!file) {
            this.showToast('Please re-add folder to play this track');
            return;
        }

        const url = URL.createObjectURL(file);
        this.audio.src = url;
        this.audio.addEventListener('loadedmetadata', () => {
            song.duration = this.audio.duration;
            this.renderLibrary();
        }, { once: true });

        // Update UI
        this.el.playerTitle.textContent = song.title;
        this.el.playerArtist.textContent = song.artist;
        if (song.albumArt) {
            this.el.playerArt.style.cssText = `background-image: url('${song.albumArt}'); background-size: cover; background-position: center; font-size: 0;`;
            this.el.playerArt.textContent = '';
        } else {
            this.el.playerArt.style.cssText = 'background-image: none; font-size: 20px;';
            this.el.playerArt.textContent = '♫';
        }

        const npPanel = document.getElementById('nowPlayingPanel');
        const npTitle = document.getElementById('npTitle');
        const npArtist = document.getElementById('npArtist');
        const npArt = document.getElementById('npArt');
        if (npPanel) {
            npPanel.style.display = 'block';
            npTitle.textContent = song.title;
            npArtist.textContent = song.artist;
            if (song.albumArt) {
                npArt.style.cssText = `background-image: url('${song.albumArt}'); background-size: cover; background-position: center; font-size: 0;`;
                npArt.textContent = '';
            } else {
                npArt.style.cssText = 'background-image: none; font-size: 16px;';
                npArt.textContent = '♫';
            }
        }

        this.renderLibrary();
        setTimeout(() => {
            const activeRow = this.el.mainSongList.querySelector('.song-row.active');
            if (activeRow) {
                activeRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }, 50);

        if (autoPlay) {
            this.audio.play();
            this.isPlaying = true;
            this.incrementPlayCount(song.filename);
        } else {
            this.isPlaying = false;
        }
        this.updatePlayerControls();
    }

    togglePlay() {
        if (!this.currentSong && this.displayedLibrary.length > 0) {
            this.playFromLibrary(0);
            return;
        }
        if (!this.audio.src) return;

        if (this.isPlaying) {
            this.audio.pause();
        } else {
            this.audio.play();
        }
        this.isPlaying = !this.isPlaying;
        this.updatePlayerControls();
        this.renderLibrary();
    }

    playNext() {
        if (this.queue.length > 0) {
            const nextFilename = this.queue.shift();
            this.renderQueue();
            const song = this.library.find(s => s.filename === nextFilename);
            if (song) this.loadSong(song, true);
            return;
        }

        if (this.context.length === 0) return;

        if (this.isShuffle) {
            this.currentIndex = Math.floor(Math.random() * this.context.length);
        } else {
            this.currentIndex++;
            if (this.currentIndex >= this.context.length) {
                this.currentIndex = 0; // wrap around
                if (!this.isRepeat) {
                    this.loadSong(this.library.find(s => s.filename === this.context[0]), false);
                    return;
                }
            }
        }
        const nextSong = this.library.find(s => s.filename === this.context[this.currentIndex]);
        if (nextSong) this.loadSong(nextSong, true);
    }

    playPrevious() {
        if (this.audio.currentTime > 3) {
            this.audio.currentTime = 0;
            return;
        }

        if (this.context.length === 0) return;

        this.currentIndex--;
        if (this.currentIndex < 0) {
            this.currentIndex = this.context.length - 1;
        }
        const prevSong = this.library.find(s => s.filename === this.context[this.currentIndex]);
        if (prevSong) this.loadSong(prevSong, true);
    }

    handleSongEnd() {
        if (this.isRepeat && this.queue.length === 0) {
            this.audio.currentTime = 0;
            this.audio.play();
        } else {
            this.playNext();
        }
    }

    updatePlayerControls() {
        const playIcon = document.getElementById('playIcon');
        if (playIcon) {
            playIcon.innerHTML = this.isPlaying
                ? '<rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect>'
                : '<polygon points="5 3 19 12 5 21 5 3"></polygon>';
        }
        this.el.btnShuffle.classList.toggle('active-control', this.isShuffle);
        this.el.btnRepeat.classList.toggle('active-control', this.isRepeat);
        this.el.visualizer.style.display = this.isPlaying ? 'flex' : 'none';
        if (this.isPlaying) {
            this.el.btnPlay.classList.add('playing');
        } else {
            this.el.btnPlay.classList.remove('playing');
        }
    }

    updateSeekBar() {
        if (!this.audio.duration) return;
        this.el.currentTime.textContent = this.formatTime(this.audio.currentTime);
        const percent = (this.audio.currentTime / this.audio.duration) * 100;
        this.el.seekProgress.style.width = `${percent}%`;
    }

    updateVolumeUI() {
        this.el.volumeProgress.style.width = `${this.el.volumeSlider.value}%`;
    }

    formatTime(seconds) {
        if (isNaN(seconds)) return '0:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    toggleLike(filename) {
        if (this.globalMeta[filename]) {
            this.globalMeta[filename].liked = !this.globalMeta[filename].liked;
            this.saveGlobalMeta();
            this.renderLibrary();
        }
    }

    incrementPlayCount(filename) {
        if (this.globalMeta[filename]) {
            this.globalMeta[filename].playCount = (this.globalMeta[filename].playCount || 0) + 1;
            this.saveGlobalMeta();
        }
    }

    saveGlobalMeta() {
        localStorage.setItem(LS_PREFIX + 'metadata', JSON.stringify(this.globalMeta));
    }

    saveSession() {
        localStorage.setItem(LS_PREFIX + 'session', JSON.stringify(this.session));
    }

    showToast(msg) {
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.textContent = msg;
        document.body.appendChild(toast);

        setTimeout(() => toast.style.opacity = '1', 10);
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 2000);
    }

    showContextMenu(e, song) {
        e.preventDefault();
        const menu = this.el.contextMenu;
        menu.style.display = 'block';

        let x = e.clientX;
        let y = e.clientY;
        if (x + menu.offsetWidth > window.innerWidth) x -= menu.offsetWidth;
        if (y + menu.offsetHeight > window.innerHeight) y -= menu.offsetHeight;

        menu.style.left = `${x}px`;
        menu.style.top = `${y}px`;

        const playNextBtn = document.getElementById('cmPlayNext');
        const addQueueBtn = document.getElementById('cmAddQueue');

        playNextBtn.onclick = () => {
            this.queue.unshift(song.filename);
            this.renderQueue();
            this.showToast('Added to play next');
            this.hideContextMenu();
        };

        addQueueBtn.onclick = () => {
            this.queue.push(song.filename);
            this.renderQueue();
            this.showToast('Added to queue');
            this.hideContextMenu();
        };
    }

    hideContextMenu() {
        this.el.contextMenu.style.display = 'none';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.player = new MusicPlayer();
});
