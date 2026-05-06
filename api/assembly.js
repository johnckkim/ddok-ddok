// /api/assembly — 열린국회정보 의안 검색 proxy
// 22대 국회 의안 목록 (이름·발의자·심사 진행)
export const config = { runtime: "edge" };
export default async function handler(req) {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const apiKey = process.env.ASSEMBLY_API_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({ error: "ASSEMBLY_API_KEY env not set", results: [] }), {
      status: 200, headers: { "Content-Type": "application/json" }
    });
  }
  const { keyword = "", age = 22, pSize = 5 } = await req.json();
  // BILL_NAME 컬럼에 keyword 부분일치
  const url = `https://open.assembly.go.kr/portal/openapi/nzmimeepazxkubdpn?KEY=${apiKey}&Type=json&pIndex=1&pSize=${pSize}&AGE=${age}` +
    (keyword ? `&BILL_NAME=${encodeURIComponent(keyword)}` : "");
  try {
    const r = await fetch(url, { headers: { "User-Agent": "LawSkill/2.3" } });
    const text = await r.text();
    let data; try { data = JSON.parse(text); } catch { data = { _raw: text.slice(0,300) }; }
    return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" }});
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message, results: [] }), { status: 500 });
  }
}
