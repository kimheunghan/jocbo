"""The paid plan: a license key turns an account into the full version.

The key is bought on the checkout page and comes back on the receipt screen and
by e-mail. Putting it in registers this PC as one of the key's places (two PCs
to a key); taking it out frees that place for another PC.

Keys are checked by our own license server (share/lib/license.js on
jocbo.pages.dev), whichever shop sold them: Paddle keys (JOCBO-XXXX-...) are made
there, and keys bought from Lemon Squeezy before it closed (2027-03-31) are taken
over there the first time they come in, so they keep working afterwards.
"""
import json
import os
import urllib.error
import urllib.request

SERVER = os.getenv('JOCBO_LICENSE_SERVER', 'https://jocbo.pages.dev').rstrip('/')
# Where [정식판 구매하기] goes. The site sends /buy on to the live checkout, so a
# new checkout needs no new build (share/build.mjs).
CHECKOUT_URL = os.getenv('JOCBO_CHECKOUT_URL', 'https://jocbo.pages.dev/buy')
# The server holds keys for several programs; this one takes only its own.
PRODUCT = 'jocbo'


class LicenseError(Exception):
    pass


def call(action, payload):
    """POST to the license server; its Korean `detail` becomes the error text."""
    request = urllib.request.Request(
        f'{SERVER}/api/license/{action}', data=json.dumps(payload).encode(), method='POST',
        headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'User-Agent': 'jocbo-desktop/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read() or b'{}')
        except Exception:
            body = {}
        raise LicenseError(body.get('detail') or f'라이선스 서버가 요청을 받지 않았습니다 ({error.code}).')
    except (urllib.error.URLError, TimeoutError, OSError):
        raise LicenseError('라이선스 서버에 연결하지 못했습니다. 인터넷 연결을 확인해 주십시오.')


def activate(key, pc_name):
    """Register this PC under the key; gives back the place's id to keep."""
    body = call('activate', {'key': key.strip(), 'name': pc_name, 'product': PRODUCT})
    if not body.get('activated') or body.get('product') != PRODUCT:
        raise LicenseError(body.get('detail') or '라이선스 키를 등록하지 못했습니다.')
    return body.get('instance', '')


def deactivate(key, instance):
    body = call('deactivate', {'key': key.strip(), 'instance': instance})
    if not body.get('deactivated'):
        raise LicenseError(body.get('detail') or '등록을 풀지 못했습니다.')
