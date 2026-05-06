// /api/crime-stats — 한국형사법무정책연구원 범죄통계정보조회 (data.go.kr 15140047)
// Base: https://apis.data.go.kr/B554626/CrimeStatistics
// 주의: sht(표코드)와 statsYr(통계연도) 둘 다 필수.
//   sht 코드 카탈로그는 별도 명세에 있어, 호출자가 지정해야 함.
//   호출자가 sht/statsYr 미지정 시 명세 안내 응답 반환(에러 아님).
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
  const { sht, statsYr, artcl, clsf } = body;

  if (!sht || !statsYr) {
    return new Response(JSON.stringify({
      skipped: true,
      reason: "sht(표코드) + statsYr(통계연도) 둘 다 필수 — 미지정",
      hint: "예: { sht: \"107000_001\", statsYr: \"2023\" } 형식으로 호출. sht 카탈로그는 data.go.kr/data/15140047 참고문서 참조."
    }), { status: 200, headers: { "Content-Type": "application/json" }});
  }

  const params = new URLSearchParams({
    serviceKey: apiKey,
    type: "json",
    sht: String(sht),
    statsYr: String(statsYr)
  });
  if (artcl) params.set("artcl", String(artcl));
  if (clsf) params.set("clsf", String(clsf));

  const url = `https://apis.data.go.kr/B554626/CrimeStatistics/getCrimeStatistics?${params}`;
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
