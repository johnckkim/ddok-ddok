// /api/interpretation — 부처별 법령 해석례 통합 (국세청·국토부·고용부 + 법제처)
// LINK형 — open.law.go.kr 직접 호출 (국가법령정보 DRF)
//
// 인증 상태(2026-05-07 검증):
//   OC=kibie 는 target=law (법령) / target=prec (판례) 두 종류만 인증됨.
//   target=expc (법령해석례), target=ntsCgmExpc (국세청), target=molitCgmExpc(국토부),
//   target=moelCgmExpc (고용부), target=licbyl (행정해석), target=admrul (행정규칙) 은
//   별도로 open.law.go.kr 에 IP/도메인 등록이 필요 — kibie 는 미인증.
//
// 동작:
//   1) 인증 가능한 target (law/prec) 은 정상 프록시
//   2) 미인증 target 은 명확한 안내 메시지 반환 (mock 아님 — 실제 등록 안내)
export const config = { runtime: "edge" };

const AGENCY_TO_TARGET = {
  국세청: "ntsCgmExpc",
  국세: "ntsCgmExpc",
  세무: "ntsCgmExpc",
  세법: "ntsCgmExpc",
  국토교통부: "molitCgmExpc",
  국토부: "molitCgmExpc",
  부동산: "molitCgmExpc",
  건축: "molitCgmExpc",
  고용노동부: "moelCgmExpc",
  고용부: "moelCgmExpc",
  노동: "moelCgmExpc",
  근로: "moelCgmExpc",
  법제처: "expc"
};

const AUTHENTICATED_TARGETS = new Set(["law", "prec"]);

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

  // Determine target
  let target = targetIn;
  if (!target) {
    target = AGENCY_TO_TARGET[agency] || "expc";
  }

  // If specialized target not authenticated → informative skip
  if (!AUTHENTICATED_TARGETS.has(target)) {
    return new Response(JSON.stringify({
      skipped: true,
      reason: `target=${target} 은 OC=${oc} 로 미인증`,
      hint: "open.law.go.kr 에서 별도 IP/도메인 등록 후 사용 가능. 또는 target=law (법령) / target=prec (판례) 사용",
      authenticated_targets: Array.from(AUTHENTICATED_TARGETS),
      results: []
    }), { status: 200, headers: { "Content-Type": "application/json" }});
  }

  // Authenticated target — call DRF
  const params = new URLSearchParams({
    OC: oc,
    target,
    type: "JSON",
    query,
    display: String(display),
    page: String(page)
  });
  const url = `https://www.law.go.kr/DRF/lawSearch.do?${params}`;
  try {
    const r = await fetch(url, { headers: { "User-Agent": "LawSkill/2.3" } });
    const text = await r.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { _raw: text.slice(0, 500), _http: r.status }; }
    if (data.result && data.msg) {
      return new Response(JSON.stringify({ error: data.msg, _result: data.result, results: [] }), {
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
