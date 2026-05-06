// /api/interpretation — 법령해석례 + 부처별 해석례 통합 (국가법령정보공동활용 API)
// OC=kibie + Referer 헤더 = 모든 DRF target 작동 검증됨 (2026-05-07)
//
// 지원 target:
//   law          — 법령
//   prec         — 판례
//   detc         — 헌재 결정문
//   expc         — 법령해석례 (법제처 + 부처 통합)
//   ntsCgmExpc   — 국세청 해석례
//   molitCgmExpc — 국토교통부 해석례
//   moelCgmExpc  — 고용노동부 해석례
//   licbyl       — 행정해석 (별표·서식)
//   admrul       — 행정규칙
//   ordin        — 자치법규
//   trty         — 조약
export const config = { runtime: "edge" };

const AGENCY_TO_TARGET = {
  국세청: "ntsCgmExpc", 국세: "ntsCgmExpc", 세무: "ntsCgmExpc", 세법: "ntsCgmExpc",
  국토교통부: "molitCgmExpc", 국토부: "molitCgmExpc", 부동산: "molitCgmExpc", 건축: "molitCgmExpc",
  고용노동부: "moelCgmExpc", 고용부: "moelCgmExpc", 노동: "moelCgmExpc", 근로: "moelCgmExpc",
  법제처: "expc"
};

export default async function handler(req) {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const oc = process.env.LAW_GO_KR_OC || "kibie";
  const body = await req.json().catch(() => ({}));
  const { query = "", target: targetIn, agency = "", display = 5, page = 1 } = body;

  if (!query) {
    return new Response(JSON.stringify({ error: "query required", results: [] }), {
      status: 400, headers: { "Content-Type": "application/json" }
    });
  }

  // target 결정: target 명시 → agency 매핑 → 기본 expc(통합 법령해석례)
  const target = targetIn || AGENCY_TO_TARGET[agency] || "expc";

  const params = new URLSearchParams({
    OC: oc, target, type: "JSON", query,
    display: String(display), page: String(page)
  });
  const url = `https://www.law.go.kr/DRF/lawSearch.do?${params}`;
  try {
    const r = await fetch(url, {
      headers: { "User-Agent": "LawSkill/2.4", "Referer": "https://www.law.go.kr/" }
    });
    const text = await r.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { _raw: text.slice(0, 500), _http: r.status }; }
    if (data.result && data.msg) {
      return new Response(JSON.stringify({ error: data.msg, _result: data.result, results: [] }), {
        status: 200, headers: { "Content-Type": "application/json" }
      });
    }
    return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message, results: [] }), {
      status: 500, headers: { "Content-Type": "application/json" }
    });
  }
}
