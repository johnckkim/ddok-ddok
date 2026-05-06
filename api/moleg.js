// /api/moleg — 법제처 입법예고 (공식 OpenAPI 미공개)
// 대안: data.go.kr "법제처_입법예고고시정보" 데이터셋 또는 RSS
// 현재 실연동 가능한 endpoint 미확인 — 사용자가 키 발급 후 구체 endpoint 지정 시 활성화
export const config = { runtime: "edge" };
export default async function handler(req) {
  return new Response(JSON.stringify({
    error: "법제처 입법예고 공식 OpenAPI 미공개",
    hint: "data.go.kr에서 '법제처_입법예고' 또는 '국가법령정보 입법예고' 데이터셋 활용신청 후, /api/datagovkr 사용 권장",
    suggested_dataset: "data.go.kr 검색: '입법예고'",
    results: []
  }), {
    status: 200, headers: { "Content-Type": "application/json" }
  });
}
