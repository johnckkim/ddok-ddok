// /api/classify — DeepSeek-chat proxy (질문 분류)
export const config = { runtime: "edge" };
export default async function handler(req) {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const apiKey = process.env.DEEPSEEK_API_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({ error: "DEEPSEEK_API_KEY env not set" }), {
      status: 500, headers: { "Content-Type": "application/json" }
    });
  }
  const body = await req.json();
  const { question } = body;
  const upstream = await fetch("https://api.deepseek.com/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + apiKey },
    body: JSON.stringify({
      model: "deepseek-chat",
      messages: [
        { role: "system", content: "한국 법률 분류기. JSON만. 키: domain(민사/형사/행정/노동/가사/상사/헌법/기타), keywords(string[]), intent_type(정의조회/사례분석/절차안내)." },
        { role: "user", content: question }
      ],
      max_tokens: 300, temperature: 0.1
    })
  });
  if (!upstream.ok) {
    return new Response(JSON.stringify({ error: "DeepSeek " + upstream.status }), { status: upstream.status });
  }
  const data = await upstream.json();
  return new Response(JSON.stringify({ content: data.choices[0].message.content }), {
    headers: { "Content-Type": "application/json" }
  });
}
