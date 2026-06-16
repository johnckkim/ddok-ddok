// /api/watch-g2b — 나라장터(조달청) 입찰공고 키워드 모니터링 → Slack + Notion
//
// 동작:
//   1) Cron(또는 외부 스케줄러)이 이 함수를 호출 (하루 여러 번 가능)
//   2) 최근 N시간(기본 48h) 게시 공고를 키워드별로 조회 (data.go.kr 입찰공고정보서비스)
//   3) Notion DB에 공고번호로 이미 있는지 확인 → 신규만 골라
//   4) Notion '나라장터' DB에 정리 + Slack #나라장터 채널로 알림
//
// 중복 방지: Notion DB의 공고번호를 "이미 처리됨" 기록으로 사용(무상태 시간창의 중복 알림 문제 해결).
//   Notion 미설정 시 → 시간창 방식으로 fallback(하루 1회 실행 전제).
//
// 키워드 문법:
//   - 단일:  "키오스크"            → 공고명에 키오스크 포함
//   - AND:   "키오스크+유지보수"   → 공고명에 키오스크 '그리고' 유지보수 모두 포함
//
// 환경변수 (Vercel → Project Settings → Environment Variables):
//   DATA_GO_KR_KEY     [필수] 공공데이터포털 일반 인증키(Decoding). "나라장터 입찰공고정보서비스" 활용신청
//   SLACK_WEBHOOK_URL  [필수] #나라장터 채널용 Slack Incoming Webhook URL
//   WATCH_KEYWORDS     [선택] 쉼표구분 키워드(미설정 시 아래 기본값)
//   WATCH_CATEGORIES   [선택] thng,servc,cnstwk,frgcpt 중 선택(기본 전체)
//   WATCH_LOOKBACK_HOURS [선택] 조회 시간창(기본 48)
//   G2B_BASE_URL       [선택] 기본 https://apis.data.go.kr/1230000/ad/BidPublicInfoService
//   CRON_SECRET        [선택] 설정 시 요청 Authorization 헤더 검증
//   NOTION_TOKEN       [선택] Notion 내부 통합 시크릿(secret_xxx). 설정 시 Notion 정리 + 중복판별
//   NOTION_DATABASE_ID [선택] '나라장터' 데이터베이스 ID
//   NOTION_TITLE_PROP  [선택] Notion title 속성명(기본 "공고명")
//   NOTION_BIDNO_PROP  [선택] 공고번호 속성명(기본 "공고번호") — 중복판별 키
//
// 수동 테스트:
//   GET /api/watch-g2b?dry=1                  → Slack/Notion 미반영, 매칭 결과만 JSON
//   GET /api/watch-g2b?dry=1&keywords=키오스크 → 키워드 임시 지정

export const config = { runtime: "edge" };

const OPS = {
  thng:   "getBidPblancListInfoThng",   // 물품
  servc:  "getBidPblancListInfoServc",  // 용역
  cnstwk: "getBidPblancListInfoCnstwk", // 공사
  frgcpt: "getBidPblancListInfoFrgcpt", // 외자
};
const CAT_LABEL = { thng: "물품", servc: "용역", cnstwk: "공사", frgcpt: "외자" };

const DEFAULT_KEYWORDS = [
  "베리어프리", "대형폐기물", "키오스크", "무인배출신소시스템",
  "베리어프리+유지보수", "대형폐기물+유지보수", "키오스크+유지보수", "무인배출신소시스템+유지보수",
];

// Date → KST(UTC+9) "YYYYMMDDHHmm"
function kstStamp(date) {
  const kst = new Date(date.getTime() + 9 * 3600 * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${kst.getUTCFullYear()}${p(kst.getUTCMonth() + 1)}${p(kst.getUTCDate())}${p(kst.getUTCHours())}${p(kst.getUTCMinutes())}`;
}

function fmtDt(s) {
  if (!s) return "";
  const d = String(s).replace(/[^0-9]/g, "");
  if (d.length >= 12) return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)} ${d.slice(8,10)}:${d.slice(10,12)}`;
  if (d.length >= 8)  return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}`;
  return String(s);
}

function extractItems(data) {
  const items = data?.response?.body?.items;
  if (!items) return [];
  if (Array.isArray(items)) return items;
  if (Array.isArray(items.item)) return items.item;
  if (items.item) return [items.item];
  return [];
}

async function fetchG2B(base, key, cat, term, bgn, end) {
  const qs = new URLSearchParams({
    serviceKey: key, pageNo: "1", numOfRows: "200", type: "json",
    inqryDiv: "1", inqryBgnDt: bgn, inqryEndDt: end, bidNtceNm: term,
  }).toString();
  const url = `${base}/${OPS[cat]}?${qs}`;
  const r = await fetch(url, { headers: { "User-Agent": "ddok-ddok/watch-g2b" } });
  const text = await r.text();
  let data; try { data = JSON.parse(text); } catch { return { items: [], error: text.slice(0, 200), http: r.status }; }
  return { items: extractItems(data) };
}

// --- Notion ---
const NOTION_BASE = "https://api.notion.com/v1";
function notionHeaders(token) {
  return { "Authorization": `Bearer ${token}`, "Notion-Version": "2022-06-28", "Content-Type": "application/json" };
}
async function notionExists(token, dbId, bidnoProp, bidNo) {
  const r = await fetch(`${NOTION_BASE}/databases/${dbId}/query`, {
    method: "POST", headers: notionHeaders(token),
    body: JSON.stringify({ filter: { property: bidnoProp, rich_text: { equals: bidNo } }, page_size: 1 }),
  });
  if (!r.ok) return { exists: false, error: `query ${r.status}: ${(await r.text()).slice(0,200)}` };
  const j = await r.json();
  return { exists: (j.results || []).length > 0 };
}
async function notionCreate(token, dbId, titleProp, bidnoProp, m) {
  const rt = (v) => ({ rich_text: [{ text: { content: String(v || "").slice(0, 1900) } }] });
  const props = {
    [titleProp]: { title: [{ text: { content: (m.bidNtceNm || "(제목없음)").slice(0, 1900) } }] },
    [bidnoProp]: rt(`${m.bidNtceNo || ""}${m.bidNtceOrd ? "-" + m.bidNtceOrd : ""}`),
    "카테고리": { select: { name: CAT_LABEL[m._cat] || m._cat } },
    "기관": rt(m.ntceInsttNm || m.dminsttNm || ""),
    "키워드": { multi_select: (m._labels || []).slice(0, 10).map((n) => ({ name: n.slice(0, 90) })) },
    "게시일": rt(fmtDt(m.bidNtceDt)),
    "마감일": rt(fmtDt(m.bidClseDt)),
  };
  if (m.bidNtceUrl) props["링크"] = { url: m.bidNtceUrl };
  const r = await fetch(`${NOTION_BASE}/pages`, {
    method: "POST", headers: notionHeaders(token),
    body: JSON.stringify({ parent: { database_id: dbId }, properties: props }),
  });
  if (!r.ok) return { ok: false, error: `create ${r.status}: ${(await r.text()).slice(0,300)}` };
  return { ok: true };
}

function buildSlackText(items, lookbackH) {
  const lines = [`:loudspeaker: *나라장터 신규 공고 ${items.length}건* (최근 ${lookbackH}h)`, ""];
  for (const m of items.slice(0, 40)) {
    const title = m.bidNtceUrl ? `<${m.bidNtceUrl}|${m.bidNtceNm}>` : (m.bidNtceNm || "(제목없음)");
    lines.push(`• [${CAT_LABEL[m._cat] || m._cat}] ${title}  _(${(m._labels || []).join(", ")})_`);
    const meta = [];
    if (m.ntceInsttNm) meta.push(`기관: ${m.ntceInsttNm}`);
    if (m.bidNtceNo) meta.push(`공고: ${m.bidNtceNo}${m.bidNtceOrd ? "-" + m.bidNtceOrd : ""}`);
    if (m.bidClseDt) meta.push(`마감: ${fmtDt(m.bidClseDt)}`);
    if (meta.length) lines.push(`    ${meta.join(" · ")}`);
  }
  if (items.length > 40) lines.push(`\n…외 ${items.length - 40}건`);
  return lines.join("\n");
}

export default async function handler(req) {
  const reqUrl = new URL(req.url);
  const dry = reqUrl.searchParams.get("dry") === "1";

  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret && !dry) {
    if (req.headers.get("authorization") !== `Bearer ${cronSecret}`) {
      return new Response("Unauthorized", { status: 401 });
    }
  }

  const key = process.env.DATA_GO_KR_KEY;
  const webhook = process.env.SLACK_WEBHOOK_URL;
  const base = process.env.G2B_BASE_URL || "https://apis.data.go.kr/1230000/ad/BidPublicInfoService";
  const lookbackH = Number(process.env.WATCH_LOOKBACK_HOURS || 48);
  const notionToken = process.env.NOTION_TOKEN;
  const notionDb = process.env.NOTION_DATABASE_ID;
  const titleProp = process.env.NOTION_TITLE_PROP || "공고명";
  const bidnoProp = process.env.NOTION_BIDNO_PROP || "공고번호";

  const rawKeywords = (reqUrl.searchParams.get("keywords") || process.env.WATCH_KEYWORDS || "").trim();
  const keywords = rawKeywords ? rawKeywords.split(",").map(s => s.trim()).filter(Boolean) : DEFAULT_KEYWORDS;
  const cats = (process.env.WATCH_CATEGORIES || "thng,servc,cnstwk,frgcpt")
    .split(",").map(s => s.trim()).filter(c => OPS[c]);

  // 키워드 → AND 그룹. groups: [["베리어프리"], ["베리어프리","유지보수"], ...]
  const groups = keywords.map(k => k.split("+").map(s => s.trim()).filter(Boolean)).filter(g => g.length);
  const primaries = [...new Set(groups.map(g => g[0]))];

  const problems = [];
  if (!key) problems.push("DATA_GO_KR_KEY 미설정");
  if (!dry && !webhook && !(notionToken && notionDb)) problems.push("SLACK_WEBHOOK_URL 또는 NOTION 설정 필요");
  if (problems.length) {
    return new Response(JSON.stringify({ skipped: true, problems }), {
      status: 200, headers: { "Content-Type": "application/json" } });
  }

  const now = new Date();
  const end = kstStamp(now);
  const bgn = kstStamp(new Date(now.getTime() - lookbackH * 3600 * 1000));

  // 1) primary term × 카테고리 조회 → pool(공고번호 dedup)
  const pool = new Map();
  const errors = [];
  for (const term of primaries) {
    for (const cat of cats) {
      try {
        const { items, error, http } = await fetchG2B(base, key, cat, term, bgn, end);
        if (error) { errors.push({ term, cat, http, error }); continue; }
        for (const it of items) {
          const id = `${cat}:${it.bidNtceNo || ""}-${it.bidNtceOrd || ""}`;
          if (!pool.has(id)) pool.set(id, { ...it, _cat: cat });
        }
      } catch (e) { errors.push({ term, cat, error: e.message }); }
    }
  }

  // 2) 키워드 그룹 매칭(공고명 기준 AND) → 라벨 부착
  const matched = [];
  for (const m of pool.values()) {
    const title = String(m.bidNtceNm || "");
    const labels = groups.filter(g => g.every(part => title.includes(part)))
      .map(g => g.join(" "));
    if (labels.length) matched.push({ ...m, _labels: labels });
  }

  const summary = { window: { bgn, end }, keywords, cats, scanned: pool.size, matched: matched.length, errors };

  if (dry) {
    return new Response(JSON.stringify({ ...summary, matches: matched }, null, 2), {
      headers: { "Content-Type": "application/json" } });
  }

  // 3) 신규만 선별(Notion 중복판별) + Notion 기록
  const useNotion = !!(notionToken && notionDb);
  const fresh = [];
  for (const m of matched.slice(0, 80)) {
    const bidNo = `${m.bidNtceNo || ""}${m.bidNtceOrd ? "-" + m.bidNtceOrd : ""}`;
    if (useNotion) {
      const ex = await notionExists(notionToken, notionDb, bidnoProp, bidNo);
      if (ex.error) { errors.push({ notion: "exists", error: ex.error }); }
      if (ex.exists) continue; // 이미 처리됨 → 스킵
    }
    fresh.push(m);
    if (useNotion) {
      const cr = await notionCreate(notionToken, notionDb, titleProp, bidnoProp, m);
      if (!cr.ok) errors.push({ notion: "create", bidNo, error: cr.error });
    }
  }
  summary.new = fresh.length;
  summary.notion = useNotion ? "on" : "off";

  // 4) Slack 알림(신규만)
  if (webhook && fresh.length) {
    const sr = await fetch(webhook, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: buildSlackText(fresh, lookbackH) }),
    });
    summary.slack = { ok: sr.ok, status: sr.status };
  } else {
    summary.slack = webhook ? "no new items" : "webhook off";
  }

  return new Response(JSON.stringify(summary), { headers: { "Content-Type": "application/json" } });
}
