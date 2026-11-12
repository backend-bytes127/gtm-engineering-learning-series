// Thin fetch wrapper. Every failure becomes an ApiError with a message that is safe to show to the user.
export class ApiError extends Error {
  constructor(message, status, data) { super(message); this.status = status; this.data = data; }
}

async function request(method, path, { body, headers, raw } = {}) {
  let res;
  try {
    res = await fetch(path, { method, headers: { ...(body && !raw ? { "Content-Type": "application/json" } : {}), ...headers }, body: raw ?? (body ? JSON.stringify(body) : undefined) });
  } catch {
    throw new ApiError("Cannot reach the app. Is `python3 -m sequencer serve` still running?", 0);
  }
  const isJson = (res.headers.get("content-type") || "").includes("json");
  const data = isJson ? await res.json() : res;
  if (!res.ok) throw new ApiError(isJson && data.error ? data.error : `Request failed (${res.status})`, res.status, data);
  return data;
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body = {}) => request("POST", path, { body }),
  upload: (file) => request("POST", "/api/upload", { raw: file, headers: { "X-Filename": file.name } }),
};
