// /api/moj — 법무부 대표 홈페이지 인기검색어 (data.go.kr/15126815)
// 검증된 실제 endpoint: apis.data.go.kr/1270000/lawyerdataApi/key_word
// 최근 7일간 검색된 인기 검색어 상위 100개 반환
export const config = { runtime: "edge" };

export default async function handler(req) {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const apiKey = process.env.DATA_GO_KR_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({
      error: "DATA_GO_KR_KEY env not set",
      results: []
    }), { status: 200, headers: { "Content-Type": "application/json" }});
  }
  const { pageNo = 1, numOfRows = 20 } = await req.json().catch(() => ({}));
  const params = new URLSearchParams({
    serviceKey: apiKey,
    pageNo: String(pageNo),
    numOfRows: String(numOfRows),
    type: "json"
  });
  const url = `https://apis.data.go.kr/1270000/lawyerdataApi/key_word?${params}`;
  try {
    const r = await fetch(url, { headers: { "User-Agent": "LawSkill/2.4" } });
    const text = await r.text();
    let data; try { data = JSON.parse(text); } catch { data = { _raw: text.slice(0,300) }; }
    return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" }});
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), { status: 500 });
  }
}
