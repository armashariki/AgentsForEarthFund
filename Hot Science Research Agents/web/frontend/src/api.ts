import type {
  AdminRunHistoryItem,
  ArtifactLink,
  RunHistoryItem,
  RunRequest,
  RunResponse,
  UserIdentity
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export type LoginResponse = {
  access_token: string;
  token_type: "bearer";
  user: UserIdentity;
};

export async function login(username: string, password: string): Promise<LoginResponse> {
  return request<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password })
  });
}

export async function me(token: string): Promise<{ user: UserIdentity }> {
  return request<{ user: UserIdentity }>("/api/me", { token });
}

export async function runHotScience(
  token: string,
  payload: RunRequest
): Promise<RunResponse> {
  return request<RunResponse>("/api/hot-science/runs", {
    method: "POST",
    token,
    body: JSON.stringify(payload)
  });
}

export async function listRuns(token: string): Promise<{ runs: RunHistoryItem[] }> {
  return request<{ runs: RunHistoryItem[] }>("/api/hot-science/runs", { token });
}

export async function listAdminRuns(
  token: string
): Promise<{ runs: AdminRunHistoryItem[] }> {
  return request<{ runs: AdminRunHistoryItem[] }>("/api/admin/hot-science/runs", {
    token
  });
}

export async function downloadArtifact(token: string, artifact: ArtifactLink): Promise<void> {
  const response = await fetch(`${API_BASE}${artifact.download_url}`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!response.ok) {
    throw new Error(await responseText(response));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = artifact.filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function request<T>(
  path: string,
  options: RequestInit & { token?: string } = {}
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers
  });
  if (!response.ok) {
    throw new Error(await responseText(response));
  }
  return response.json() as Promise<T>;
}

async function responseText(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    return JSON.stringify(payload);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}
