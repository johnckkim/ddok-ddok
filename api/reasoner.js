// /api/reasoner — DeepSeek-reasoner proxy (딥씽크)
export const config = { runtime: "edge" };
export default async function handler(req) {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const apiKey = process.env.DEEPSEEK_API_KEY;
  if (!apiKey) return new Response(JSON.stringify({ content: "", reasoning: "", skipped: true }), { status: 200, headers:{"Content-Type":"application/json"}});
  const { question } = await req.json();
  const upstream = await fetch("https://api.deepseek.com/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + apiKey },
    body: JSON.stringify({
      model: "deepseek-reasoner",
      messages: [
        { role: "system", content: "한국 법률 전문가. 단계별 깊이 사고 후 답변." },
        { role: "user", content: question }
      ],
      max_tokens: 4096
    })
  });
  if (!upstream.ok) return new Response(JSON.stringify({ error: "Reasoner "+upstream.status }), { status: upstream.status });
  const data = await upstream.json();
  const msg = data.choices[0].message;
  return new Response(JSON.stringify({ content: msg.content||"", reasoning: msg.reasoning_content||"" }), { headers: {"Content-Type":"application/json"}});
}
