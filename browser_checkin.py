#!/usr/bin/env python3
"""GLaDOS GitHub Actions check-in using a real browser fingerprint.

The service now rejects direct requests as a bot. This script runs Chromium
under Xvfb, injects the GitHub Actions cookie, and calls the same browser API
as the web UI.
"""

import json
import os
import sys
import time
from typing import Dict, List

import requests
from playwright.sync_api import sync_playwright

DOMAINS = ["glados.rocks", "glados.cloud"]
COOKIE_ENV = "GLADOS_COOKIES"
SENDKEY_ENV = "SENDKEY"
RETRIES = 3

MAC_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
)


def log(message: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S"), "-", message, flush=True)


def parse_cookie_string(raw: str) -> List[Dict[str, str]]:
    cookies = []
    for item in raw.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        name, value = item.split("=", 1)
        cookies.append({"name": name.strip(), "value": value.strip()})
    return cookies


def add_cookies(context, domain: str, raw: str) -> None:
    cookies = []
    for cookie in parse_cookie_string(raw):
        cookies.append(
            {
                **cookie,
                "domain": domain,
                "path": "/",
                "secure": True,
            }
        )
    if not cookies:
        raise ValueError("GLADOS_COOKIES contains no parseable cookies")
    context.add_cookies(cookies)


def checkin_on_domain(page, domain: str) -> Dict:
    page.goto(
        f"https://{domain}/console/checkin",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    page.wait_for_timeout(5000)
    if page.url.rstrip("/") == f"https://{domain}":
        return {"ok": False, "message": f"{domain}: login cookie rejected"}

    last = None
    for attempt in range(1, RETRIES + 1):
        response = page.evaluate(
            """async (domain) => {
                try {
                    const r = await fetch('/api/user/checkin', {
                        method: 'POST',
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json, text/plain, */*',
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({token: domain})
                    });
                    const text = await r.text();
                    let data;
                    try { data = JSON.parse(text); } catch (_) { data = {raw: text}; }
                    return {http_status: r.status, data};
                } catch (e) {
                    return {http_status: 0, error: String(e)};
                }
            }""",
            domain,
        )
        last = response
        data = response.get("data") or {}
        code = data.get("code")
        log(f"{domain}: attempt {attempt}, HTTP {response.get('http_status')}, code {code}")
        if code == 0:
            return {"ok": True, "already": False, "message": f"{domain}: check-in succeeded (+{data.get('points', '?')} points)"}
        if code == 1:
            return {"ok": True, "already": True, "message": f"{domain}: already checked in today"}
        if code == 4 and data.get("reason") == "device-mismatch":
            return {"ok": False, "message": f"{domain}: device mismatch ({data.get('loginDevice')} vs {data.get('currentDevice')})"}
        if code == -2:
            return {"ok": False, "message": f"{domain}: cookie expired or unauthorized"}
        if attempt < RETRIES:
            time.sleep(3 * attempt)
    return {"ok": False, "message": f"{domain}: API failed: {json.dumps(last, ensure_ascii=False)}"}


def notify(title: str, content: str) -> bool:
    key = os.environ.get(SENDKEY_ENV, "").strip()
    if not key:
        log("SENDKEY is not configured; notification skipped")
        return False
    try:
        response = requests.post(
            f"https://sctapi.ftqq.com/{key}.send",
            data={"title": title, "desp": content},
            timeout=30,
        )
        data = response.json()
        ok = response.ok and data.get("code") == 0
        log("Server酱 notification: " + ("sent" if ok else f"failed: {data}"))
        return ok
    except Exception as exc:
        log(f"Server酱 notification exception: {exc}")
        return False


def main() -> int:
    raw_cookie = os.environ.get(COOKIE_ENV, "").strip()
    if not raw_cookie:
        log(f"{COOKIE_ENV} is not configured")
        notify("GLaDOS check-in failed", f"{COOKIE_ENV} is not configured")
        return 1

    results = []
    with sync_playwright() as playwright:
        # GitHub runners provide stable Google Chrome; using it avoids the
        # automation fingerprint that GLaDOS classifies as the Bot device.
        launch_kwargs = {
            "channel": "chrome",
            "headless": False,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        }
        browser = playwright.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            user_agent=MAC_UA,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        context.add_init_script(
            """Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
               Object.defineProperty(navigator, 'platform', {get: () => 'MacIntel'});"""
        )
        try:
            for domain in DOMAINS:
                add_cookies(context, domain, raw_cookie)
                page = context.new_page()
                try:
                    result = checkin_on_domain(page, domain)
                    results.append(result)
                    if result["ok"]:
                        message = result["message"]
                        notify("GLaDOS check-in", message + " ✅")
                        return 0
                finally:
                    page.close()
        finally:
            context.close()
            browser.close()

    message = "\n".join(result["message"] for result in results) or "no result"
    notify("GLaDOS check-in failed", message + " ❌")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
