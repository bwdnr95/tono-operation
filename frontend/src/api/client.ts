// src/api/client.ts

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://172.30.1.75:8000/api/v1";

type QueryParams = Record<string, unknown>;

function buildUrl(path: string, query?: QueryParams): string {
  const base = API_BASE_URL.replace(/\/+$/, "");
  const normPath = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(base + normPath);

  if (query) {
    Object.entries(query).forEach(([key, value]) => {
      if (value === undefined || value === null) return;

      if (Array.isArray(value)) {
        value.forEach((v) => url.searchParams.append(key, String(v)));
      } else {
        url.searchParams.set(key, String(value));
      }
    });
  }

  return url.toString();
}

async function request<TResponse>(
  path: string,
  options: RequestInit & { query?: QueryParams } = {},
): Promise<TResponse> {
  const { query, ...init } = options;
  const url = buildUrl(path, query);

  const resp = await fetch(url, {
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
    ...init,
  });

  if (!resp.ok) {
    let detail = "";
    try {
      detail = await resp.text();
    } catch {
      // ignore
    }
    throw new Error(
      `API error ${resp.status} ${resp.statusText}${
        detail ? ` – ${detail}` : ""
      }`,
    );
  }

  if (resp.status === 204) {
    return undefined as TResponse;
  }

  const data = (await resp.json()) as TResponse;
  return data;
}

export function apiGet<TResponse>(
  path: string,
  query?: QueryParams,
  init?: RequestInit,
): Promise<TResponse> {
  return request<TResponse>(path, {
    method: "GET",
    query,
    ...init,
  });
}

export function apiPost<TResponse = unknown, TBody = unknown>(
  path: string,
  body?: TBody,
  query?: QueryParams,
  init?: RequestInit,
): Promise<TResponse> {
  return request<TResponse>(path, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
    query,
    ...init,
  });
}

export function apiPatch<TResponse = unknown, TBody = unknown>(
  path: string,
  body?: TBody,
  query?: QueryParams,
  init?: RequestInit,
): Promise<TResponse> {
  return request<TResponse>(path, {
    method: "PATCH",
    body: body !== undefined ? JSON.stringify(body) : undefined,
    query,
    ...init,
  });
}

export function apiDelete<TResponse = unknown>(
  path: string,
  query?: QueryParams,
  init?: RequestInit,
): Promise<TResponse> {
  return request<TResponse>(path, {
    method: "DELETE",
    query,
    ...init,
  });
}
