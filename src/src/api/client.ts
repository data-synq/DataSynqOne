const BASE_URL = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8001";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export interface PaperlessDocument {
  id: number;
  title: string;
  correspondent: number | null;
  document_type: number | null;
  created: string;
  content?: string;
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
  | { type: "chart"; id: string; spec: ChartSpec }
  | { type: "session"; id: string }
  | { type: "ping" };

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
  tags: TagRef[];
  status: string;
  due_date: string | null;
  content?: string | null;
}

export interface Deadline {
  document_id: number;
  title: string;
  correspondent_name: string | null;
  due_date: string;
  days_until: number;
}

export interface ChartBucket {
  labels: string[];
  data: number[];
}

export interface DashboardOverview {
  kpis: Record<string, number>;
  by_status: Record<string, DocSummary[]>;
  deadlines: Deadline[];
  recent: DocSummary[];
  charts: Record<string, ChartBucket>;
  generated_at: string;
}

async function streamChat(
  message: string,
  history: { role: string; content: string }[],
  sessionId: string | null,
  onEvent: (event: AgentEvent) => void,
): Promise<void> {
  const res = await fetch(`${BASE_URL}/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history, session_id: sessionId }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`Request failed: ${res.status} ${await res.text()}`);
  }

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

export const api = {
  getDocument: (id: number) => request<PaperlessDocument>(`/documents/${id}`),
  getDocumentDetail: (id: number) => request<DocSummary>(`/documents/${id}/detail`),
  getDashboardOverview: () => request<DashboardOverview>("/dashboard/overview"),
  streamChat,
  listSessions: () => request<ChatSession[]>("/sessions/"),
  getSession: (id: string) => request<ChatSessionDetail>(`/sessions/${id}`),
  deleteSession: (id: string) => request<{ status: string }>(`/sessions/${id}`, { method: "DELETE" }),
};
