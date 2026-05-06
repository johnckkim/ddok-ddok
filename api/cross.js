// /api/cross — Grok 교차 검증 proxy
export const config = { runtime: "edge" };
export default async function handler(req) {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const apiKey = process.env.GROK_API_KEY;
  if (!apiKey) return new Response(JSON.stringify({ content: "(Grok 키 미설정)", skipped: true }), { status: 200, headers:{"Content-Type":"application/json"}});
  const { content } = await req.json();
  const upstream = await fetch("https://api.x.ai/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + apiKey },
    body: JSON.stringify({
      model: "grok-4-fast",
      messages: [
        { role: "system", content: "한국 법률 교차검증자. 200토큰 한국어." },
        { role: "user", content: `검증 (200토큰):\n${content.slice(0,1200)}` }
      ],
      max_tokens: 400, temperature: 0.2
    })
  });
  if (!upstream.ok) return new Response(JSON.stringify({ error: "Grok "+upstream.status }), { status: upstream.status });
  const data = await upstream.json();
  return new Response(JSON.stringify({ content: data.choices[0].message.content }), { headers: {"Content-Type":"application/json"}});
}
