// /api/lawsearch — law.go.kr DRF proxy (CORS 우회)
export const config = { runtime: "edge" };
export default async function handler(req) {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const oc = process.env.LAW_GO_KR_OC || "kibie";
  const { target = "law", query = "", display = 5 } = await req.json();
  const url = `https://www.law.go.kr/DRF/lawSearch.do?OC=${oc}&target=${target}&type=JSON&query=${encodeURIComponent(query)}&display=${display}`;
  try {
    const r = await fetch(url, { headers: { "User-Agent": "LawSkill/2.3", "Referer": "https://www.law.go.kr/" } });
    const text = await r.text();
    let data; try { data = JSON.parse(text); } catch { data = { _raw: text.slice(0,300) }; }
    return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" }});
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), { status: 500 });
  }
}
