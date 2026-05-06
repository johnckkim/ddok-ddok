// /api/crime — 한국형사법무정책연구원 범죄통계 alias (실제 path: /api/crime-stats)
// data.go.kr/15140047 → apis.data.go.kr/B554626/CrimeStatistics
// 주의: getCrimeStatistics 는 sht(표코드)+statsYr 둘 다 필수. 미지정시 안내 응답.
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
  const body = await req.json().catch(() => ({}));
  const { sht, statsYr, year, artcl, clsf } = body;
  const yr = statsYr || year;
  if (!sht || !yr) {
    return new Response(JSON.stringify({
      skipped: true,
      reason: "sht(표코드) + statsYr(통계연도) 둘 다 필수 — 미지정",
      hint: "예: { sht: '107000_001', statsYr: '2023' }. sht 카탈로그는 data.go.kr/data/15140047 명세 참조."
    }), { headers: { "Content-Type": "application/json" }});
  }
  const params = new URLSearchParams({
    serviceKey: apiKey, type: "json",
    sht: String(sht), statsYr: String(yr)
  });
  if (artcl) params.set("artcl", String(artcl));
  if (clsf) params.set("clsf", String(clsf));
  const url = `https://apis.data.go.kr/B554626/CrimeStatistics/getCrimeStatistics?${params}`;
  try {
    const r = await fetch(url, { headers: { "User-Agent": "LawSkill/2.4" } });
    const text = await r.text();
    let data; try { data = JSON.parse(text); } catch { data = { _raw: text.slice(0,300) }; }
    return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" }});
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), { status: 500 });
  }
}
