// LM Studio Auto Optimizer - WebSocket Manager

export class WebSocketManager {
    constructor() {
        this.connections = new Map();
        this.reconnectAttempts = new Map();
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 2000;
        this._intentional = new Set();
        this._unloaded = false;
        window.addEventListener('beforeunload', () => { this._unloaded = true; this.disconnectAll(); });
    }

    _scheme() {
        return window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    }

    connect(runId, onMessage) {
        this._intentional.delete(runId);
        const ws = new WebSocket(`${this._scheme()}//${window.location.host}/ws/optimize/${runId}`);

        ws.onopen = () => {
            console.log(`WebSocket connected for run ${runId}`);
            this.reconnectAttempts.set(runId, 0);
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                onMessage(data);
            } catch (error) {
                console.error('WebSocket message parse error:', error);
            }
        };

        ws.onclose = () => {
            console.log(`WebSocket disconnected for run ${runId}`);
            if (this._intentional.has(runId) || this._unloaded) return;
            this.attemptReconnect(runId, onMessage);
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        this.connections.set(runId, ws);
        return ws;
    }

    disconnect(runId) {
        this._intentional.add(runId);
        const ws = this.connections.get(runId);
        if (ws) {
            try { ws.close(); } catch (e) {}
            this.connections.delete(runId);
            this.reconnectAttempts.delete(runId);
        }
        // clear any pending reconnect timer
        if (this._reconnectTimers && this._reconnectTimers.has(runId)) {
            clearTimeout(this._reconnectTimers.get(runId));
            this._reconnectTimers.delete(runId);
        }
    }

    disconnectAll() {
        this._unloaded = true;
        for (const [runId, ws] of this.connections) {
            this._intentional.add(runId);
            try { ws.close(); } catch (e) {}
        }
        this.connections.clear();
        this.reconnectAttempts.clear();
    }

    attemptReconnect(runId, onMessage) {
        if (this._unloaded || this._intentional.has(runId)) return;
        const attempts = this.reconnectAttempts.get(runId) || 0;

        if (attempts >= this.maxReconnectAttempts) {
            console.log(`Max reconnect attempts reached for run ${runId}`);
            return;
        }

        this.reconnectAttempts.set(runId, attempts + 1);
        const delay = this.reconnectDelay * (attempts + 1);
        const timer = setTimeout(() => {
            if (this._intentional.has(runId) || this._unloaded) return;
            console.log(`Reconnecting to run ${runId} (attempt ${attempts + 1})`);
            this.connect(runId, onMessage);
        }, delay);
        if (!this._reconnectTimers) this._reconnectTimers = new Map();
        this._reconnectTimers.set(runId, timer);
    }
}

export default WebSocketManager;