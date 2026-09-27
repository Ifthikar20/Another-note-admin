/**
 * The admin API's answers, as the BFF forwards them: the TypeScript side of
 * bff/app/contract.py. Times are UTC ISO-8601 strings; days are "YYYY-MM-DD" (UTC days).
 */

export type Role = "owner" | "support" | "analyst" | "viewer";
export type Kind = "standard" | "managed_child";
export type AgeBand = "under_13" | "13_17" | "18_plus" | "unknown";
export type UserStatus = "active" | "deactivated" | "deleted";
export type PlanSource = "user" | "organization" | "default";
export type TicketStatus = "open" | "waiting_on_us" | "waiting_on_user" | "resolved" | "closed";
export type TicketPriority = "low" | "normal" | "high" | "urgent";
export type AuthKind =
  | "sign_in"
  | "sign_in_failed"
  | "pin_locked"
  | "pin_reset"
  | "sign_out"
  | "sign_out_everywhere"
  | "password_changed"
  | "refresh_replay"
  | "admin_action";
export type AuthMethod = "password" | "google" | "microsoft" | "pin" | "desktop";
export type UsageGroup = "day" | "feature" | "provider" | "model";

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface Range {
  from: string;
  to: string;
  tz: "UTC";
}

export interface Me {
  email: string;
  role: Role;
  capabilities: string[];
  environment: "production" | "development";
  dev_identity: boolean;
  version: string;
  sign_out_url: string | null;
  idle_lock_minutes: number;
  idle_sign_out_minutes: number;
}

export interface Health {
  ok: boolean;
  bff_version: string;
  admin_api: { ok: boolean; db?: boolean; redis?: boolean; version?: string; error?: string };
}

// --- overview and metrics -------------------------------------------------------------
export interface FeatureCost {
  feature: string;
  cost_usd: number | null;
  tokens: number;
}

export interface Overview {
  range: Range;
  accounts: { total: number; adults: number; children: number; teachers: number; guardians: number; deactivated: number };
  activity: { online_now: number; active_today: number; active_7d: number; active_30d: number };
  sign_ins: { today: number; failed_today: number; by_method_today: Record<string, number> };
  sessions: { live: number; users_with_live_sessions: number };
  usage: {
    tokens_today: number;
    cost_today_usd: number | null;
    cost_month_usd: number | null;
    budget_month_usd: number | null;
    top_features_month: FeatureCost[];
  };
  tickets: { open: number; waiting_on_us: number; oldest_open_hours: number | null };
  storage: { pdfs: number; pdf_bytes: number };
  generated_at: string;
}

export interface ActiveUsers {
  range: Range;
  granularity: "day";
  series: { day: string; dau: number }[];
  wau: number;
  mau: number;
  as_of: string;
}

export interface DayCount {
  day: string;
  count: number;
}

export interface SignIns {
  range: Range;
  group: "method";
  series: { day: string; method: string; count: number }[];
  failures: DayCount[];
  totals: { sign_ins: number; failures: number };
}

export interface OnlineNow {
  online_now: number;
  live_sessions: number;
  users_with_live_sessions: number;
  generated_at: string;
}

// --- people ---------------------------------------------------------------------------
export interface Identity {
  email_masked: string | null;
  username_masked: string | null;
  first_name: string;
}

export interface UserRef {
  id: number;
  identity: Identity;
  kind: Kind;
}

export interface OrgRef {
  id: number;
  name: string;
}

export interface PlanRef {
  id: string;
  name: string;
  source: PlanSource;
  status: string;
}

export interface Usage30d {
  tokens: number;
  cost_usd: number | null;
}

export interface UserRow {
  id: number;
  identity: Identity;
  kind: Kind;
  role: string | null;
  age_band: AgeBand;
  organization: OrgRef | null;
  plan: PlanRef | null;
  created_at: string;
  last_login: string | null;
  last_seen_at: string | null;
  live_sessions: number;
  usage_30d: Usage30d;
  open_tickets: number;
  status: UserStatus;
  flags: string[];
}

export interface FamilyLink {
  id: number;
  relation: "guardian" | "child";
  other_user_id: number;
  origin: "created" | "claimed";
  status: "pending" | "active" | "revoked" | "aged_out";
  activated_at: string | null;
  revoked_at: string | null;
}

export interface UserDetail {
  user: UserRow;
  profile: {
    auth_provider: string | null;
    org_role: string | null;
    onboarding_completed: boolean;
    credentials_locked: boolean;
    pin_locked_until: string | null;
    xp: number;
    deleted_at: string | null;
    is_demo: boolean;
    email_domain: string | null;
  };
  footprint: {
    study_sessions: number;
    notes: number;
    youtube_sessions: number;
    pdfs: number;
    office_files: number;
    pdf_bytes: number;
    highlights: number;
    sticky_notes: number;
    answers: number;
    last_session_at: string | null;
  };
  family: {
    guardians_active: number;
    guardians_revoked: number;
    children_active: number;
    children_revoked: number;
    links: FamilyLink[];
  };
  security: { failed_sign_ins_30d: number; locked_until: string | null; replays_30d: number };
  usage_by_feature_30d: { feature: string; tokens: number; cost_usd: number | null }[];
  activity_30d: { day: string; active_seconds: number }[];
  note: string;
}

export interface RevealedEmail {
  email: string | null;
  first_name: string;
}

export interface LiveSession {
  session_id: number;
  created_at: string;
  expires_at: string;
  device: { ua_family: string | null; country: string | null; method: AuthMethod | null; last_refresh_at: string | null } | null;
}

// --- usage ----------------------------------------------------------------------------
export interface UsageNumbers {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  characters: number;
  audio_ms: number;
  cost_usd: number | null;
  unpriced_calls: number;
}

export interface UsageRow extends UsageNumbers {
  key: string;
}

export interface UsagePoint {
  day: string;
  key: string;
  calls: number;
  tokens: number;
  characters: number;
  audio_ms: number;
  cost_usd: number | null;
}

export interface UsageSummary {
  range: Range;
  group: UsageGroup;
  totals: UsageNumbers;
  rows: UsageRow[];
  series: UsagePoint[];
  month_to_date?: { month: string; cost_usd: number | null; budget_usd: number | null } | null;
}

export interface TopUser {
  user: UserRef;
  value: number;
  calls: number;
  tokens: number;
  characters: number;
  cost_usd: number | null;
}

export interface TopUsers {
  range: Range;
  metric: "cost" | "tokens" | "characters";
  items: TopUser[];
}

export interface Anomaly {
  user: UserRef;
  metric: "tokens" | "cost";
  value: number;
  median_30d: number;
  ratio: number | null;
  reason: "spike" | "over_plan_share";
  plan_id: string | null;
}

export interface Anomalies {
  date: string;
  items: Anomaly[];
}

export interface Price {
  provider: string;
  model: string;
  input_per_mtok: number | null;
  output_per_mtok: number | null;
  cache_read_per_mtok: number | null;
  cache_write_per_mtok: number | null;
  per_mchar: number | null;
  per_request: number | null;
}

export interface Prices {
  items: Price[];
  source: string;
  currency: "USD";
  budget_month_usd: number | null;
}

// --- plans ----------------------------------------------------------------------------
export interface PlanLimits {
  monthly_ai_tokens?: number | null;
  monthly_ai_cost_usd?: number | null;
  monthly_tts_characters?: number | null;
  monthly_transcription_minutes?: number | null;
  max_upload_mb?: number | null;
  max_study_sessions?: number | null;
  teach_mode?: boolean | null;
  pictures?: boolean | null;
  youtube_import?: boolean | null;
  family_seats?: number | null;
}

export interface Plan {
  id: string;
  name: string;
  description: string;
  is_default: boolean;
  is_active: boolean;
  limits: PlanLimits;
  price_cents: number | null;
  currency: string | null;
  interval: "month" | "year" | null;
  created_at: string;
  updated_at: string;
  assignments: { active: number; trial: number };
}

export interface Assignment {
  id: number;
  subject_type: "user" | "organization";
  subject_id: number;
  plan_id: string;
  status: "active" | "trial" | "past_due" | "canceled" | "expired";
  source: "manual" | "promo" | "organization" | "stripe";
  starts_at: string;
  ends_at: string | null;
  note: string | null;
  assigned_by: string | null;
  created_at: string;
}

export interface SubjectPlan {
  effective: {
    plan: { id: string; name: string };
    source: PlanSource;
    status: string;
    assignment_id: number | null;
    starts_at: string | null;
    ends_at: string | null;
  };
  history: Assignment[];
}

// --- organisations ------------------------------------------------------------------
export interface OrgRow {
  id: number;
  name: string;
  slug: string;
  sso_provider: string | null;
  sso_enforced: boolean;
  created_at: string;
  members: number;
  plan: PlanRef | null;
}

export interface OrgDetail {
  org: OrgRow;
  domains: { domain: string; verified: boolean }[];
  member_counts: { total: number; teachers: number; students: number; org_owners: number; org_admins: number };
  plan: SubjectPlan;
}

// --- tickets ----------------------------------------------------------------------------
export interface TicketRow {
  id: number;
  number: string;
  reason: string;
  reason_label: string;
  subject: string;
  status: TicketStatus;
  priority: TicketPriority;
  assignee_email: string | null;
  tags: string[];
  user: UserRef;
  created_at: string;
  updated_at: string;
  last_user_at: string | null;
  last_staff_at: string | null;
  message_count: number;
  preview: string;
}

export type TicketCounts = Record<TicketStatus, number>;

export interface TicketList extends Page<TicketRow> {
  counts: TicketCounts;
}

export interface TicketMessage {
  id: number;
  author: "user" | "staff" | "system";
  staff_email: string | null;
  body: string;
  internal: boolean;
  created_at: string;
}

export interface TicketDetail {
  ticket: TicketRow;
  page_url: string | null;
  context: {
    browser?: string | null;
    language?: string | null;
    viewport?: string | null;
    timezone?: string | null;
    app_version?: string | null;
    session_id?: string | null;
    from?: string | null;
  } | null;
  closed_at: string | null;
  messages: TicketMessage[];
  user: {
    id: number;
    identity: Identity;
    kind: Kind;
    organization: OrgRef | null;
    plan: PlanRef | null;
    last_seen_at: string | null;
    usage_30d: Usage30d;
  };
}

export interface OutboxEvent {
  id: number;
  kind: "ticket.created" | "ticket.user_replied";
  ticket_id: number;
  created_at: string;
}

// --- security -------------------------------------------------------------------------
export interface AuthEvent {
  id: number;
  created_at: string;
  user_id: number | null;
  kind: AuthKind;
  method: AuthMethod | null;
  reason: string | null;
  country: string | null;
  ua_family: string | null;
  ip_prefix_hash: string | null;
  identifier_hash: string | null;
}

export interface SecuritySummary {
  range: Range;
  totals: { sign_ins: number; failed: number; lockouts: number; replays: number; pin_resets: number; sign_outs_everywhere: number };
  failed_per_hour: { hour: string; count: number }[];
  failures_by_reason: { reason: string; count: number }[];
  top_networks: { ip_prefix_hash: string; failures: number; identifiers: number; countries: string[]; last_at: string }[];
}

// --- activity (analytics) ---------------------------------------------------------------
export interface AnalyticsSummary {
  range: Range;
  totals: { views: number; actions: number; errors: number; users: number };
  by_day: { day: string; view: number; action: number; error: number }[];
  top_pages: { name: string; count: number; users: number }[];
  top_actions: { name: string; count: number; users: number }[];
  campaigns: { utm_source: string | null; utm_medium: string | null; utm_campaign: string | null; events: number; users: number }[];
}

export interface ErrorGroup {
  name: string;
  count: number;
  users: number;
  first_at: string;
  last_at: string;
  paths: string[];
  by_day: DayCount[];
}

export interface ErrorGroups extends Page<ErrorGroup> {
  range: Range;
}

export interface AnalyticsEvent {
  id: number;
  created_at: string;
  user_id: number | null;
  kind: "view" | "action" | "error";
  name: string;
  path: string | null;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
}

// --- audit and settings -------------------------------------------------------------------
export interface AuditRow {
  id: number;
  at: string;
  actor_email: string;
  actor_role: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  reason: string | null;
  request_id: string | null;
  details: Record<string, string | number | boolean | null | (string | number)[]> | null;
}

export interface Members {
  items: { email: string; role: Role }[];
  source: string;
  editable: boolean;
  dev_identity: { email: string; role: Role } | null;
}

export interface AccessReview {
  generated_at: string;
  generated_by: string;
  items: {
    email: string;
    role: Role;
    capabilities: string[];
    last_admin_action_at: string | null;
    last_admin_action: string | null;
    dev_identity: boolean;
  }[];
  sources: string[];
}
