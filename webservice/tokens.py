"""쿠키가 막힌 환경을 위한 서명 토큰.

왜 필요한가: 전시 사이트가 이 앱을 iframe 으로 띄우고, 관람객은 카카오톡 인앱
브라우저로 그 페이지를 연다. 이중 서드파티 컨텍스트라 **로그인 응답의 Set-Cookie
가 저장되지 않는다.** 로그인 자체는 200 으로 성공하는데 직후의 모든 요청이 401 이
되어, 화면은 로그인된 것처럼 보이면서 아무것도 동작하지 않는다.

localStorage 는 iframe 의 출처 기준으로 동작해서 쿠키가 차단돼도 살아남는다.
그래서 로그인 때 토큰을 함께 내려주고, 클라이언트가 그걸 헤더에 실어 보낸다.

쿠키를 없애지는 않는다 — 쿠키가 되는 환경(브라우저에서 직접 열기)에서는 그대로
쓰고, 토큰은 쿠키가 실패했을 때의 대체 경로다.

서명은 세션 쿠키와 같은 비밀키(DAON_SECRET)를 쓴다. 키를 하나로 두면 배포에서
관리할 값이 늘지 않고, 키를 바꾸면 쿠키와 토큰이 함께 무효가 된다.
"""

import base64
import json
import os

from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

# 세션 쿠키(Max-Age=1209600)와 같은 수명. 둘이 다르면 한쪽만 살아남아
# '로그인은 되어 있는데 일부만 401' 이라는 헷갈리는 상태가 생긴다.
MAX_AGE_SECONDS = 14 * 24 * 3600


def _signer():
    # app.py 와 같은 기본값. 배포(DAON_EMBED=1)에서는 app.py 가 기본값을 거부한다.
    secret = os.environ.get("DAON_SECRET") or "dev-demo-secret-change-me"
    return TimestampSigner(secret, salt="daon-api-token")


def make_token(user):
    """로그인한 사용자 정보를 담은 서명 토큰."""
    raw = base64.urlsafe_b64encode(json.dumps(user, ensure_ascii=False).encode())
    return _signer().sign(raw).decode()


def read_token(token):
    """토큰에서 사용자 정보를 꺼낸다. 위조·만료·형식 오류는 전부 None."""
    if not token:
        return None
    try:
        raw = _signer().unsign(token.encode(), max_age=MAX_AGE_SECONDS)
        return json.loads(base64.urlsafe_b64decode(raw).decode())
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None


def from_header(authorization):
    """`Authorization: Bearer <토큰>` 헤더에서 사용자 정보를 꺼낸다."""
    if not authorization or not isinstance(authorization, str):
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return read_token(parts[1])
