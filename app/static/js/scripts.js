// FileSync JS helpers (modernized with ES6+ syntax)
(() => {
    const doc = window.document || {};
    const htmlEl = doc.documentElement || {};
    const htmlDataset = htmlEl.dataset || {};
    const runtimeConfig = window.APP_CONFIG || {};
    let socketInstance = null;

    const normalizeScriptRoot = (value) => {
        if (!value || value === '/') {
            return '';
        }
        return value.replace(/\/+$/, '');
    };

    const scriptRoot = normalizeScriptRoot(runtimeConfig.scriptRoot || htmlDataset.scriptRoot || '');
    const isAbsoluteUrl = (value = '') => /^https?:\/\//i.test(value) || value.indexOf('//') === 0;

    const resolveUrl = (path = '') => {
        if (!path) {
            return scriptRoot || '/';
        }
        if (isAbsoluteUrl(path)) {
            return path;
        }
        const normalized = path.charAt(0) === '/' ? path : `/${path}`;
        return scriptRoot ? `${scriptRoot}${normalized}` : normalized;
    };

    const fetchJson = (path, options = {}) =>
        fetch(resolveUrl(path), options).then((res) => {
            if (!res.ok) {
                const error = new Error(`HTTP ${res.status}`);
                error.response = res;
                throw error;
            }
            return res.json();
        });

    const getSyncSocket = () => {
        if (socketInstance) {
            return socketInstance;
        }
        if (typeof window.io !== 'function') {
            console.error('Socket.IO client is not available.');
            return null;
        }
        socketInstance = window.io({
            path: resolveUrl('/socket.io'),
        });
        return socketInstance;
    };

    window.FileSyncApp = {
        resolveUrl,
        fetchJson,
        getSyncSocket,
        routes: runtimeConfig.routes || {},
    };
})();

// Alpine statusBadge component (client-side polling/rendering)
window.statusBadge = () => {
    const app = window.FileSyncApp || {};
    const routes = app.routes || {};
    const endpoint = routes.serverStatusJson || '/server/status.json';

    const fetchStatusData = () => {
        if (typeof app.fetchJson === 'function') {
            return app.fetchJson(endpoint, { cache: 'no-store' });
        }
        const url = typeof app.resolveUrl === 'function' ? app.resolveUrl(endpoint) : endpoint;
        return fetch(url, { cache: 'no-store' }).then((res) => {
            if (!res.ok) {
                throw new Error(`HTTP ${res.status}`);
            }
            return res.json();
        });
    };

    return {
        state: '로딩...',
        detail: '서버 응답 대기 중',
        badgeClass: 'bg-slate-800 text-slate-200 border-slate-500/60',
        dotClass: 'bg-slate-300',
        intervalId: null,

        fetchStatus() {
            return fetchStatusData()
                .then((payload) => {
                    this.state = payload.state || 'UNKNOWN';
                    this.detail = payload.detail || '';
                    if (payload.tone === 'online') {
                        this.badgeClass = 'bg-emerald-900/30 text-emerald-100 border-emerald-500/50';
                        this.dotClass = 'w-2 h-2 rounded-full animate-pulse bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.7)]';
                    } else if (payload.tone === 'idle') {
                        this.badgeClass = 'bg-amber-900/30 text-amber-100 border-amber-500/40';
                        this.dotClass = 'w-2 h-2 rounded-full animate-pulse bg-amber-300 shadow-[0_0_8px_rgba(251,191,36,0.6)]';
                    } else {
                        this.badgeClass = 'bg-slate-800 text-slate-200 border-slate-500/60';
                        this.dotClass = 'w-2 h-2 rounded-full animate-pulse bg-slate-300';
                    }
                    if (this.$el) {
                        this.$el.className = `px-3 py-1.5 rounded-full text-xs font-semibold flex items-center gap-2 border transition-colors duration-200 ${this.badgeClass}`;
                    }
                })
                .catch(() => {
                    this.state = '오프라인';
                    this.detail = '서버와 통신할 수 없음';
                    this.badgeClass = 'bg-red-900/40 text-red-100 border-red-500/60';
                    this.dotClass = 'w-2 h-2 rounded-full animate-pulse bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.8)]';
                    if (this.$el) {
                        this.$el.className = `px-3 py-1.5 rounded-full text-xs font-semibold flex items-center gap-2 border transition-colors duration-200 ${this.badgeClass}`;
                    }
                });
        },

        start() {
            this.$el = this.$el || document.getElementById('system-status-badge');
            this.fetchStatus();
            this.intervalId = setInterval(() => this.fetchStatus(), 5000);
        },

        stop() {
            if (this.intervalId) {
                clearInterval(this.intervalId);
            }
        },
    };
};

// Alpine sync status panel (per configuration) - WebSocket driven
window.syncStatusPanel = (options) => {
    const app = window.FileSyncApp || {};

    return {
        configId: options.configId,
        isRunning: Boolean(options.initialRunning),
        stateLabel: '',
        details: '',
        currentFile: '',
        progressPercent: 0,
        lastSyncTime: '',
        updatedAt: '',
        busy: false,

        init() {
            this.applyStatus(options.initialStatus || {});
            this.bindSocket();
        },

        bindSocket() {
            const socket = typeof app.getSyncSocket === 'function' ? app.getSyncSocket() : null;
            if (!socket) {
                this.details = '실시간 연결을 초기화할 수 없습니다.';
                return;
            }
            socket.on('sync_update', (payload) => {
                if (!payload || payload.config_id !== this.configId) {
                    return;
                }
                this.isRunning = Boolean(payload.is_running);
                this.applyStatus(payload.status || {});
            });
        },

        applyStatus(status) {
            const payload = status || {};
            this.stateLabel = payload.state || (this.isRunning ? 'RUNNING' : 'STOPPED');
            this.details = payload.details || '';
            this.currentFile = payload.current_file || '';
            const percent = Number(payload.progress_percent);
            this.progressPercent = Number.isFinite(percent) ? Math.min(100, Math.max(0, percent)) : 0;
            this.lastSyncTime = payload.last_sync_time || '';
            this.updatedAt = payload.updated_at || '';
        },

        startSync() {
            this._command('start');
        },

        stopSync() {
            this._command('stop');
        },

        _command(action) {
            if (this.busy) {
                return;
            }
            this.busy = true;
            const endpoint = `/filesync/${action}/${this.configId}`;
            const requestUrl = typeof app.resolveUrl === 'function' ? app.resolveUrl(endpoint) : endpoint;
            fetch(requestUrl, {
                method: 'POST',
                headers: {
                    Accept: 'application/json',
                },
            })
                .then((res) => {
                    if (!res.ok) {
                        throw new Error(`HTTP ${res.status}`);
                    }
                })
                .catch(() => {
                    this.details = action === 'start' ? '동기화를 시작할 수 없습니다.' : '동기화를 중지할 수 없습니다.';
                })
                .finally(() => {
                    this.busy = false;
                });
        },

        get progressLabel() {
            return `${Math.round(this.progressPercent)}% complete`;
        },

        get progressVisible() {
            return this.isRunning || (this.stateLabel && this.stateLabel !== 'IDLE') || this.progressPercent > 0;
        },
    };
};
