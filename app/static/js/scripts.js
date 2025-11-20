// Alpine statusBadge component (client-side polling/rendering)
window.statusBadge = function () {
    return {
        state: '로딩...',
        detail: '서버 응답 대기 중',
        badgeClass: 'bg-slate-800 text-slate-200 border-slate-500/60',
        dotClass: 'bg-slate-300',
        intervalId: null,

        async fetchStatus() {
            try {
                const res = await fetch('/server/status.json', { cache: 'no-store' });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const j = await res.json();
                this.state = j.state || 'UNKNOWN';
                this.detail = j.detail || '';
                if (j.tone === 'online') {
                    this.badgeClass = 'bg-emerald-900/30 text-emerald-100 border-emerald-500/50';
                    this.dotClass = 'w-2 h-2 rounded-full animate-pulse bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.7)]';
                } else if (j.tone === 'idle') {
                    this.badgeClass = 'bg-amber-900/30 text-amber-100 border-amber-500/40';
                    this.dotClass = 'w-2 h-2 rounded-full animate-pulse bg-amber-300 shadow-[0_0_8px_rgba(251,191,36,0.6)]';
                } else {
                    this.badgeClass = 'bg-slate-800 text-slate-200 border-slate-500/60';
                    this.dotClass = 'w-2 h-2 rounded-full animate-pulse bg-slate-300';
                }
                // apply badgeClass
                this.$el && (this.$el.className = 'px-3 py-1.5 rounded-full text-xs font-semibold flex items-center gap-2 border transition-colors duration-200 ' + this.badgeClass);
            } catch (err) {
                // network or timeout
                this.state = '오프라인';
                this.detail = '서버와 통신할 수 없음';
                this.badgeClass = 'bg-red-900/40 text-red-100 border-red-500/60';
                this.dotClass = 'w-2 h-2 rounded-full animate-pulse bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.8)]';
                this.$el && (this.$el.className = 'px-3 py-1.5 rounded-full text-xs font-semibold flex items-center gap-2 border transition-colors duration-200 ' + this.badgeClass);
            }
        },

        start() {
            // bind $el for convenience
            this.$el = this.$el || document.getElementById('system-status-badge');
            this.fetchStatus();
            this.intervalId = setInterval(() => this.fetchStatus(), 5000);
        },

        stop() {
            if (this.intervalId) clearInterval(this.intervalId);
        }
    };
};

// Alpine sync status panel (per configuration)
window.syncStatusPanel = function ({ configId, initialStatus, initialRunning }) {
    return {
        configId,
        isRunning: Boolean(initialRunning),
        stateLabel: "",
        details: "",
        currentFile: "",
        progressPercent: 0,
        lastSyncTime: "",
        updatedAt: "",
        busy: false,
        pollTimer: null,

        init() {
            this.applyStatus(initialStatus || {});
            this.startPolling();
        },

        applyStatus(status) {
            const payload = status || {};
            this.stateLabel = payload.state || (this.isRunning ? "RUNNING" : "STOPPED");
            this.details = payload.details || "";
            this.currentFile = payload.current_file || "";
            const percent = Number(payload.progress_percent ?? 0);
            this.progressPercent = Number.isFinite(percent) ? Math.min(100, Math.max(0, percent)) : 0;
            this.lastSyncTime = payload.last_sync_time || "";
            this.updatedAt = payload.updated_at || "";
        },

        async fetchStatus() {
            try {
                const res = await fetch(`/filesync/status/${this.configId}.json`, { cache: "no-store" });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                this.isRunning = Boolean(data.is_running);
                this.applyStatus(data.status);
            } catch (error) {
                this.details = "상태를 불러오지 못했습니다.";
            }
        },

        startPolling() {
            this.fetchStatus();
            this.pollTimer = setInterval(() => this.fetchStatus(), 2000);
        },

        async startSync() {
            await this._command("start");
        },

        async stopSync() {
            await this._command("stop");
        },

        async _command(action) {
            if (this.busy) return;
            this.busy = true;
            try {
                const res = await fetch(`/filesync/${action}/${this.configId}`, {
                    method: "POST",
                    headers: {
                        Accept: "application/json",
                    },
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                this.isRunning = Boolean(data.is_running);
                this.applyStatus(data.status);
            } catch (error) {
                this.details = action === "start" ? "동기화를 시작할 수 없습니다." : "동기화를 중지할 수 없습니다.";
            } finally {
                this.busy = false;
            }
        },

        get progressLabel() {
            return `${Math.round(this.progressPercent)}% complete`;
        },

        get progressVisible() {
            return this.isRunning || (this.stateLabel && this.stateLabel !== "IDLE") || this.progressPercent > 0;
        },
    };
};
