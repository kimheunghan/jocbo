// 우리의 족보 - 공유 사이트의 화면을 dist 에 만듭니다.
// PC 화면(frontend)을 그대로 가져오고, 공유용 share.js·share.css 를 끼웁니다.
// 공유 주소는 /s/아이디 라서 화면의 파일 이름을 / 부터 적고, 고친 판을 브라우저가
// 새로 받도록 내용에 따른 꼬리표(?v=)를 붙입니다.
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';

const front = join(import.meta.dirname, '..', 'frontend');
const web = join(import.meta.dirname, 'web');
const dist = join(import.meta.dirname, 'dist');

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist);
cpSync(front, dist, { recursive: true });
cpSync(web, dist, { recursive: true });

const stamp = name => createHash('sha256').update(readFileSync(join(dist, name))).digest('hex').slice(0, 10);
let page = readFileSync(join(dist, 'index.html'), 'utf8');
for (const name of readdirSync(dist)) {
  page = page.replaceAll(`"${name}"`, `"/${name}?v=${stamp(name)}"`);
}
const theme = `/theme.css?v=${stamp('theme.css')}`;
const app = `<script src="/app.js?v=${stamp('app.js')}" defer></script>`;
if (!page.includes(theme) || !page.includes(app)) throw new Error('index.html 의 theme.css·app.js 자리를 찾지 못했습니다.');
page = page
  .replace(`href="${theme}">`, `href="${theme}"><link rel="stylesheet" href="/share.css?v=${stamp('share.css')}">`)
  .replace(app, `<script src="/share.js?v=${stamp('share.js')}" defer></script>${app}`);
writeFileSync(join(dist, 'index.html'), page);
console.log('dist 완료');
