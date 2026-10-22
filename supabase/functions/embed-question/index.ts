import { corsHeaders, isAllowedOrigin } from "../_shared/cors.ts";
import { verifyUserToken } from "../_shared/auth.ts";

const GEMINI_EMBED_URL =
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent";
const EMBEDDING_DIMENSIONS = 1536;
const MAX_QUESTION_LENGTH = 4000;

interface GeminiEmbedResponse {
  embedding?: {
    values?: unknown[];
  };
}

function jsonResponse(
  request: Request,
  body: Record<string, unknown>,
  status = 200,
): Response {
  const headers = corsHeaders(request);
  headers.set("Content-Type", "application/json; charset=utf-8");
  headers.set("X-Content-Type-Options", "nosniff");

  return new Response(JSON.stringify(body), { status, headers });
}

Deno.serve(async (request: Request): Promise<Response> => {
  const origin = request.headers.get("origin");
  if (!isAllowedOrigin(origin)) {
    return new Response(JSON.stringify({ error: "Origin not allowed." }), {
      status: 403,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Vary": "Origin",
      },
    });
  }

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders(request) });
  }

  if (request.method !== "POST") {
    return jsonResponse(request, { error: "Use POST for this endpoint." }, 405);
  }

  // Step 5 asks us to disable the gateway's legacy JWT check at deployment and
  // verify Supabase Auth tokens in the function instead.
  try {
    if (!await verifyUserToken(request)) {
      return jsonResponse(request, { error: "Sign in to use semantic search." }, 401);
    }
  } catch {
    return jsonResponse(
      request,
      { error: "Could not verify your Supabase session." },
      503,
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return jsonResponse(request, { error: "Request body must be valid JSON." }, 400);
  }

  const question = body && typeof body === "object"
    ? (body as Record<string, unknown>).question
    : undefined;
  if (typeof question !== "string" || question.trim().length === 0) {
    return jsonResponse(request, { error: "A non-empty question is required." }, 400);
  }

  const trimmedQuestion = question.trim();
  if (trimmedQuestion.length > MAX_QUESTION_LENGTH) {
    return jsonResponse(
      request,
      { error: `Question must be ${MAX_QUESTION_LENGTH} characters or fewer.` },
      413,
    );
  }

  const geminiApiKey = Deno.env.get("GEMINI_API_KEY");
  if (!geminiApiKey) {
    return jsonResponse(request, { error: "Gemini is not configured on the server." }, 500);
  }

  // Gemini Embedding 2 uses task instructions in the text prompt rather than
  // a task_type field. This query format matches the talk documents embedded
  // as "title: {title} | text: {sentence}" in the import pipeline.
  const queryText = `task: question answering | query: ${trimmedQuestion}`;

  let geminiResponse: Response;
  try {
    geminiResponse = await fetch(GEMINI_EMBED_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-goog-api-key": geminiApiKey,
      },
      body: JSON.stringify({
        content: { parts: [{ text: queryText }] },
        output_dimensionality: EMBEDDING_DIMENSIONS,
      }),
    });
  } catch {
    return jsonResponse(request, { error: "Could not reach the Gemini API." }, 502);
  }

  if (!geminiResponse.ok) {
    // Do not return Gemini's raw response; keep implementation details out of
    // the browser response and never log or expose the API key.
    const status = geminiResponse.status === 429 ? 429 : 502;
    return jsonResponse(
      request,
      { error: status === 429 ? "Gemini rate limit reached. Try again shortly." : "Gemini could not create an embedding." },
      status,
    );
  }

  let geminiData: GeminiEmbedResponse;
  try {
    geminiData = await geminiResponse.json() as GeminiEmbedResponse;
  } catch {
    return jsonResponse(request, { error: "Gemini returned an invalid response." }, 502);
  }

  const embedding = geminiData.embedding?.values;
  if (
    !Array.isArray(embedding) ||
    embedding.length !== EMBEDDING_DIMENSIONS ||
    !embedding.every((value) => typeof value === "number" && Number.isFinite(value))
  ) {
    return jsonResponse(request, { error: "Gemini returned an unexpected embedding." }, 502);
  }

  return jsonResponse(request, { embedding });
});
