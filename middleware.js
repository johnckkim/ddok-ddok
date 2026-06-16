import { next } from '@vercel/edge';

export const config = {
  matcher: '/(.*)',
};

export default function middleware(request) {
  // Cron 모니터링 엔드포인트는 Basic Auth 우회 (함수 자체가 CRON_SECRET 으로 보호).
  // Vercel Cron 요청은 Basic 자격이 없으므로 여기서 막으면 안 됨.
  if (new URL(request.url).pathname === '/api/watch-g2b') {
    return next();
  }

  const expectedUser = process.env.SITE_USER;
  const expectedPass = process.env.SITE_PASS;

  if (!expectedUser || !expectedPass) {
    return new Response('Site authentication is not configured', { status: 500 });
  }

  const auth = request.headers.get('authorization');
  if (auth && auth.startsWith('Basic ')) {
    try {
      const decoded = atob(auth.slice(6));
      const idx = decoded.indexOf(':');
      if (idx > 0) {
        const user = decoded.slice(0, idx);
        const pass = decoded.slice(idx + 1);
        if (user === expectedUser && pass === expectedPass) {
          return next();
        }
      }
    } catch {}
  }

  return new Response('Authentication required', {
    status: 401,
    headers: {
      'WWW-Authenticate': 'Basic realm="ddok-ddok", charset="UTF-8"',
      'Content-Type': 'text/plain; charset=utf-8',
    },
  });
}
