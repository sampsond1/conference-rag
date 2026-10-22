function getRuntimePublishableKey(): string | undefined {
  const singleKey = Deno.env.get("SUPABASE_PUBLISHABLE_KEY") ??
    Deno.env.get("SUPABASE_ANON_KEY");
  if (singleKey) return singleKey;

  // Newer Supabase projects expose named publishable keys as a JSON object.
  const namedKeysJson = Deno.env.get("SUPABASE_PUBLISHABLE_KEYS");
  if (namedKeysJson) {
    try {
      const namedKeys: unknown = JSON.parse(namedKeysJson);
      if (namedKeys && typeof namedKeys === "object") {
        const defaultKey = (namedKeys as Record<string, unknown>).default;
        if (typeof defaultKey === "string") return defaultKey;
      }
    } catch {
      // The caller can still provide the public apikey header.
    }
  }

  return undefined;
}

/**
 * Verify the caller's bearer token with this project's Supabase Auth service.
 * Decoding a JWT locally would only read its claims; it would not prove that
 * the token is valid or unexpired.
 */
export async function verifyUserToken(request: Request): Promise<boolean> {
  const authorization = request.headers.get("authorization");
  const match = authorization?.match(/^Bearer\s+(.+)$/i);
  if (!match) return false;

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const apiKey = request.headers.get("apikey") ?? getRuntimePublishableKey();
  if (!supabaseUrl || !apiKey) {
    throw new Error("Supabase Auth verification is not configured.");
  }

  const response = await fetch(
    `${supabaseUrl.replace(/\/+$/, "")}/auth/v1/user`,
    {
      method: "GET",
      headers: {
        "apikey": apiKey,
        "Authorization": `Bearer ${match[1]}`,
      },
    },
  );

  if (response.status === 401 || response.status === 403) return false;
  if (!response.ok) {
    throw new Error("Supabase Auth could not verify the request.");
  }

  const user: unknown = await response.json();
  return Boolean(
    user && typeof user === "object" &&
      typeof (user as Record<string, unknown>).id === "string",
  );
}
