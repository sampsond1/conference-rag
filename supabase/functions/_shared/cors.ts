const DEFAULT_ALLOWED_ORIGINS = [
  // GitHub Pages origin for this repository. The path is not part of Origin.
  "https://sampsond1.github.io",
  // Common local static-server addresses for development.
  "http://localhost:5500",
  "http://127.0.0.1:5500",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
];

function allowedOrigins(): Set<string> {
  const configuredOrigins = Deno.env.get("ALLOWED_ORIGINS")
    ?.split(",")
    .map((origin) => origin.trim())
    .filter(Boolean) ?? [];

  return new Set([...DEFAULT_ALLOWED_ORIGINS, ...configuredOrigins]);
}

export function isAllowedOrigin(origin: string | null): boolean {
  // Requests from command-line tools may not send an Origin header. They still
  // need a valid Supabase user token, which is checked separately.
  return origin === null || allowedOrigins().has(origin);
}

export function corsHeaders(request: Request): Headers {
  const headers = new Headers({
    "Access-Control-Allow-Headers":
      "authorization, apikey, content-type, x-client-info",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Vary": "Origin",
  });

  const origin = request.headers.get("origin");
  if (origin && isAllowedOrigin(origin)) {
    headers.set("Access-Control-Allow-Origin", origin);
  }

  return headers;
}
