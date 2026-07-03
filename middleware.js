import { next } from '@vercel/edge';

export const config = {
  matcher: '/((?!api/watch-g2b).*)',
};

// SITE_USERS 예시: [{"id":"최종률","pw":"01088645734","name":"최종률"}, ...]
// 하위 호환: SITE_USER + SITE_PASS 단일 계정도 지원.
function parseUsers(env) {
  const raw = env.SITE_USERS;
  if (raw) {
    try {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr)) return arr.map(u => ({
        id: String(u.id ?? ''),
        pw: String(u.pw ?? u.password ?? ''),
        name: String(u.name ?? u.id ?? ''),
      })).filter(u => u.id && u.pw);
    } catch {}
  }
  if (env.SITE_USER && env.SITE_PASS) {
    return [{ id: env.SITE_USER, pw: env.SITE_PASS, name: env.SITE_USER }];
  }
  return [];
}

// 한글 이름을 쿠키에 안전하게 (RFC 6265 friendly) 저장/읽기용
function encodeName(name) { return encodeURIComponent(name); }

function decodeBasic(header) {
  try {
    // atob은 latin1만 다루므로 UTF-8 로 다시 디코딩 (한글 아이디 지원)
    const bin = atob(header.slice(6));
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const decoded = new TextDecoder('utf-8').decode(bytes);
    const idx = decoded.indexOf(':');
    if (idx < 0) return null;
    return { user: decoded.slice(0, idx), pass: decoded.slice(idx + 1) };
  } catch { return null; }
}

const LOGOUT_HTML = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>로그아웃 — 똑똑</title><style>
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Malgun Gothic",sans-serif;background:#f6efe6;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;color:#1a3a6c}
.card{background:#fff;border-radius:16px;padding:36px 28px;max-width:420px;width:100%;box-shadow:0 4px 24px rgba(0,0,0,0.08);text-align:center}
h1{margin:0 0 12px;font-size:22px}
p{margin:8px 0;color:#5b6474;font-size:14px;line-height:1.6}
.hint{font-size:12px;color:#888;margin-top:20px;padding-top:16px;border-top:1px solid #eee}
a{display:inline-block;margin-top:16px;padding:10px 20px;background:#1a3a6c;color:#fff;text-decoration:none;border-radius:8px;font-weight:600;font-size:14px}
a:hover{background:#0f2954}
</style></head><body><div class="card">
<h1>👋 로그아웃 되었습니다</h1>
<p>안전한 종료를 위해 <b>브라우저 창을 완전히 닫으신 후</b> 다시 접속해 주세요.</p>
<p class="hint">HTTP Basic 인증은 브라우저가 로그인 정보를 세션 내내 캐시하는 특성상, 창을 닫아야 완전히 지워집니다.</p>
<a href="/">다시 로그인</a>
</div></body></html>`;

export default function middleware(request) {
  const url = new URL(request.url);

  // === 로그아웃 처리 ===
  if (url.pathname === '/logout') {
    return new Response(LOGOUT_HTML, {
      status: 401, // 401 로 응답해야 브라우저가 Basic Auth 캐시를 무효화
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        // WWW-Authenticate 를 넣지 않아 재로그인 다이얼로그가 즉시 뜨지 않게 함
        'Cache-Control': 'no-store, no-cache, must-revalidate, private',
        'Clear-Site-Data': '"cookies", "storage"',
        'Set-Cookie': 'ddok_user=; Path=/; Max-Age=0; SameSite=Lax; Secure',
      },
    });
  }

  const users = parseUsers(process.env);
  if (users.length === 0) {
    return new Response('Site authentication is not configured (set SITE_USERS or SITE_USER/SITE_PASS)', { status: 500 });
  }

  const auth = request.headers.get('authorization');
  if (auth && auth.startsWith('Basic ')) {
    const creds = decodeBasic(auth);
    if (creds) {
      const match = users.find(u => u.id === creds.user && u.pw === creds.pass);
      if (match) {
        const res = next();
        // 브라우저 세션 쿠키 — 창 닫으면 사라짐. path=/ 로 index.html에서도 읽음.
        res.headers.append(
          'Set-Cookie',
          `ddok_user=${encodeName(match.name)}; Path=/; SameSite=Lax; Secure`
        );
        return res;
      }
    }
  }

  return new Response('Authentication required', {
    status: 401,
    headers: {
      'WWW-Authenticate': 'Basic realm="ddok-ddok", charset="UTF-8"',
      'Content-Type': 'text/plain; charset=utf-8',
    },
  });
}
