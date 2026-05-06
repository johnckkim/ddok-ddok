// /api/chat — Anthropic Claude streaming proxy (Vercel Edge Function)
// Hides ANTHROPIC_API_KEY from client. Streams SSE to browser.
export const config = { runtime: "edge" };

export default async function handler(req) {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({ error: "ANTHROPIC_API_KEY env not set" }), {
      status: 500, headers: { "Content-Type": "application/json" }
    });
  }
  let body;
  try { body = await req.json(); } catch {
    return new Response("Invalid JSON", { status: 400 });
  }
  const { messages, system, model = "claude-opus-4-6", max_tokens = 4096, temperature = 0.2, stream = true } = body;

  const upstream = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01"
    },
    body: JSON.stringify({ model, max_tokens, system, messages, temperature, stream })
  });

  if (!upstream.ok) {
    const txt = await upstream.text();
    return new Response(JSON.stringify({ error: `Anthropic ${upstream.status}: ${txt.slice(0,300)}` }), {
      status: upstream.status, headers: { "Content-Type": "application/json" }
    });
  }
  // pass-through stream
  return new Response(upstream.body, {
    headers: {
      "Content-Type": stream ? "text/event-stream" : "application/json",
      "Cache-Control": "no-cache, no-transform",
      "Connection": "keep-alive"
    }
  });
}
