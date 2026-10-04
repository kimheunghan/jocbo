"""The paid plan: a Lemon Squeezy license key turns an account into the full version.

The key is bought on the checkout page, and comes back on the receipt screen and
by e-mail. Putting it in activates this PC as one of the key's instances (two
PCs to a key); taking it out frees that place for another PC.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.lemonsqueezy.com/v1/licenses'
# Where [정식판 구매하기] goes. Set once the product exists on Lemon Squeezy.
CHECKOUT_URL = os.getenv('JOCBO_CHECKOUT_URL', '')
# A key is taken only for a product of this name, so a FindInside key sold from
# the same store does not unlock this.
PRODUCT_WORD = '족보'


class LicenseError(Exception):
    pass


def call(action, **fields):
    data = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(f'{API}/{action}', data=data, method='POST',
                                     headers={'Accept': 'application/json', 'User-Agent': 'jocbo-desktop/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read() or b'{}')
        except Exception:
            body = {}
        raise LicenseError(explain(body.get('error')) or f'라이선스 서버가 요청을 받지 않았습니다 ({error.code}).')
    except (urllib.error.URLError, TimeoutError, OSError):
        raise LicenseError('라이선스 서버에 연결하지 못했습니다. 인터넷 연결을 확인해 주십시오.')


def explain(error):
    """Lemon Squeezy's English errors, in the words the page uses."""
    if not error:
        return ''
    text = str(error).lower()
    if 'activation limit' in text:
        return '이 키는 이미 PC 2대에 등록되어 있습니다. 쓰지 않는 PC에서 먼저 등록을 풀어 주십시오.'
    if 'not found' in text or 'invalid' in text:
        return '라이선스 키가 맞지 않습니다. 결제 확인 이메일의 키를 그대로 붙여 넣어 주십시오.'
    if 'expired' in text or 'disabled' in text:
        return '쓸 수 없는 키입니다(만료 또는 환불). 문의 메일로 알려 주십시오.'
    return str(error)


def activate(key, pc_name):
    """Register this PC under the key; gives back the instance id to keep."""
    body = call('activate', license_key=key, instance_name=pc_name)
    if not body.get('activated'):
        raise LicenseError(explain(body.get('error')) or '라이선스 키를 등록하지 못했습니다.')
    product = (body.get('meta') or {}).get('product_name', '')
    instance = (body.get('instance') or {}).get('id', '')
    if PRODUCT_WORD not in product:
        # Give the place back at once; this key is for something else.
        try:
            call('deactivate', license_key=key, instance_id=instance)
        except LicenseError:
            pass
        raise LicenseError('우리의 족보 정식판 키가 아닙니다.')
    return instance


def deactivate(key, instance):
    body = call('deactivate', license_key=key, instance_id=instance)
    if not body.get('deactivated'):
        raise LicenseError(explain(body.get('error')) or '등록을 풀지 못했습니다.')
