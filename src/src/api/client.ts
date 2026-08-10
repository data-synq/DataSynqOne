// `||` (not `??`) on purpose: the Dockerfile bakes `ENV VITE_BACKEND_URL=$ARG`,
// so an unset build-arg becomes an empty string ("") rather than undefined. `??`
// would keep that "" and send every request to the frontend's own origin (404).
// `||` treats "" as unset and falls back to the local backend for dev builds.
const BASE_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8001";

/** Die Sitzung ist abgelaufen oder wurde entzogen. Der Router-Guard fängt das ab. */
export class UnauthorizedError extends Error {
  constructor() {
    super("Nicht angemeldet");
    this.name = "UnauthorizedError";
  }
}

/** Eine Fehlermeldung des Backends, die direkt angezeigt werden darf. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Wird beim ersten 401 aufgerufen, damit der Auth-Store aufräumen kann. */
let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

/** Zieht `detail` aus einer FastAPI-Fehlerantwort, sonst den nackten Text. */
async function errorMessage(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const detail = JSON.parse(text).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail.message === "string") return detail.message;
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  } catch {
    /* keine JSON-Antwort — dann eben der Rohtext */
  }
  return text || `Request failed: ${res.status}`;
}

async function failure(res: Response): Promise<never> {
  if (res.status === 401) {
    onUnauthorized?.();
    throw new UnauthorizedError();
  }
  throw new ApiError(await errorMessage(res), res.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    // Das Session-Cookie muss auch dann mitgehen, wenn jemand am Vite-Proxy
    // vorbei direkt auf :8001 zugreift — dort ist der Aufruf cross-origin.
    credentials: "include",
    ...init,
  });
  if (!res.ok) await failure(res);
  return res.json() as Promise<T>;
}

export interface PaperlessDocument {
  id: number;
  title: string;
  correspondent: number | null;
  document_type: number | null;
  created: string;
  content?: string;
  original_file_name?: string | null;
}

export interface DocumentList {
  count: number;
  results: PaperlessDocument[];
}

export interface ChartDataset {
  label: string;
  data: number[];
}

export interface ChartSpec {
  chart_type: "bar" | "line" | "pie" | "doughnut";
  title: string;
  labels: string[];
  datasets: ChartDataset[];
  x_label?: string;
  y_label?: string;
}

export type AgentEvent =
  | { type: "tool_call"; id: string; name: string; arguments: Record<string, unknown> }
  | { type: "tool_result"; id: string; name: string; result: unknown }
  | { type: "message"; content: string }
  | { type: "error"; message: string }
  | { type: "suggestions"; items: string[] }
  | { type: "session"; id: string; title: string }
  | ({ type: "board"; id: string } & BoardEventFields)
  | { type: "ping" };

/** Ein Board-Ereignis nach Art — jede Art traegt ihre eigene Payload-Form. */
export type BoardEventFields =
  | { kind: "document"; title: string; payload: { documentId: number } }
  | { kind: "chart"; title: string; payload: { spec: ChartSpec } }
  | { kind: "email"; title: string; payload: { draftId: string } };

export type BoardEvent = { id: string; toolCallIndex: number } & BoardEventFields;

export interface EmailDraft {
  id: string;
  recipient: string;
  subject: string;
  body: string;
  document_id?: number | null;
  sent_at?: string | null;
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface StoredMessage {
  role: string;
  content: string;
  tool_calls?: { name: string; arguments: Record<string, unknown> }[] | null;
  board_events?: ({ id: string; tool_call_index: number } & BoardEventFields)[];
}

export interface ChatSessionDetail extends ChatSession {
  messages: StoredMessage[];
}

export interface TagRef {
  id: number;
  name: string;
  color: string;
}

export interface DocSummary {
  id: number;
  title: string;
  created: string;
  correspondent_name: string | null;
  document_type_name: string | null;
  /** Slug aus der Tag-Taxonomie. Beschriftung über `categoryLabel()`. */
  category: string | null;
  /** Aus einem `OBJ-…`-Tag in Paperless. Null, solange dort keines gepflegt ist. */
  object_name: string | null;
  tags: TagRef[];
  status: string;
  due_date: string | null;
  content?: string | null;
}

export interface Deadline {
  document_id: number;
  title: string;
  correspondent_name: string | null;
  object_name: string | null;
  due_date: string;
  days_until: number;
}

export interface ChartBucket {
  labels: string[];
  data: number[];
}

/** Die Zahlen hinter der Kennzahlenzeile. Die Unterzeilen formuliert KpiTileRow daraus. */
export interface DashboardKpis {
  open: number;
  urgent: number;
  overdue: number;
  untagged: number;
  recent_7d: number;
  total: number;
  open_new_7d: number;
  urgent_new_today: number;
  overdue_oldest_days: number;
  recent_7d_tagged: number;
}

export interface DashboardOverview {
  kpis: DashboardKpis;
  queue: DocSummary[];
  objects: string[];
  deadlines: Deadline[];
  recent: DocSummary[];
  charts: Record<string, ChartBucket>;
  generated_at: string;
}

async function streamChat(
  message: string,
  sessionId: string | null,
  onEvent: (event: AgentEvent) => void,
): Promise<void> {
  const res = await fetch(`${BASE_URL}/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (!res.ok) await failure(res);
  if (!res.body) throw new ApiError("Der Server hat keine Antwort geliefert.", res.status);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() ?? "";
      for (const chunk of chunks) {
        const line = chunk.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        onEvent(JSON.parse(line.slice("data: ".length)) as AgentEvent);
      }
    }
  } catch {
    throw new Error("Verbindung zum Server wurde unterbrochen. Bitte versuche es erneut.");
  }
}

export type PermissionName =
  | "documents:read"
  | "agent:chat"
  | "agent:write"
  | "sync:run"
  | "users:manage"
  | "mail:manage";

export interface AppUser {
  id: string;
  email: string;
  display_name: string;
  role: "admin" | "editor" | "viewer";
  role_label: string;
  is_active: boolean;
  must_change_password: boolean;
  mfa_enabled: boolean;
  object_access_mode: "all" | "restricted";
  object_codes: string[];
  last_login_at: string | null;
  created_at: string;
}

export interface ObjectOption {
  code: string;
  label: string;
}

export interface ObjectAccessInput {
  mode: "all" | "restricted";
  object_codes: string[];
}

export interface CurrentUser extends AppUser {
  permissions: PermissionName[];
  auth_stage: "password_change" | "mfa_setup" | "mfa_challenge" | "ready";
}

export interface AuthSession {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  absolute_expires_at: string;
  user_agent: string | null;
  current: boolean;
}

export interface MfaSetup {
  secret: string;
  provisioning_uri: string;
}

export interface MfaConfirmation {
  user: CurrentUser;
  recovery_codes: string[];
}

export interface InvitationInfo {
  display_name: string;
  purpose: "invitation" | "password_reset";
}

/** `invitation_link` steht nur drin, wenn die Mail nicht rausging. */
export interface InvitationResult {
  user: AppUser;
  mail_sent: boolean;
  invitation_link: string | null;
}

export interface MailSettings {
  enabled: boolean;
  host: string;
  port: number;
  security: string;
  username: string;
  from_email: string;
  from_name: string;
  reply_to: string;
  app_base_url: string;
}

export interface CaseSummary {
  id: string;
  tracking_id: string;
  title: string;
  summary: string | null;
  status: "open" | "closed";
  sender_email: string | null;
  object_code: string | null;
  created_at: string;
  closed_at: string | null;
}

export interface CaseDocumentRef {
  paperless_id: number;
  role: "email" | "attachment" | "reply" | "linked";
  added_at: string;
}

export interface CaseEvent {
  id: string;
  kind:
    | "received"
    | "filed"
    | "tagged"
    | "linked"
    | "unlinked"
    | "note_added"
    | "closed"
    | "reopened"
    | "reply_sent"
    | "chat_linked";
  detail: string | null;
  actor_user_id: string | null;
  /** Aufgelöster Anzeigename, wenn actor_user_id gesetzt ist. */
  actor_name: string | null;
  /** Freitext-Akteur ohne Konto, z. B. die Mail-Aufnahme-Pipeline. */
  actor_label: string | null;
  link_kind: "note" | "case" | "document" | "session" | null;
  link_id: string | null;
  created_at: string;
}

export interface CaseNote {
  id: string;
  author_user_id: string | null;
  author_name?: string | null;
  body: string;
  created_at: string;
}

export interface CaseLink {
  dependent_tracking_id: string;
  dependent_title: string;
  prerequisite_tracking_id: string;
  prerequisite_title: string;
  status: "proposed" | "confirmed";
  proposed_by: string;
  created_at: string;
}

export interface CaseLinkEdge {
  dependent_tracking_id: string;
  prerequisite_tracking_id: string;
  status: "proposed" | "confirmed";
  proposed_by: string;
  created_at: string;
}

export interface CaseDetail extends CaseSummary {
  documents: CaseDocumentRef[];
  events: CaseEvent[];
  notes: CaseNote[];
  links: CaseLink[];
}

export interface PendingSender {
  email: string;
  status: "pending" | "approved" | "rejected";
  approved_by: string | null;
  approved_at: string | null;
  expires_at: string | null;
  first_seen_at: string;
  last_seen_at: string;
}

export const api = {
  login: (email: string, password: string) =>
    request<CurrentUser>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ status: string }>("/auth/logout", { method: "POST" }),
  me: () => request<CurrentUser>("/auth/me"),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<CurrentUser>("/auth/password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),
  listAuthSessions: () => request<AuthSession[]>("/auth/sessions"),
  revokeAuthSession: (id: string) =>
    request<{ status: string }>(`/auth/sessions/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  revokeOtherAuthSessions: () =>
    request<{ status: string }>("/auth/sessions", { method: "DELETE" }),
  setupMfa: () => request<MfaSetup>("/auth/mfa/setup", { method: "POST" }),
  confirmMfa: (code: string) =>
    request<MfaConfirmation>("/auth/mfa/confirm", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  verifyMfa: (code: string) =>
    request<CurrentUser>("/auth/mfa/verify", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),

  invitationInfo: (token: string) =>
    request<InvitationInfo>(`/auth/invitation/${encodeURIComponent(token)}`),
  redeemInvitation: (token: string, password: string) =>
    request<CurrentUser>(`/auth/invitation/${encodeURIComponent(token)}`, {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  listUsers: () => request<AppUser[]>("/users/"),
  createUser: (payload: {
    email: string;
    display_name: string;
    role: string;
    object_access: ObjectAccessInput;
  }) =>
    request<InvitationResult>("/users/", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (
    id: string,
    payload: { display_name?: string; role?: string; is_active?: boolean },
  ) => request<AppUser>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  listObjectOptions: () => request<ObjectOption[]>("/users/object-options"),
  updateObjectScope: (id: string, objectAccess: ObjectAccessInput) =>
    request<AppUser>(`/users/${id}/object-scope`, {
      method: "PUT",
      body: JSON.stringify(objectAccess),
    }),
  resendInvitation: (id: string) =>
    request<InvitationResult>(`/users/${id}/invitation`, { method: "POST" }),
  deleteUser: (id: string) => request<{ status: string }>(`/users/${id}`, { method: "DELETE" }),

  mailSettings: () => request<MailSettings>("/mail/settings"),
  sendTestMail: () =>
    request<{ mail_sent: boolean; recipient: string; detail: string }>("/mail/test", {
      method: "POST",
    }),
  sendDraft: (id: string, recipient: string, subject: string, body: string) =>
    request<EmailDraft>(`/mail/drafts/${id}/send`, {
      method: "POST",
      body: JSON.stringify({ recipient, subject, body }),
    }),
  getDraft: (id: string) => request<EmailDraft>(`/mail/drafts/${id}`),

  listPendingSenders: (statusFilter?: string) =>
    request<PendingSender[]>(
      `/mail/pending-senders${statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : ""}`,
    ),
  approveSender: (email: string) =>
    request<PendingSender>(`/mail/pending-senders/${encodeURIComponent(email)}/approve`, {
      method: "POST",
    }),
  rejectSender: (email: string) =>
    request<PendingSender>(`/mail/pending-senders/${encodeURIComponent(email)}/reject`, {
      method: "POST",
    }),

  listCases: (statusFilter?: string) =>
    request<CaseSummary[]>(
      `/cases${statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : ""}`,
    ),
  getCase: (trackingId: string) => request<CaseDetail>(`/cases/${encodeURIComponent(trackingId)}`),
  addCaseNote: (trackingId: string, body: string) =>
    request<CaseNote>(`/cases/${encodeURIComponent(trackingId)}/notes`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),
  closeCase: (trackingId: string) =>
    request<CaseSummary>(`/cases/${encodeURIComponent(trackingId)}/close`, { method: "POST" }),
  reopenCase: (trackingId: string) =>
    request<CaseSummary>(`/cases/${encodeURIComponent(trackingId)}/reopen`, { method: "POST" }),
  listAllCaseLinks: () => request<CaseLinkEdge[]>("/cases/links/all"),
  createCaseLink: (dependentTrackingId: string, prerequisiteTrackingId: string) =>
    request<CaseLinkEdge>("/cases/links", {
      method: "POST",
      body: JSON.stringify({
        dependent_tracking_id: dependentTrackingId,
        prerequisite_tracking_id: prerequisiteTrackingId,
      }),
    }),
  confirmCaseLink: (dependentTrackingId: string, prerequisiteTrackingId: string) =>
    request<CaseLinkEdge>(
      `/cases/links/${encodeURIComponent(dependentTrackingId)}/${encodeURIComponent(prerequisiteTrackingId)}/confirm`,
      { method: "POST" },
    ),
  removeCaseLink: (dependentTrackingId: string, prerequisiteTrackingId: string) =>
    request<{ status: string }>(
      `/cases/links/${encodeURIComponent(dependentTrackingId)}/${encodeURIComponent(prerequisiteTrackingId)}`,
      { method: "DELETE" },
    ),
  attachCaseDocuments: (trackingId: string, paperlessIds: number[]) =>
    request<CaseDocumentRef[]>(`/cases/${encodeURIComponent(trackingId)}/documents`, {
      method: "POST",
      body: JSON.stringify({ paperless_ids: paperlessIds }),
    }),
  detachCaseDocument: (trackingId: string, paperlessId: number) =>
    request<{ status: string }>(
      `/cases/${encodeURIComponent(trackingId)}/documents/${paperlessId}`,
      { method: "DELETE" },
    ),

  getDocument: (id: number) => request<PaperlessDocument>(`/documents/${id}`),
  searchDocuments: (query: string) =>
    request<DocumentList>(`/documents/?query=${encodeURIComponent(query)}`),
  getDocumentDetail: (id: number) => request<DocSummary>(`/documents/${id}/detail`),
  getDashboardOverview: () => request<DashboardOverview>("/dashboard/overview"),
  streamChat,
  listSessions: () => request<ChatSession[]>("/sessions/"),
  getSession: (id: string) => request<ChatSessionDetail>(`/sessions/${id}`),
  deleteSession: (id: string) => request<{ status: string }>(`/sessions/${id}`, { method: "DELETE" }),
};
