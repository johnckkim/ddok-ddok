// /api/cdc — 헌법재판소 판례정보 조회 alias (실제 path: /api/constitutional)
// data.go.kr/15141085 → apis.data.go.kr/9750000/PrecedentInfomationService
// 검증된 실제 endpoint 사용 (2026-05-07)
export const config = { runtime: "edge" };

export default async function handler(req) {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const apiKey = process.env.DATA_GO_KR_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({
      error: "DATA_GO_KR_KEY env not set",
      hint: "data.go.kr 인증키를 Vercel 환경변수에 등록",
      results: []
    }), { status: 200, headers: { "Content-Type": "application/json" }});
  }
  const { keyword = "", query = "", pageNo = 1, numOfRows = 5 } = await req.json().catch(() => ({}));
  const eventNm = keyword || query || "";
  const params = new URLSearchParams({
    serviceKey: apiKey,
    type: "json",
    numOfRows: String(numOfRows),
    pageNo: String(pageNo)
  });
  if (eventNm) params.set("eventNm", eventNm);
  const url = `https://apis.data.go.kr/9750000/PrecedentInfomationService/getKorPrcdntList?${params}`;
  try {
    const r = await fetch(url, { headers: { "User-Agent": "LawSkill/2.4" } });
    const text = await r.text();
    let data; try { data = JSON.parse(text); } catch { data = { _raw: text.slice(0,300) }; }
    return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" }});
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message, results: [] }), { status: 500 });
  }
}
