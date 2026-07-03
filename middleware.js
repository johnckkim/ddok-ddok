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

export default function middleware(request) {
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
