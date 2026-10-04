// 우리의 족보 - 설치 파일 내려받기 주소.
//
//   GET /download/<태그>/jocbo-setup.exe   설치 파일 (v…, store-v…)
//   GET /download/<태그>/jocbo.msix        Store 용 MSIX 패키지 (msix-v…)
//
// GitHub Releases 의 주소는 실제 파일이 있는 다른 주소로 넘겨집니다(리디렉션).
// Microsoft Store 는 넘겨지지 않고 바로 파일을 주는 주소를 요구하므로, 여기서 GitHub 의
// 같은 판을 받아 그대로 흘려보냅니다. 판(태그)이 주소에 들어 있어 내용이 바뀌지 않습니다.

const REPO = 'https://github.com/kimheunghan/jocbo/releases/download';

export async function onRequest({ request, params }) {
  const { tag, file } = params;
  const ok = (/^(store-)?v[0-9.]+$/.test(tag) && file === 'jocbo-setup.exe') || (/^msix-v[0-9.]+$/.test(tag) && file === 'jocbo.msix');
  if (!ok) {
    return new Response('없는 파일입니다.', { status: 404 });
  }
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return new Response(null, { status: 405, headers: { Allow: 'GET, HEAD' } });
  }
  const upstream = await fetch(`${REPO}/${tag}/${file}`, { method: request.method, redirect: 'follow' });
  if (!upstream.ok) return new Response('없는 파일입니다.', { status: 404 });
  const headers = new Headers({
    'Content-Type': 'application/octet-stream',
    'Content-Disposition': `attachment; filename="${file}"`,
    'Cache-Control': 'public, max-age=86400',
  });
  const length = upstream.headers.get('content-length');
  if (length) headers.set('Content-Length', length);
  return new Response(request.method === 'HEAD' ? null : upstream.body, { status: 200, headers });
}
