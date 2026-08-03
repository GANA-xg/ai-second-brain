/* ── Auth ── */
export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  full_name: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  username: string | null;
  bio: string | null;
  avatar_url: string | null;
}

/* ── Documents ── */
export interface DocumentResponse {
  id: string;
  user_id: string;
  original_filename: string;
  mime_type: string;
  extension: string;
  file_size: number;
  sha256_checksum: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface UploadResponse {
  message: string;
  document: DocumentResponse;
}

export interface DocumentListResponse {
  documents: DocumentResponse[];
  total: number;
}

/* ── Chat ── */
export interface ChatRequest {
  question: string;
  conversation_id?: string | null;
  top_k?: number | null;
  score_threshold?: number | null;
  document_ids?: string[] | null;
}

export interface Citation {
  document_id: string;
  filename: string;
  chunk_id: string;
  page: number | null;
  score: number;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  conversation_id: string;
  message_id: string;
  retrieved_chunks: RetrievedChunk[];
  prompt_version: string;
  model_used: string;
}

export interface RetrievedChunk {
  chunk_id: string;
  document_id: string;
  score: number;
  content: string;
  filename: string | null;
  page: number | null;
  section: string | null;
  source_type: string | null;
}

export interface ConversationSummary {
  id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  conversations: ConversationSummary[];
  total: number;
}

export interface MessageResponse {
  id: string;
  role: string;
  content: string;
  status: string | null;
  citations: Record<string, unknown>[] | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  error_metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface ConversationDetailResponse {
  id: string;
  title: string;
  messages: MessageResponse[];
  message_count: number;
  page: number;
  page_size: number;
  has_next: boolean;
  created_at: string;
  updated_at: string;
}

export interface PaginatedMessages {
  messages: MessageResponse[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

/* SSE stream event types */
export interface StreamEvent {
  type: "token" | "citation" | "done" | "error";
  content?: string;
  citations?: Citation[];
  conversation_id?: string;
  message_id?: string;
  detail?: string;
}

/* ── Memory ── */
export type MemoryType = "FACT" | "PREFERENCE" | "GOAL";

export interface MemoryResponse {
  id: string;
  type: MemoryType;
  content: string;
  confidence: number;
  is_active: boolean;
  source_message_id: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface MemoryListResponse {
  memories: MemoryResponse[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface MemoryCreateRequest {
  type: MemoryType;
  content: string;
  confidence?: number;
}

export interface MemoryUpdateRequest {
  content?: string;
  type?: MemoryType;
  is_active?: boolean;
}

export interface MemoryDeleteResponse {
  detail: string;
  deleted_count: number;
}

/* ── Flashcards ── */
export type FlashcardDifficulty = "easy" | "medium" | "hard";

export interface FlashcardResponse {
  id: string;
  user_id: string;
  document_id: string;
  source_chunk_id: string | null;
  front: string;
  back: string;
  difficulty: FlashcardDifficulty;
  created_at: string;
  updated_at: string;
}

export interface FlashcardListResponse {
  flashcards: FlashcardResponse[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface FlashcardGenerateResponse {
  message: string;
  generated_count: number;
  discarded_count: number;
  total_count: number;
}

export interface FlashcardDeleteResponse {
  detail: string;
  deleted_count: number;
}

/* ── Quizzes ── */
export type QuestionType = "multiple_choice" | "true_false" | "short_answer";

export interface QuizQuestionSchema {
  id: string;
  question_type: string;
  question_text: string;
  options: string[] | null;
  correct_answer: string;
  explanation: string | null;
  order_index: number;
  difficulty: string | null;
  source_chunk_id: string | null;
}

export interface QuizQuestionPublic {
  id: string;
  question_type: string;
  question_text: string;
  options: string[] | null;
  order_index: number;
  difficulty: string | null;
  source_chunk_id: string | null;
}

export interface QuizResponse {
  id: string;
  user_id: string;
  document_id: string;
  title: string;
  total_questions: number;
  questions: QuizQuestionSchema[];
  created_at: string;
  updated_at: string;
}

export interface QuizSummary {
  id: string;
  title: string;
  document_id: string;
  total_questions: number;
  created_at: string;
}

export interface QuizListResponse {
  quizzes: QuizSummary[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface QuizGenerateResponse {
  message: string;
  quiz_id: string | null;
  total_questions: number;
  discarded_count: number;
}

export interface AttemptAnswerResult {
  question_text: string;
  user_answer: string;
  correct_answer: string;
  explanation: string | null;
  is_correct: boolean;
}

export interface QuizAttemptResponse {
  id: string;
  quiz_id: string;
  score: number;
  total_questions: number;
  correct_answers: number;
  completed_at: string | null;
  created_at: string;
  results: AttemptAnswerResult[];
}

export interface AttemptSummary {
  id: string;
  quiz_id: string;
  score: number;
  total_questions: number;
  correct_answers: number;
  completed_at: string | null;
  created_at: string;
}

export type QuizAttemptResult = QuizAttemptResponse;

export interface QuizAttemptListResponse {
  attempts: AttemptSummary[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

/* ── Generic API Error ── */
export interface ApiError {
  detail: string;
  status?: number;
}
