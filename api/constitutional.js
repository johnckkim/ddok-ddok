// /api/constitutional — 헌법재판소 판례정보 조회 (data.go.kr 15141085)
// Base: https://apis.data.go.kr/9750000/PrecedentInfomationService
export const config = { runtime: "edge" };

export default async function handler(req) {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const apiKey = process.env.DATA_GO_KR_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({ error: "DATA_GO_KR_KEY env not set", results: [] }), {
      status: 200, headers: { "Content-Type": "application/json" }
    });
  }
  const body = await req.json().catch(() => ({}));
  const {
    query = "",
    op = "getKorPrcdntList",
    numOfRows = 5,
    pageNo = 1,
    eventType,
    rstaResult,
    rstaStartDate,
    rstaEndDate
  } = body;

  const allowedOps = new Set([
    "getKorPrcdntList", "getKorPrcdntDetail",
    "getRealmMainPrcdntList", "getRealmMainPrcdntDetail",
    "getOcprPrcdntList", "getOcprOutlineList", "getOcprOutlineDetail",
    "getEngPrcdntList", "getEngPrcdntDetail"
  ]);
  if (!allowedOps.has(op)) {
    return new Response(JSON.stringify({ error: `unsupported op: ${op}` }), {
      status: 400, headers: { "Content-Type": "application/json" }
    });
  }

  const params = new URLSearchParams({
    serviceKey: apiKey,
    type: "json",
    numOfRows: String(numOfRows),
    pageNo: String(pageNo)
  });
  if (query) params.set("eventNm", query);
  if (eventType) params.set("eventType", eventType);
  if (rstaResult) params.set("rstaResult", rstaResult);
  if (rstaStartDate) params.set("rstaStartDate", rstaStartDate);
  if (rstaEndDate) params.set("rstaEndDate", rstaEndDate);

  const url = `https://apis.data.go.kr/9750000/PrecedentInfomationService/${op}?${params}`;
  try {
    const r = await fetch(url, { headers: { "User-Agent": "LawSkill/2.3" } });
    const text = await r.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { _raw: text.slice(0, 500), _http: r.status }; }
    return new Response(JSON.stringify(data), {
      headers: { "Content-Type": "application/json" }
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message, results: [] }), {
      status: 500, headers: { "Content-Type": "application/json" }
    });
  }
}
