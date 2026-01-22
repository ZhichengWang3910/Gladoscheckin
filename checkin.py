import requests
import os
import time


def send_wechat(token, title, msg):
    url = "https://www.pushplus.plus/send"
    params = {
        "token": token,
        "title": title,
        "content": msg,
        "template": "html"
    }
    r = requests.get(url, params=params, timeout=10)
    print("PushPlus:", r.text)


def build_urls(domain: str):
    base = f"https://{domain}"
    return {
        "checkin": f"{base}/api/user/checkin",
        "status":  f"{base}/api/user/status",
        "referer": f"{base}/console/checkin",
        "origin":  base
    }


if __name__ == "__main__":

    # ========= 基础配置（全部可通过 Env 覆盖） =========
    domain = os.environ.get("GLADOS_DOMAIN", "glados.cloud").strip()
    cookies = os.environ.get("COOKIES", "").split("&")
    sendkey = os.environ.get("SENDKEY", "")

    if not domain:
        print("GLADOS_DOMAIN 为空")
        exit(0)

    if not cookies or cookies[0] == "":
        print("未找到 COOKIES")
        exit(0)

    urls = build_urls(domain)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "Referer": urls["referer"],
        "Origin": urls["origin"],
        "Content-Type": "application/json;charset=UTF-8",
    }

    payload = {"token": "glados.one"}

    success, repeat, fail = 0, 0, 0
    summary = []

    for idx, cookie in enumerate(cookies, 1):
        print(f"\n==== Account {idx} ({domain}) ====")

        session = requests.Session()
        session.headers.update(headers)
        session.headers.update({"Cookie": cookie})

        try:
            r = session.post(urls["checkin"], json=payload, timeout=15)
            print("Checkin:", r.text)

            data = r.json()
            msg = data.get("message", "")
            points = data.get("points", 0)

            if "Checkin! Got" in msg:
                success += 1
                status_msg = f"签到成功 +{points}"
            elif "Repeats" in msg:
                repeat += 1
                status_msg = "重复签到"
            else:
                fail += 1
                summary.append(f"签到失败: {msg}")
                continue

            r2 = session.get(urls["status"], timeout=15)
            info = r2.json().get("data", {})

            email = info.get("email", "unknown")
            days = info.get("leftDays", "NA")

            summary.append(
                f"{email} | {status_msg} | 剩余 {days} 天"
            )

            time.sleep(2)

        except Exception as e:
            fail += 1
            summary.append(f"异常: {str(e)}")

    title = f"GLaDOS ({domain}) 成功{success} 重复{repeat} 失败{fail}"
    content = "<br>".join(summary)

    print("\n=== Summary ===")
    print(title)
    print(content)

    if sendkey:
        send_wechat(sendkey, title, content)
    else:
        print("未设置 SENDKEY，不推送")
