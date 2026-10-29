export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method,
      credentials: "include",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      0,
      "Cannot reach the server. Check your connection and try again.",
    );
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const fields = data.error?.fields
      ?.map(
        (f: { field: string; message: string }) =>
          `${f.field.replace(/^body\./, "")}: ${f.message}`,
      )
      .join("; ");
    throw new ApiError(
      response.status,
      fields || data.error?.message || `Request failed (${response.status})`,
    );
  }
  if (method !== "GET" && path.startsWith("/profile"))
    window.dispatchEvent(new Event("candidate-updated"));
  return response.status === 204 ? (undefined as T) : response.json();
}
