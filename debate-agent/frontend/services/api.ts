const BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001";

export async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method, headers: { "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch {
    throw new Error("无法连接本机服务，请先在 8001 端口启动后端。");
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(`${error.error_code || "REQUEST_FAILED"}（${response.status}）`);
  }
  return response.json() as Promise<T>;
}

export async function exportMarkdown(revisionId: string): Promise<string> {
  const response = await fetch(`${BASE}/api/v1/case-revisions/${revisionId}/export`);
  if (!response.ok) throw new Error("导出失败，请检查正式版本。");
  return response.text();
}
