// /api/interpretation — 부처별 법령 해석례 통합 (국세청·국토부·고용부 + 법제처)
// LINK형 — open.law.go.kr 직접 호출 (국가법령정보 DRF, OC=kibie 사용)
// target 옵션:
//   expc  — 법령해석례 (법제처 + 각 부처 통합)
//   licbyl — 행정해석 (각 행정부처)
//   admrul — 행정규칙
// 부처 필터(orgCls)로 국세청·국토부·고용부 등 세분화 가능.
export const config = { runtime: "edge" };

const TARGET_BY_AGENCY = {
  // 부처 키 → DRF 검색용 부처명 (법령해석례 검색 시 검색어로 결합)
  국세청: "국세청",
  국세: "국세청",
  세무: "국세청",
  세법: "국세청",
  국토교통부: "국토교통부",
  국토부: "국토교통부",
  부동산: "국토교통부",
  건축: "국토교통부",
  고용노동부: "고용노동부",
  고용부: "고용노동부",
  노동: "고용노동부",
  근로: "고용노동부",
  법제처: "법제처"
};

export default async function handler(req) {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const oc = process.env.LAW_GO_KR_OC || "kibie";
  const body = await req.json().catch(() => ({}));
  const {
    query = "",
    target = "expc", // expc | licbyl | admrul
    agency = "",     // 국세청 | 국토교통부 | 고용노동부 | 법제처 | "" (전체)
    display = 5,
    page = 1
  } = body;

  if (!query) {
    return new Response(JSON.stringify({ error: "query required", results: [] }), {
      status: 400, headers: { "Content-Type": "application/json" }
    });
  }

  // 부처 필터링: 검색어에 부처명을 prefix로 추가하면 정확도 향상
  const agencyName = TARGET_BY_AGENCY[agency] || agency || "";
  const finalQuery = agencyName ? `${agencyName} ${query}` : query;

  const params = new URLSearchParams({
    OC: oc,
    target,
    type: "JSON",
    query: finalQuery,
    display: String(display),
    page: String(page)
  });
  const url = `https://www.law.go.kr/DRF/lawSearch.do?${params}`;
  try {
    const r = await fetch(url, { headers: { "User-Agent": "LawSkill/2.3" } });
    const text = await r.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { _raw: text.slice(0, 500), _http: r.status }; }
    if (data.result && (data.msg || String(data.result).startsWith("필수입력"))) {
      return new Response(JSON.stringify({ error: data.msg || "OC 미인증", results: [] }), {
        status: 200, headers: { "Content-Type": "application/json" }
      });
    }
    return new Response(JSON.stringify(data), {
      headers: { "Content-Type": "application/json" }
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message, results: [] }), {
      status: 500, headers: { "Content-Type": "application/json" }
    });
  }
}
