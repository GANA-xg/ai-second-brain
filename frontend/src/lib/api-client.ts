/* ── Typed API client for every backend endpoint ── */
import api from "./api";
import type {
  LoginRequest,
  RegisterRequest,
  TokenResponse,
  UserResponse,
  DocumentListResponse,
  DocumentResponse,
  UploadResponse,
  ConversationListResponse,
  ConversationSummary,
  ConversationDetailResponse,
  ChatResponse,
  PaginatedMessages,
  MemoryListResponse,
  MemoryResponse,
  MemoryCreateRequest,
  MemoryUpdateRequest,
  MemoryDeleteResponse,
  FlashcardListResponse,
  FlashcardResponse,
  FlashcardGenerateResponse,
  FlashcardDeleteResponse,
  QuizListResponse,
  QuizResponse,
  QuizGenerateResponse,
  QuizAttemptResponse,
  QuizAttemptListResponse,
  QuizAttemptResult,
} from "./types";

/* ── Auth ── */
export const authApi = {
  login: (data: LoginRequest) =>
    api.post<TokenResponse>("/auth/login", data).then((r) => r.data),

  register: (data: RegisterRequest) =>
    api.post<UserResponse>("/auth/register", data).then((r) => r.data),

  refresh: (refreshToken: string) =>
    api
      .post<TokenResponse>("/auth/refresh", { refresh_token: refreshToken })
      .then((r) => r.data),

  logout: (refreshToken: string) =>
    api
      .post<{ message: string }>("/auth/logout", { refresh_token: refreshToken })
      .then((r) => r.data),

  logoutAll: () =>
    api.post<{ message: string }>("/auth/logout-all").then((r) => r.data),

  getProfile: () =>
    api.get<UserResponse>("/auth/me").then((r) => r.data),

  updateProfile: (data: { full_name?: string; username?: string; bio?: string; avatar_url?: string }) =>
    api.patch<UserResponse>("/auth/me", data).then((r) => r.data),
};

/* ── Documents ── */
export const documentsApi = {
  list: (skip = 0, limit = 50) =>
    api.get<DocumentListResponse>("/files", { params: { skip, limit } }).then((r) => r.data),

  get: (id: string) =>
    api.get<DocumentResponse>(`/files/${id}`).then((r) => r.data),

  upload: (file: File, onProgress?: (pct: number) => void) => {
    const formData = new FormData();
    formData.append("file", file);
    return api
      .post<UploadResponse>("/files/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => {
          if (onProgress && e.total) {
            onProgress(Math.round((e.loaded * 100) / e.total));
          }
        },
      })
      .then((r) => r.data);
  },

  delete: (id: string) =>
    api.delete(`/files/${id}`).then((r) => r.data),
};

/* ── Chat / Conversations ── */
export const chatApi = {
  listConversations: (limit = 50, offset = 0) =>
    api
      .get<ConversationListResponse>("/chat/conversations", {
        params: { limit, offset },
      })
      .then((r) => r.data),

  createConversation: (title?: string) =>
    api
      .post<ConversationSummary>("/chat/conversations", { title })
      .then((r) => r.data),

  getConversation: (id: string, page = 1, pageSize = 50) =>
    api
      .get<ConversationDetailResponse>(`/chat/conversations/${id}`, {
        params: { page, page_size: pageSize },
      })
      .then((r) => r.data),

  updateConversation: (id: string, title: string) =>
    api
      .patch<ConversationSummary>(`/chat/conversations/${id}`, { title })
      .then((r) => r.data),

  deleteConversation: (id: string) =>
    api.delete(`/chat/conversations/${id}`).then((r) => r.data),

  getMessages: (conversationId: string, page = 1, pageSize = 50) =>
    api
      .get<PaginatedMessages>(
        `/chat/conversations/${conversationId}/messages`,
        { params: { page, page_size: pageSize } }
      )
      .then((r) => r.data),

  ask: (data: {
    question: string;
    conversation_id?: string | null;
    top_k?: number | null;
    score_threshold?: number | null;
  }) => api.post<ChatResponse>("/chat/ask", data).then((r) => r.data),

  streamUrl: () => `${api.defaults.baseURL}/chat/stream`,
};

/* ── Memories ── */
export const memoriesApi = {
  list: (params?: {
    type?: string;
    is_active?: boolean;
    include_deleted?: boolean;
    page?: number;
    page_size?: number;
  }) =>
    api.get<MemoryListResponse>("/memories", { params }).then((r) => r.data),

  create: (data: MemoryCreateRequest) =>
    api.post<MemoryResponse>("/memories", data).then((r) => r.data),

  get: (id: string) =>
    api.get<MemoryResponse>(`/memories/${id}`).then((r) => r.data),

  update: (id: string, data: MemoryUpdateRequest) =>
    api.patch<MemoryResponse>(`/memories/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    api.delete<MemoryDeleteResponse>(`/memories/${id}`).then((r) => r.data),

  deleteAll: () =>
    api.delete<MemoryDeleteResponse>("/memories").then((r) => r.data),
};

/* ── Flashcards ── */
export const flashcardsApi = {
  generate: (documentId: string) =>
    api
      .post<FlashcardGenerateResponse>(
        `/documents/${documentId}/flashcards/generate`
      )
      .then((r) => r.data),

  list: (params?: {
    document_id?: string;
    page?: number;
    page_size?: number;
  }) =>
    api
      .get<FlashcardListResponse>("/flashcards", { params })
      .then((r) => r.data),

  update: (id: string, data: { front?: string; back?: string }) =>
    api.patch<FlashcardResponse>(`/flashcards/${id}`, data).then((r) => r.data),

  delete: (id: string) => api.delete(`/flashcards/${id}`),

  deleteForDocument: (documentId: string) =>
    api
      .delete<FlashcardDeleteResponse>(`/documents/${documentId}/flashcards`)
      .then((r) => r.data),
};

/* ── Quizzes ── */
export const quizzesApi = {
  generate: (documentId: string, questionCount = 5) =>
    api
      .post<QuizGenerateResponse>(
        `/documents/${documentId}/quizzes/generate`,
        null,
        { params: { question_count: questionCount } }
      )
      .then((r) => r.data),

  list: (params?: {
    document_id?: string;
    page?: number;
    page_size?: number;
  }) =>
    api.get<QuizListResponse>("/quizzes", { params }).then((r) => r.data),

  get: (id: string) =>
    api.get<QuizResponse>(`/quizzes/${id}`).then((r) => r.data),

  delete: (id: string) => api.delete(`/quizzes/${id}`),

  deleteForDocument: (documentId: string) =>
    api.delete(`/documents/${documentId}/quizzes`),

  submitAttempt: (quizId: string, answers: Array<{ question_id: string; answer: string }>) =>
    api
      .post<QuizAttemptResponse>(`/quizzes/${quizId}/attempt`, answers)
      .then((r) => r.data),

  listAttempts: (quizId: string, params?: { page?: number; page_size?: number }) =>
    api
      .get<QuizAttemptListResponse>(`/quizzes/${quizId}/attempts`, { params })
      .then((r) => r.data),

  getAttempt: (quizId: string, attemptId: string) =>
    api
      .get<QuizAttemptResult>(`/quizzes/${quizId}/attempts/${attemptId}`)
      .then((r) => r.data),
};
