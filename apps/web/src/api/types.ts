/**
 * TypeScript-типы API CustDevAI. Поддерживаются вручную из
 * /api/openapi.json (по решению пользователя — без кодогенератора).
 *
 * Phase 4 покрытие: auth, users, scripts, campaigns, reports.
 */

export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail?: string | null;
  instance?: string | null;
  errors?: Array<{ loc: unknown[]; msg: string; type?: string }>;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  must_change_password: boolean;
}

export interface UserOut {
  id: number;
  email: string;
  full_name: string | null;
  is_active: boolean;
  must_change_password: boolean;
  researcher_telegram_chat_id: number | null;
  roles: string[];
}

export interface MyProfileUpdate {
  full_name?: string | null;
  researcher_telegram_chat_id?: number | null;
}

export type CampaignStatus = "draft" | "running" | "paused" | "completed";
export type CampaignAnalysisStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export interface CampaignOut {
  id: number;
  title: string;
  description: string | null;
  script_id: number;
  created_by_user_id: number | null;
  status: CampaignStatus;
  invitation_url: string | null;
  started_at: string | null;
  completed_at: string | null;
  has_pseudonym_salt: boolean;
  analysis_status: CampaignAnalysisStatus;
  target_topic_count: number;
}

export interface CampaignAnalysisStatusOut {
  campaign_id: number;
  analysis_status: CampaignAnalysisStatus;
  analysis_started_at: string | null;
  analysis_completed_at: string | null;
  analysis_error: string | null;
  target_topic_count: number;
}

export interface CampaignCreate {
  title: string;
  description?: string | null;
  script_id: number;
  target_topic_count?: number;
}

export interface CampaignUpdate {
  title?: string | null;
  description?: string | null;
  status?: CampaignStatus | null;
  target_topic_count?: number | null;
}

export interface QuestionIn {
  text: string;
  order_index: number;
  is_required: boolean;
  hint_text?: string | null;
}

export interface QuestionOut extends QuestionIn {
  id: number;
  script_id: number;
}

export interface ScriptCreate {
  title: string;
  description?: string | null;
  questions?: QuestionIn[];
}

export interface ScriptOut {
  id: number;
  title: string;
  description: string | null;
  created_by_user_id: number | null;
  questions: QuestionOut[];
}

export type ReportFormat = "pdf" | "xlsx";

export interface ReportOut {
  id: number;
  campaign_id: number;
  format: ReportFormat;
  file_size: number;
  generated_at: string;
  generated_by_user_id: number | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
