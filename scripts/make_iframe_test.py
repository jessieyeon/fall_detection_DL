#!/usr/bin/env python3
"""배포 URL을 iframe에 넣어 검증하는 테스트 페이지를 만든다.

    python3 scripts/make_iframe_test.py https://your-app.up.railway.app
    open iframe_test.html

전시 사이트가 우리 앱을 iframe으로 띄우기 때문에, URL을 직접 여는 것만으로는
검증이 안 된다. iframe 안에서는 쿠키가 서드파티가 되어 로그인이 풀리거나,
CSP/X-Frame-Options 때문에 화면이 아예 비는 일이 생긴다. 그 상황을 그대로
재현한다.
"""

import argparse
import os
import sys

TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>다온 iframe 임베드 검증</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 0; padding: 24px; background: #f5f6f8; color: #1a1d21; }}
  h1 {{ font-size: 18px; margin: 0 0 4px; }}
  .url {{ font-size: 13px; color: #5b6270; margin-bottom: 20px;
          word-break: break-all; }}
  .row {{ display: flex; gap: 20px; align-items: flex-start; flex-wrap: wrap; }}
  .panel {{ background: #fff; border: 1px solid #dfe3e8; border-radius: 10px;
            padding: 16px; }}
  .frames {{ flex: 1 1 640px; }}
  .checks {{ flex: 0 1 320px; }}
  .size {{ font-size: 12px; color: #5b6270; margin: 12px 0 6px; font-weight: 600; }}
  iframe {{ border: 1px solid #c9ced6; border-radius: 6px; background: #fff;
            display: block; }}
  #desktop {{ width: 100%; height: 620px; }}
  #mobile {{ width: 390px; height: 620px; max-width: 100%; }}
  ul {{ margin: 0; padding-left: 18px; font-size: 14px; line-height: 1.9; }}
  code {{ background: #eef0f3; padding: 1px 5px; border-radius: 4px;
          font-size: 12px; }}
  .note {{ font-size: 13px; line-height: 1.7; color: #454b54;
           border-left: 3px solid #c9ced6; padding-left: 12px; margin-top: 16px; }}
  #status {{ font-size: 13px; margin-top: 10px; padding: 10px 12px;
             border-radius: 6px; background: #eef0f3; }}
</style>
</head>
<body>

<h1>다온 iframe 임베드 검증</h1>
<div class="url">{url}</div>

<div class="row">
  <div class="panel frames">
    <div class="size">데스크톱 (100% 폭)</div>
    <iframe id="desktop" src="{url}"
            allow="camera; microphone; fullscreen"></iframe>

    <div class="size">모바일 (390px — iPhone 폭)</div>
    <iframe id="mobile" src="{url}"
            allow="camera; microphone; fullscreen"></iframe>

    <div id="status">로딩 확인 중…</div>
  </div>

  <div class="panel checks">
    <strong style="font-size:14px">확인 항목</strong>
    <ul>
      <li>화면이 뜨는가 (비면 CSP 문제)</li>
      <li><b>iframe 안에서 로그인이 되는가</b></li>
      <li>새로고침해도 로그인이 유지되는가</li>
      <li>영상 업로드 → 리포트까지 완주</li>
      <li>390px에서 레이아웃이 안 깨지는가</li>
      <li>콘솔에 에러가 없는가</li>
    </ul>

    <div class="note">
      <b>화면이 비어 있다면</b><br>
      개발자도구 콘솔에 <code>Refused to display ... in a frame</code>
      가 있는지 보세요. 있으면 <code>DAON_FRAME_ANCESTORS</code> 설정 문제입니다.
    </div>

    <div class="note">
      <b>로그인만 안 된다면</b><br>
      가장 흔한 원인입니다. iframe 안에서 쿠키가 서드파티가 되어
      <code>SameSite=lax</code>로는 전송되지 않습니다.
      서버에 <code>DAON_EMBED=1</code>을 설정하세요.
    </div>

    <div class="note">
      <b>데모 계정</b><br>
      senior@daon.com / pw<br>
      guardian@daon.com / pw
    </div>
  </div>
</div>

<script>
  // iframe 로드 자체는 잡히지만, CSP로 차단된 경우도 load 이벤트가 발생한다.
  // 그래서 '뜬 것처럼 보여도 눈으로 확인하라'고 안내한다.
  const status = document.getElementById('status');
  let loaded = 0;
  for (const id of ['desktop', 'mobile']) {{
    document.getElementById(id).addEventListener('load', () => {{
      loaded += 1;
      if (loaded === 2) {{
        status.textContent =
          'iframe 요청 완료. 실제로 화면이 보이는지는 눈으로 확인하세요 — ' +
          'CSP로 차단돼도 load 이벤트는 발생합니다.';
      }}
    }});
  }}
</script>

</body>
</html>
"""


def serve(path, port=8899):
    """테스트 페이지를 http 로 띄운다.

    파일을 그냥 더블클릭해 열면 주소가 `file://` 인데, CSP 의 `frame-ancestors *`
    는 http/https/ws/wss 같은 **네트워크 스킴만** 매칭한다. 그래서 배포가 멀쩡해도
    브라우저가 이렇게 거부한다:

        Framing '...' violates ... "frame-ancestors *". ...
        Note that '*' matches only URLs with network schemes ...

    실제 전시 사이트는 https 라 문제가 없다. 테스트만 http 로 맞춰주면 된다.
    """
    import functools
    import http.server
    import socketserver
    import webbrowser

    directory = os.path.dirname(os.path.abspath(path)) or "."
    filename = os.path.basename(path)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=directory)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        url = f"http://127.0.0.1:{port}/{filename}"
        print(f"\n테스트 페이지: {url}")
        print("Ctrl+C 로 종료합니다.\n")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n종료")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="배포된 앱의 공개 URL (https://...)")
    ap.add_argument("-o", "--out", default="iframe_test.html")
    ap.add_argument("--no-serve", action="store_true",
                    help="파일만 만들고 로컬 서버를 띄우지 않는다")
    ap.add_argument("--port", type=int, default=8899)
    args = ap.parse_args()

    url = args.url.rstrip("/")
    if not url.startswith("http"):
        sys.exit("URL은 http:// 또는 https:// 로 시작해야 합니다.")
    if url.startswith("http://"):
        print("경고: HTTP 입니다. iframe 안에서 쿠키(SameSite=None; Secure)가")
        print("      동작하지 않습니다. 실제 제출은 HTTPS 여야 합니다.\n")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(TEMPLATE.format(url=url))

    print(f"생성: {os.path.abspath(args.out)}")

    if args.no_serve:
        print("\n주의: 이 파일을 그대로 열면(file://) CSP 때문에 iframe 이 차단됩니다.")
        print("      'frame-ancestors *' 는 http/https 만 매칭하고 file:// 은 제외됩니다.")
        print(f"      http 로 띄우려면:  python3 -m http.server {args.port}")
        return

    serve(args.out, args.port)


if __name__ == "__main__":
    main()
