/**
 * 우리의 족보 - 라이선스 키 메일 발송 창구 (Google Apps Script)
 *
 * 운영자 Gmail(hung67890@gmail.com) 계정의 Apps Script 에 붙여 넣고 "웹 앱"으로 배포합니다.
 * 라이선스 서버(share/lib/license.js)가 결제가 끝날 때마다 이 주소로 메일 내용을 보내면,
 * 이 계정 이름으로 고객에게 메일을 보냅니다. 무료 계정은 하루 100통까지 보냅니다.
 *
 * 설정
 *   1. https://script.google.com → 새 프로젝트 → 이 파일 내용을 붙여 넣기
 *   2. 프로젝트 설정 → 스크립트 속성 → MAIL_SECRET 에 서버와 같은 비밀값 넣기
 *   3. 배포 → 새 배포 → 유형: 웹 앱 → 실행: 나 / 액세스: 모든 사용자 → 배포 → 권한 허용
 *   4. 나온 웹 앱 URL 을 서버의 MAIL_URL 비밀값으로 넣기
 *
 * 비밀값이 맞을 때만 보내므로, 주소를 알아도 다른 사람이 메일을 보낼 수 없습니다.
 */
function doPost(e) {
  var out = function (body) {
    return ContentService.createTextOutput(JSON.stringify(body)).setMimeType(ContentService.MimeType.JSON);
  };
  var secret = PropertiesService.getScriptProperties().getProperty('MAIL_SECRET');
  var body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    return out({ ok: false, error: 'bad json' });
  }
  if (!secret || body.secret !== secret) return out({ ok: false, error: 'forbidden' });
  if (!body.to || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(body.to) || !body.subject) return out({ ok: false, error: 'bad request' });
  if (MailApp.getRemainingDailyQuota() < 1) return out({ ok: false, error: 'quota' });
  MailApp.sendEmail({
    to: body.to,
    subject: String(body.subject).slice(0, 200),
    body: String(body.text || ''),
    htmlBody: String(body.html || ''),
    name: String(body.name || '우리의 족보'),
  });
  return out({ ok: true, left: MailApp.getRemainingDailyQuota() });
}

/** 스크립트 편집기에서 한 번 실행해 권한을 허용하고, 운영자에게 시험 메일이 오는지 봅니다. */
function testMail() {
  MailApp.sendEmail(Session.getActiveUser().getEmail(), '[우리의 족보] 메일 창구 시험', '이 메일이 보이면 키 메일 발송 창구가 준비된 것입니다.');
}
