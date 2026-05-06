// /api/datagovkr — 공공데이터포털 통합 proxy
// 법률 관련 데이터셋(통계·범죄·소송) 호출
// 데이터셋 ID + endpoint 지정 → serviceKey로 호출
export const config = { runtime: "edge" };
export default async function handler(req) {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const apiKey = process.env.DATA_GO_KR_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({
      error: "DATA_GO_KR_KEY env not set",
      hint: "공공데이터포털(data.go.kr) → 데이터셋 활용신청 후 키 발급 → Vercel 환경변수 등록",
      results: []
    }), { status: 200, headers: { "Content-Type": "application/json" }});
  }
  const { dataset, endpoint, params = {} } = await req.json();
  if (!dataset || !endpoint) {
    return new Response(JSON.stringify({ error: "dataset, endpoint required" }), { status: 400 });
  }
  // apis.data.go.kr/<dataset>/<endpoint>?serviceKey=...
  const qs = new URLSearchParams({ serviceKey: apiKey, returnType: "JSON", ...params }).toString();
  const url = `https://apis.data.go.kr/${dataset}/${endpoint}?${qs}`;
  try {
    const r = await fetch(url, { headers: { "User-Agent": "LawSkill/2.3" } });
    const text = await r.text();
    let data; try { data = JSON.parse(text); } catch { data = { _raw: text.slice(0,300) }; }
    return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" }});
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message, results: [] }), { status: 500 });
  }
}
