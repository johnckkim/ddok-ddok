// /api/watch-g2b — 나라장터(조달청) 입찰공고 키워드 모니터링 → Slack 알림
//
// 동작:
//   1) Vercel Cron 이 매일 이 함수를 호출 (vercel.json 의 crons 참조)
//   2) 최근 N시간(기본 24h) 게시된 공고를 키워드별로 조회 (data.go.kr 입찰공고정보서비스)
//   3) 매칭된 공고를 Slack Incoming Webhook 으로 전송
//
// 중복 방지: 별도 저장소 없이 "최근 N시간 게시분"만 조회하는 시간창 방식.
//   매일 같은 시각에 1회 실행 전제. (WATCH_LOOKBACK_HOURS 로 겹침 조절)
//
// 필요한 환경변수 (Vercel → Project Settings → Environment Variables):
//   DATA_GO_KR_KEY     공공데이터포털 일반 인증키(Decoding). "입찰공고정보서비스" 활용신청 필요
//   SLACK_WEBHOOK_URL  Slack Incoming Webhook URL
//   WATCH_KEYWORDS     쉼표로 구분한 키워드. 예: "인공지능,데이터 구축,LLM"
// 선택 환경변수:
//   WATCH_CATEGORIES   조회 대상. thng(물품),servc(용역),cnstwk(공사),frgcpt(외자) 중 쉼표구분. 기본 전체
//   WATCH_LOOKBACK_HOURS  조회 시간창(시간). 기본 24
//   G2B_BASE_URL       입찰공고정보서비스 베이스 URL. 기본 http://apis.data.go.kr/1230000/ad/BidPublicInfoService
//   CRON_SECRET        설정 시 Vercel Cron 요청의 Authorization 헤더 검증
//
// 수동 테스트:
//   GET /api/watch-g2b?dry=1            → Slack 미전송, 매칭 결과만 JSON 반환
//   GET /api/watch-g2b?dry=1&keywords=인공지능,데이터  → 키워드 임시 지정

export const config = { runtime: "edge" };

const OPS = {
  thng:   "getBidPblancListInfoThng",   // 물품
  servc:  "getBidPblancListInfoServc",  // 용역
  cnstwk: "getBidPblancListInfoCnstwk", // 공사
  frgcpt: "getBidPblancListInfoFrgcpt", // 외자
};
const CAT_LABEL = { thng: "물품", servc: "용역", cnstwk: "공사", frgcpt: "외자" };

// Date → KST(UTC+9) "YYYYMMDDHHmm"
function kstStamp(date) {
  const kst = new Date(date.getTime() + 9 * 3600 * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${kst.getUTCFullYear()}${p(kst.getUTCMonth() + 1)}${p(kst.getUTCDate())}${p(kst.getUTCHours())}${p(kst.getUTCMinutes())}`;
}

// 응답에서 공고 배열 정규화 (items 가 배열 / {item:[...]} / 단일객체 모두 대응)
function extractItems(data) {
  const items = data?.response?.body?.items;
  if (!items) return [];
  if (Array.isArray(items)) return items;
  if (Array.isArray(items.item)) return items.item;
  if (items.item) return [items.item];
  return [];
}

function fmtDt(s) {
  // "202606160930" 또는 "2026-06-16 09:30" 형태 → 보기 좋게
  if (!s) return "";
  const d = String(s).replace(/[^0-9]/g, "");
  if (d.length >= 12) return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)} ${d.slice(8,10)}:${d.slice(10,12)}`;
  return String(s);
}

async function fetchForKeyword(base, key, cat, keyword, bgn, end) {
  const op = OPS[cat];
  const qs = new URLSearchParams({
    serviceKey: key,
    pageNo: "1",
    numOfRows: "200",
    type: "json",
    inqryDiv: "1",        // 1 = 공고게시일시 기준
    inqryBgnDt: bgn,      // YYYYMMDDHHmm
    inqryEndDt: end,
    bidNtceNm: keyword,   // 공고명 키워드 (부분일치)
  }).toString();
  const url = `${base}/${op}?${qs}`;
  const r = await fetch(url, { headers: { "User-Agent": "ddok-ddok/watch-g2b" } });
  const text = await r.text();
  let data;
  try { data = JSON.parse(text); } catch { return { items: [], error: text.slice(0, 200), http: r.status }; }
  return { items: extractItems(data), raw: data };
}

function buildSlackText(matches, keywords, lookbackH) {
  const lines = [
    `:loudspeaker: *나라장터 신규 공고 ${matches.length}건* — 키워드: ${keywords.map(k => "`" + k + "`").join(", ")} (최근 ${lookbackH}h)`,
    "",
  ];
  for (const m of matches.slice(0, 40)) {
    const title = m.bidNtceUrl ? `<${m.bidNtceUrl}|${m.bidNtceNm}>` : (m.bidNtceNm || "(제목없음)");
    lines.push(`• [${CAT_LABEL[m._cat] || m._cat}] ${title}`);
    const meta = [];
    if (m.ntceInsttNm) meta.push(`기관: ${m.ntceInsttNm}`);
    if (m.bidNtceNo) meta.push(`공고번호: ${m.bidNtceNo}${m.bidNtceOrd ? "-" + m.bidNtceOrd : ""}`);
    if (m.bidClseDt) meta.push(`마감: ${fmtDt(m.bidClseDt)}`);
    if (meta.length) lines.push(`    ${meta.join(" · ")}`);
  }
  if (matches.length > 40) lines.push(`\n…외 ${matches.length - 40}건`);
  return lines.join("\n");
}

export default async function handler(req) {
  const reqUrl = new URL(req.url);
  const dry = reqUrl.searchParams.get("dry") === "1";

  // Vercel Cron 보호 (CRON_SECRET 설정 시에만 검증; 수동 dry 테스트는 통과)
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret && !dry) {
    const auth = req.headers.get("authorization");
    if (auth !== `Bearer ${cronSecret}`) {
      return new Response("Unauthorized", { status: 401 });
    }
  }

  const key = process.env.DATA_GO_KR_KEY;
  const webhook = process.env.SLACK_WEBHOOK_URL;
  const base = process.env.G2B_BASE_URL || "http://apis.data.go.kr/1230000/ad/BidPublicInfoService";
  const lookbackH = Number(process.env.WATCH_LOOKBACK_HOURS || 24);

  const keywords = (reqUrl.searchParams.get("keywords") || process.env.WATCH_KEYWORDS || "")
    .split(",").map(s => s.trim()).filter(Boolean);
  const cats = (process.env.WATCH_CATEGORIES || "thng,servc,cnstwk,frgcpt")
    .split(",").map(s => s.trim()).filter(c => OPS[c]);

  const problems = [];
  if (!key) problems.push("DATA_GO_KR_KEY 미설정");
  if (!keywords.length) problems.push("WATCH_KEYWORDS 미설정");
  if (!dry && !webhook) problems.push("SLACK_WEBHOOK_URL 미설정");
  if (problems.length) {
    return new Response(JSON.stringify({ skipped: true, problems }), {
      status: 200, headers: { "Content-Type": "application/json" },
    });
  }

  const now = new Date();
  const end = kstStamp(now);
  const bgn = kstStamp(new Date(now.getTime() - lookbackH * 3600 * 1000));

  // 키워드 × 카테고리 조회, 공고번호로 dedup
  const seen = new Set();
  const matches = [];
  const errors = [];
  for (const kw of keywords) {
    for (const cat of cats) {
      try {
        const { items, error, http } = await fetchForKeyword(base, key, cat, kw, bgn, end);
        if (error) { errors.push({ kw, cat, http, error }); continue; }
        for (const it of items) {
          const id = `${it.bidNtceNo || ""}-${it.bidNtceOrd || ""}-${cat}`;
          if (seen.has(id)) continue;
          seen.add(id);
          matches.push({ ...it, _cat: cat, _kw: kw });
        }
      } catch (e) {
        errors.push({ kw, cat, error: e.message });
      }
    }
  }

  const summary = { window: { bgn, end }, keywords, cats, matched: matches.length, errors };

  if (dry) {
    return new Response(JSON.stringify({ ...summary, matches }, null, 2), {
      headers: { "Content-Type": "application/json" },
    });
  }

  if (matches.length) {
    const text = buildSlackText(matches, keywords, lookbackH);
    const sr = await fetch(webhook, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    summary.slack = { ok: sr.ok, status: sr.status };
  } else {
    summary.slack = { skipped: "no matches" };
  }

  return new Response(JSON.stringify(summary), {
    headers: { "Content-Type": "application/json" },
  });
}
