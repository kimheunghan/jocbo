// 우리의 족보 - 공유 사이트를 dist 에 만듭니다.
// 첫 화면(index.html)은 홍보 페이지(web/landing.html)이고, 공유 링크(/s/아이디)는
// app.html 을 엽니다. app.html 은 PC 화면(frontend)에 공유용 share.js·share.css 를 끼운 것입니다.
// 공유 주소는 /s/아이디 라서 화면의 파일 이름을 / 부터 적고, 고친 판을 브라우저가
// 새로 받도록 내용에 따른 꼬리표(?v=)를 붙입니다.
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync, readdirSync, renameSync, statSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';

const front = join(import.meta.dirname, '..', 'frontend');
const web = join(import.meta.dirname, 'web');
const dist = join(import.meta.dirname, 'dist');

// 폴더째 지우지 않고 안만 비웁니다. 미리보기 서버 등이 폴더를 잡고 있으면 Windows 는
// 폴더 자체는 지우지 못하게 합니다.
mkdirSync(dist, { recursive: true });
for (const name of readdirSync(dist)) rmSync(join(dist, name), { recursive: true, force: true });
cpSync(front, dist, { recursive: true });
cpSync(web, dist, { recursive: true });

const stamp = name => createHash('sha256').update(readFileSync(join(dist, name))).digest('hex').slice(0, 10);
let page = readFileSync(join(dist, 'index.html'), 'utf8');
for (const name of readdirSync(dist).filter(name => statSync(join(dist, name)).isFile())) {
  page = page.replaceAll(`"${name}"`, `"/${name}?v=${stamp(name)}"`);
}
const theme = `/theme.css?v=${stamp('theme.css')}`;
const app = `<script src="/app.js?v=${stamp('app.js')}" defer></script>`;
if (!page.includes(theme) || !page.includes(app)) throw new Error('index.html 의 theme.css·app.js 자리를 찾지 못했습니다.');
page = page
  .replace(`href="${theme}">`, `href="${theme}"><link rel="stylesheet" href="/share.css?v=${stamp('share.css')}">`)
  .replace(app, `<script src="/share.js?v=${stamp('share.js')}" defer></script>${app}`);
// 공유 화면은 검색에 싣지 않습니다(robots.txt 로도 막지만, 링크가 밖에 걸려도 색인되지 않게).
page = page.replace('<head>', '<head><meta name="robots" content="noindex, nofollow">');
writeFileSync(join(dist, 'app.html'), page);
renameSync(join(dist, 'landing.html'), join(dist, 'index.html'));
// Cloudflare Pages 는 netlify.toml 을 읽지 않으므로 같은 규칙을 _redirects 로도 둡니다.
// Pages 는 app.html 을 /app 으로 부르므로(/app.html 로 가면 /app 으로 돌려보냄) /app 으로 잇습니다.
// 구글 서치 콘솔 확인 파일은 .html 주소 그대로 바로 열려야 합니다. Pages 는 .html 주소를
// 확장자 없는 주소로 넘기므로(308) .txt 로 두고 .html 주소를 그쪽으로 잇습니다.
const verify = readdirSync(dist).filter(name => /^google[0-9a-f]+\.html$/.test(name));
for (const name of verify) renameSync(join(dist, name), join(dist, name.replace(/\.html$/, '.txt')));
// [정식판 구매하기]는 홈페이지와 프로그램 모두 /buy 로 갑니다. 결제 주소가 바뀌면 여기만
// 고치면 되고, 이미 설치된 프로그램도 다시 빌드하지 않아도 새 주소로 갑니다.
const checkout = 'https://findinside.lemonsqueezy.com/checkout/buy/4d6c9aac-24bf-4e7c-b881-3b66c96f5f3c';
writeFileSync(join(dist, '_redirects'), '/s/* /app 200\n'
  + `/buy ${checkout} 302\n`
  + verify.map(name => `/${name} /${name.replace(/\.html$/, '.txt')} 200\n`).join(''));
// jocbo.netlify.app 에 올리는 사이트맵 전용 폴더도 같은 사이트맵과 구글 확인 파일로 맞춥니다.
const mirror = join(import.meta.dirname, 'sitemap-mirror');
cpSync(join(web, 'sitemap.xml'), join(mirror, 'sitemap.xml'));
for (const name of readdirSync(web).filter(name => /^google[0-9a-f]+\.html$/.test(name))) cpSync(join(web, name), join(mirror, name));
console.log('dist 완료');
