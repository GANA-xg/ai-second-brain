import axios, {
  AxiosError,
  AxiosInstance,
  InternalAxiosRequestConfig,
} from "axios";

let apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
if (apiBase.endsWith("/")) apiBase = apiBase.slice(0, -1);

const api: AxiosInstance = axios.create({
  baseURL: apiBase,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 60000,
});

/* ── Token management (memory only) ── */
let accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/* ── Refresh token management (httpOnly cookie — just a holder for the opaque value we send) ── */
let refreshTokenValue: string | null = null;

export function setRefreshToken(token: string | null) {
  refreshTokenValue = token;
}

export function getRefreshToken(): string | null {
  return refreshTokenValue;
}

export function clearTokens() {
  accessToken = null;
  refreshTokenValue = null;
}

/* ── Request interceptor: attach access token ── */
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
    // For multipart uploads, let browser set Content-Type
    if (config.data instanceof FormData) {
      delete config.headers["Content-Type"];
    }
    return config;
  },
  (error) => Promise.reject(error)
);

/* ── Response interceptor: 401 → refresh → retry ── */
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach((p) => {
    if (token) {
      p.resolve(token);
    } else {
      p.reject(error);
    }
  });
  failedQueue = [];
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    // Don't retry auth endpoints or if already retried
    if (
      !originalRequest ||
      originalRequest._retry ||
      originalRequest.url?.includes("/auth/") ||
      error.response?.status !== 401
    ) {
      return Promise.reject(error);
    }

    if (isRefreshing) {
      return new Promise<string>((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      }).then((token) => {
        originalRequest.headers.Authorization = `Bearer ${token}`;
        return api(originalRequest);
      });
    }

    originalRequest._retry = true;
    isRefreshing = true;

    try {
      const response = await axios.post(`${apiBase}/auth/refresh`, {
        refresh_token: refreshTokenValue,
      });
      const { access_token, refresh_token } = response.data;
      setAccessToken(access_token);
      setRefreshToken(refresh_token);
      processQueue(null, access_token);
      originalRequest.headers.Authorization = `Bearer ${access_token}`;
      return api(originalRequest);
    } catch (refreshError) {
      processQueue(refreshError, null);
      clearTokens();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/auth/")) {
        window.location.href = "/auth/login";
      }
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);

export default api;
