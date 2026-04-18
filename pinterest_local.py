#!/usr/bin/env python3
"""本地 Pinterest 爬虫客户端 - 调用 Windows Chrome CDP"""

import argparse, json, os, sys, urllib.request, urllib.error, time


def wait_chrome(port=9222, timeout=30):
    for _ in range(timeout):
        try:
            req = urllib.request.Request(f"http://localhost:{port}/json/version")
            with urllib.request.urlopen(req, timeout=5) as r:
                if r.status == 200:
                    return True
        except:
            pass
        time.sleep(1)
    return False


def get_cdp_endpoint(port=9222):
    req = urllib.request.Request(f"http://localhost:{port}/json/version")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--max-pins", type=int, default=100)
    parser.add_argument("--min-saves", type=int, default=0)
    parser.add_argument("--min-likes", type=int, default=0)
    parser.add_argument("--min-comments", type=int, default=0)
    parser.add_argument(
        "--download-images", type=lambda x: x.lower() == "true", default=True
    )
    args = parser.parse_args()

    if not wait_chrome():
        print(
            json.dumps(
                {"success": False, "error": "Chrome not ready on localhost:9222"}
            )
        )
        sys.exit(1)

    meta = get_cdp_endpoint()
    print(
        json.dumps(
            {
                "success": True,
                "query": args.query,
                "max_pins": args.max_pins,
                "min_saves": args.min_saves,
                "min_likes": args.min_likes,
                "min_comments": args.min_comments,
                "download_images": args.download_images,
                "chrome_version": meta.get("Browser", "unknown"),
                "websocket": meta.get("webSocketDebuggerUrl", ""),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
