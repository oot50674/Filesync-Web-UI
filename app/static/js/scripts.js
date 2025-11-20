// Singleton Socket.IO connection (ES5)
(function () {
    var socketInstance = null;
    window.getSyncSocket = function () {
        if (!socketInstance) {
            if (typeof window.io !== 'function') {
                console.error('Socket.IO client is not available.');
                return null;
            }
            socketInstance = window.io();
        }
        return socketInstance;
    };
})();

// Alpine statusBadge component (client-side polling/rendering)
window.statusBadge = function () {
    return {
        state: '로딩...',
        detail: '서버 응답 대기 중',
        badgeClass: 'bg-slate-800 text-slate-200 border-slate-500/60',
        dotClass: 'bg-slate-300',
        intervalId: null,

        fetchStatus: function () {
            var self = this;
            return fetch('/server/status.json', { cache: 'no-store' })
                .then(function (res) {
                    if (!res.ok) throw new Error('HTTP ' + res.status);
                    return res.json();
                })
                .then(function (j) {
                    self.state = j.state || 'UNKNOWN';
                    self.detail = j.detail || '';
                    if (j.tone === 'online') {
                        self.badgeClass = 'bg-emerald-900/30 text-emerald-100 border-emerald-500/50';
                        self.dotClass = 'w-2 h-2 rounded-full animate-pulse bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.7)]';
                    } else if (j.tone === 'idle') {
                        self.badgeClass = 'bg-amber-900/30 text-amber-100 border-amber-500/40';
                        self.dotClass = 'w-2 h-2 rounded-full animate-pulse bg-amber-300 shadow-[0_0_8px_rgba(251,191,36,0.6)]';
                    } else {
                        self.badgeClass = 'bg-slate-800 text-slate-200 border-slate-500/60';
                        self.dotClass = 'w-2 h-2 rounded-full animate-pulse bg-slate-300';
                    }
                    if (self.$el) {
                        self.$el.className = 'px-3 py-1.5 rounded-full text-xs font-semibold flex items-center gap-2 border transition-colors duration-200 ' + self.badgeClass;
                    }
                })
                .catch(function () {
                    self.state = '오프라인';
                    self.detail = '서버와 통신할 수 없음';
                    self.badgeClass = 'bg-red-900/40 text-red-100 border-red-500/60';
                    self.dotClass = 'w-2 h-2 rounded-full animate-pulse bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.8)]';
                    if (self.$el) {
                        self.$el.className = 'px-3 py-1.5 rounded-full text-xs font-semibold flex items-center gap-2 border transition-colors duration-200 ' + self.badgeClass;
                    }
                });
        },

        start: function () {
            this.$el = this.$el || document.getElementById('system-status-badge');
            this.fetchStatus();
            var self = this;
            this.intervalId = setInterval(function () { self.fetchStatus(); }, 5000);
        },

        stop: function () {
            if (this.intervalId) clearInterval(this.intervalId);
        }
    };
};

// Alpine sync status panel (per configuration) - WebSocket driven
window.syncStatusPanel = function (options) {
    return {
        configId: options.configId,
        isRunning: Boolean(options.initialRunning),
        stateLabel: "",
        details: "",
        currentFile: "",
        progressPercent: 0,
        lastSyncTime: "",
        updatedAt: "",
        busy: false,

        init: function () {
            this.applyStatus(options.initialStatus || {});
            this.bindSocket();
        },

        bindSocket: function () {
            var self = this;
            var socket = window.getSyncSocket();
            if (!socket) {
                self.details = "실시간 연결을 초기화할 수 없습니다.";
                return;
            }
            socket.on('sync_update', function (payload) {
                if (!payload || payload.config_id !== self.configId) {
                    return;
                }
                self.isRunning = Boolean(payload.is_running);
                self.applyStatus(payload.status || {});
            });
        },

        applyStatus: function (status) {
            var payload = status || {};
            this.stateLabel = payload.state || (this.isRunning ? "RUNNING" : "STOPPED");
            this.details = payload.details || "";
            this.currentFile = payload.current_file || "";
            var percent = Number(payload.progress_percent);
            if (!isFinite(percent)) {
                percent = 0;
            }
            this.progressPercent = Math.min(100, Math.max(0, percent));
            this.lastSyncTime = payload.last_sync_time || "";
            this.updatedAt = payload.updated_at || "";
        },

        startSync: function () {
            this._command("start");
        },

        stopSync: function () {
            this._command("stop");
        },

        _command: function (action) {
            var self = this;
            if (self.busy) return;
            self.busy = true;
            fetch('/filesync/' + action + '/' + self.configId, {
                method: "POST",
                headers: {
                    Accept: "application/json"
                }
            })
                .then(function (res) {
                    if (!res.ok) {
                        throw new Error('HTTP ' + res.status);
                    }
                })
                .catch(function () {
                    self.details = action === "start" ? "동기화를 시작할 수 없습니다." : "동기화를 중지할 수 없습니다.";
                })
                .then(function () {
                    self.busy = false;
                });
        },

        get progressLabel() {
            return Math.round(this.progressPercent) + "% complete";
        },

        get progressVisible() {
            return this.isRunning || (this.stateLabel && this.stateLabel !== "IDLE") || this.progressPercent > 0;
        }
    };
};
