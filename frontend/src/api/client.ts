// src/api/client.ts

const API_BASE =
  import.meta.env.VITE_API_BASE_URL?.toString() || "/api/v1";

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!res.ok) {
    let msg = `API error ${res.status}`;
    try {
      const data = await res.json();
      if (data?.detail) msg = data.detail;
    } catch {
      // ignore
    }
    throw new ApiError(msg, res.status);
  }

  if (res.status === 204) {
    // no content
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),
};

export { ApiError };
