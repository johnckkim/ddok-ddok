// /api/verify — DeepSeek 검증 proxy
export const config = { runtime: "edge" };
export default async function handler(req) {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const apiKey = process.env.DEEPSEEK_API_KEY;
  if (!apiKey) return new Response(JSON.stringify({ content: "(DeepSeek 키 미설정)", skipped: true }), { status: 200, headers:{"Content-Type":"application/json"}});
  const { content } = await req.json();
  const upstream = await fetch("https://api.deepseek.com/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + apiKey },
    body: JSON.stringify({
      model: "deepseek-chat",
      messages: [
        { role: "system", content: "한국 법률 검증자. 간결." },
        { role: "user", content: `다음 답변의 논리 결함·인용 오류 점검 (300토큰):\n${content.slice(0,2500)}` }
      ],
      max_tokens: 500, temperature: 0.2
    })
  });
  if (!upstream.ok) return new Response(JSON.stringify({ error: "DeepSeek "+upstream.status }), { status: upstream.status });
  const data = await upstream.json();
  return new Response(JSON.stringify({ content: data.choices[0].message.content }), { headers: {"Content-Type":"application/json"}});
}
