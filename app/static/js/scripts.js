// FileSync JS helpers
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
        confirmAndDispatch(el, message, opts = {}) {
            const target = el || document.body;
            const eventName = opts.eventName || 'confirmed';
            const dispatch = () => target && target.dispatchEvent(new Event(eventName, { bubbles: true }));
            const toastConfirm = typeof window.Toast?.confirm === 'function';
            if (toastConfirm) {
                window.Toast.confirm(
                    message || '계속 진행하시겠습니까?',
                    () => dispatch(),
                    () => {},
                    {
                        title: opts.title || '확인 필요',
                        okText: opts.okText || '확인',
                        cancelText: opts.cancelText || '취소',
                        position: 'top-center',
                        duration: 0,
                    },
                );
                return;
            }
            if (window.confirm(message || '계속 진행하시겠습니까?')) {
                dispatch();
            }
        },
        setBadgeOffline() {
            const el = document.getElementById('system-status-badge');
            if (!el) return;
            const dot = el.querySelector('[data-role="dot"]');
            const stateEl = el.querySelector('[data-role="state"]');
            const detailEl = el.querySelector('[data-role="detail"]');
            const badgeClass = 'bg-red-900/40 text-red-100 border-red-500/60';
            const dotClass = 'w-2 h-2 rounded-full animate-pulse bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.8)]';
            el.className = `px-3 py-1.5 rounded-full text-xs font-semibold flex items-center gap-2 border transition-colors duration-200 ${badgeClass}`;
            if (dot) dot.className = `${dotClass}`;
            if (stateEl) stateEl.textContent = '오프라인';
            if (detailEl) detailEl.textContent = '서버 재시작 중';
        },
        handleAfterRequest(message, toastType = 'info', reloadDelay = -1) {
            if (window.Toast && typeof window.Toast[toastType] === 'function') {
                window.Toast[toastType](message, { position: 'top-center' });
            } else {
                alert(message);
            }
            if (reloadDelay > 0) {
                setTimeout(() => window.location.reload(), reloadDelay);
            }
        },
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
    const initialStatus = options.initialStatus || {};

    const formatTimestamp = (str) => {
        if (!str) return '';
        const d = new Date(str.endsWith('Z') || str.includes('+') ? str : str + 'Z');
        const now = new Date();
        const isToday = d.toDateString() === now.toDateString();
        const time = d.toLocaleTimeString('ko-KR', { hour12: false });
        if (isToday) return time;
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${year}-${month}-${day} ${time}`;
    };

    return {
        configId: options.configId,
        isRunning: Boolean(options.initialRunning),
        stateLabel: initialStatus.state || (options.initialRunning ? 'RUNNING' : 'IDLE'),
        details: initialStatus.details || '',
        currentFile: initialStatus.current_file || '',
        progressPercent: Number.isFinite(Number(initialStatus.progress_percent))
            ? Math.min(100, Math.max(0, Number(initialStatus.progress_percent)))
            : 0,
        updatedAt: formatTimestamp(initialStatus.updated_at),
        busy: false,
        pathAlerted: false,

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

            this.updatedAt = formatTimestamp(payload.updated_at);

            // 소스/백업 경로 오류 시 즉시 알림
            const detailText = (this.details || '').toLowerCase();
            const pathError =
                detailText.includes('does not exist or is not a directory') ||
                detailText.includes('경로');
            if (pathError && !this.pathAlerted && typeof window.Toast?.alert === 'function') {
                window.Toast.alert(this.details || '소스/백업 경로를 확인하세요.', {
                    title: '경로 오류',
                    position: 'top-center',
                    duration: 5000,
                });
                this.pathAlerted = true;
            } else if (!pathError) {
                this.pathAlerted = false;
            }
        },

        startSync() {
            this._command('start');
        },

        stopSync() {
            this._command('stop');
        },

        _command(action) {
            if (this.busy) return;
            this.busy = true;
            const endpoint = `/filesync/${action}/${this.configId}`;
            const requestUrl = typeof app.resolveUrl === 'function' ? app.resolveUrl(endpoint) : endpoint;
            fetch(requestUrl, {
            method: 'POST',
            headers: { Accept: 'application/json' },
            })
            .then((res) => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const contentType = res.headers.get('content-type') || '';
                return contentType.includes('application/json') ? res.json() : {};
            })
            .then((payload = {}) => {
                if (payload.status) {
                this.isRunning = Boolean(payload.is_running);
                this.applyStatus(payload.status);
                const detailMsg = (payload.status.details || '').trim();
                const isError = detailMsg && detailMsg.toLowerCase().includes('오류');
                if (isError && typeof window.Toast?.alert === 'function') {
                    window.Toast.alert(detailMsg, { position: 'top-center', duration: 4500 });
                }
                }
            })
            .catch(() => {
                this.details = action === 'start'
                ? '동기화를 시작할 수 없습니다.'
                : '동기화를 중지할 수 없습니다.';
            })
            .finally(() => {
                this.busy = false;
            });
        },

        get progressLabel() {
            return `${Math.round(this.progressPercent)}% complete`;
        },

        get progressVisible() {
            // IDLE 상태에서는 프로그레스 바를 숨기고,
            // 실제로 동기화가 실행 중인 경우에만 표시합니다.
            return this.isRunning && this.stateLabel !== 'IDLE';
        },
    };
};
