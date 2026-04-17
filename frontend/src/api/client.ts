const TOKEN_KEY = "pgia_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(t: string | null) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

/** Item devolvido pela API em erros 400 de governança Kanban. */
export type GovernanceNoticePayload = { message: string; href?: string | null };

export class ApiError extends Error {
  governance?: GovernanceNoticePayload[];

  constructor(message: string, opts?: { governance?: GovernanceNoticePayload[] }) {
    super(message);
    this.name = "ApiError";
    this.governance = opts?.governance;
  }
}

function isGovernanceDetail(d: unknown): d is GovernanceNoticePayload[] {
  if (!Array.isArray(d) || d.length === 0) return false;
  const first = d[0];
  if (typeof first !== "object" || first === null) return false;
  return typeof (first as { message?: unknown }).message === "string";
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const tok = getToken();
  if (tok) headers.set("Authorization", `Bearer ${tok}`);
  const res = await fetch(`/api${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (j?.detail != null) {
        if (typeof j.detail === "string") {
          detail = j.detail;
        } else if (isGovernanceDetail(j.detail)) {
          const items: GovernanceNoticePayload[] = j.detail.map((x) => ({
            message: x.message,
            href: x.href ?? undefined,
          }));
          const summary = items.map((i) => i.message).join(" ");
          throw new ApiError(summary, { governance: items });
        } else if (Array.isArray(j.detail) && j.detail[0] && typeof (j.detail[0] as { msg?: string }).msg === "string") {
          detail =
            (j.detail as { msg?: string }[])
              .map((x) => x.msg)
              .filter(Boolean)
              .join("; ") || JSON.stringify(j.detail);
        } else {
          detail = JSON.stringify(j.detail);
        }
      }
    } catch (e) {
      if (e instanceof ApiError) throw e;
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** Resposta binária (ex.: application/zip) com o mesmo auth que `api`. */
export async function apiBlob(path: string, init: RequestInit = {}): Promise<Blob> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const tok = getToken();
  if (tok) headers.set("Authorization", `Bearer ${tok}`);
  const res = await fetch(`/api${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const raw = await res.text();
      try {
        const j = JSON.parse(raw) as { detail?: unknown };
        if (typeof j.detail === "string") detail = j.detail;
        else if (j.detail != null) detail = JSON.stringify(j.detail);
      } catch {
        detail = raw.slice(0, 800) || detail;
      }
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.blob();
}

/** Texto (ex.: HTML) com o mesmo auth que `api`. */
export async function apiText(path: string, init: RequestInit = {}): Promise<string> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "*/*");
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const tok = getToken();
  if (tok) headers.set("Authorization", `Bearer ${tok}`);
  const res = await fetch(`/api${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const raw = await res.text();
      try {
        const j = JSON.parse(raw) as { detail?: unknown };
        if (typeof j.detail === "string") detail = j.detail;
        else if (j.detail != null) detail = JSON.stringify(j.detail);
      } catch {
        detail = raw.slice(0, 800) || detail;
      }
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.text();
}
