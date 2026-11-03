import axios, { type InternalAxiosRequestConfig } from "axios";

const api = axios.create({
    baseURL:
        import.meta.env.VITE_API_URL ??
        (import.meta.env.DEV
            ? "http://127.0.0.1:8000/api/v1"
            : "https://ahmed2552-oraliq-api.hf.space/api/v1"),
    // A sleeping server can take ~60s to answer its first request. Long uploads
    // (exam submit, transcription) pass their own, longer timeout.
    timeout: 90_000,
});

// ── Slow-server signal ──────────────────────────────────────────────────────
// Any request still waiting after SLOW_MS marks the server as "waking up";
// <ServerStatus/> shows a calm notice instead of leaving the user guessing.
const SLOW_MS = 6_000;
let slowCount = 0;
const listeners = new Set<(slow: boolean) => void>();
const emit = () => listeners.forEach((fn) => fn(slowCount > 0));

export function onServerSlow(fn: (slow: boolean) => void) {
    listeners.add(fn);
    return () => { listeners.delete(fn); };
}

type TimedConfig = InternalAxiosRequestConfig & { _slowTimer?: ReturnType<typeof setTimeout>; _slow?: boolean };

function settle(config?: TimedConfig) {
    if (!config) return;
    if (config._slowTimer) clearTimeout(config._slowTimer);
    if (config._slow) {
        config._slow = false;
        slowCount = Math.max(0, slowCount - 1);
        emit();
    }
}

api.interceptors.request.use((config: TimedConfig) => {
    const token = localStorage.getItem("token");
    if (token) config.headers.Authorization = `Bearer ${token}`;

    // Uploads are expected to be slow; only flag ordinary requests.
    const isUpload = typeof FormData !== "undefined" && config.data instanceof FormData;
    if (!isUpload) {
        config._slowTimer = setTimeout(() => {
            config._slow = true;
            slowCount += 1;
            emit();
        }, SLOW_MS);
    }
    return config;
});

// ── Expired session ─────────────────────────────────────────────────────────
// The API answers an invalid/expired token with 403 "Could not validate credentials"
// and a deleted account with 401. Either way: back to sign-in, then back here.
function handleExpiredSession() {
    // Never navigate away mid-exam: that would throw away the student's recording.
    // ExamRoom shows its own "session expired" state instead.
    if (window.location.pathname.startsWith("/exam")) return;
    const hadToken = !!localStorage.getItem("token");
    localStorage.removeItem("token");
    if (!hadToken) return;
    const here = window.location.pathname + window.location.search;
    if (window.location.pathname.startsWith("/login")) return;
    window.location.assign(`/login?expired=1&redirect=${encodeURIComponent(here)}`);
}

api.interceptors.response.use(
    (response) => {
        settle(response.config as TimedConfig);
        return response;
    },
    (error) => {
        settle(error?.config as TimedConfig);
        const status = error?.response?.status;
        const detail = error?.response?.data?.detail;
        const isLogin = String(error?.config?.url || "").includes("/login/");
        if (!isLogin && (status === 401 || (status === 403 && detail === "Could not validate credentials"))) {
            handleExpiredSession();
        }
        return Promise.reject(error);
    },
);

export default api;
