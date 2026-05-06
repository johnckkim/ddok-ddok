// /api/court — 대법원 사법정보공유포털 (openapi.scourt.go.kr)
// 자격 요건: 변호사·법무사 등 자격 인증 필요 → 일반 사용자 회원가입 불가
// 현 상태: 키 발급 불가 → 미연동
// 대안: law.go.kr DRF target=prec (이미 연동됨)
export const config = { runtime: "edge" };
export default async function handler(req) {
  return new Response(JSON.stringify({
    error: "대법원 사법정보공유포털은 변호사 자격 등 인증 필요",
    hint: "/api/lawsearch (target=prec) 사용 — law.go.kr DRF로 동일 판례 검색 가능",
    fallback: "/api/lawsearch",
    results: []
  }), {
    status: 200, headers: { "Content-Type": "application/json" }
  });
}
