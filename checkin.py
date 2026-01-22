import requests
import json
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


if __name__ == '__main__':

    sckey = os.environ.get("SENDKEY", "")
    cookies = os.environ.get("COOKIES", "").split("&")

    if not cookies or cookies[0] == "":
        print("未找到 cookies")
        exit(0)

    check_in_url = "https://glados.space/api/user/checkin"
    status_url = "https://glados.space/api/user/status"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "Referer": "https://glados.space/console/checkin",
        "Origin": "https://glados.space",
        "Content-Type": "application/json;charset=UTF-8",
    }

    payload = {"token": "glados.one"}

    success, fail, repeat = 0, 0, 0
    context_lines = []

    for idx, cookie in enumerate(cookies, 1):
        print(f"\n==== Account {idx} ====")

        session = requests.Session()
        session.headers.update(headers)
        session.headers.update({"Cookie": cookie})

        try:
            # 签到
            r = session.post(check_in_url, json=payload, timeout=15)
            print("Checkin response:", r.text)

            try:
                result = r.json()
            except Exception:
                fail += 1
                context_lines.append("签到返回非 JSON，可能被风控")
                continue

            msg = result.get("message", "")
            points = result.get("points", 0)

            if "Checkin! Got" in msg:
                success += 1
                status_msg = f"签到成功 +{points}"
            elif "Repeats" in msg:
                repeat += 1
                status_msg = "重复签到"
            else:
                fail += 1
                status_msg = f"签到失败: {msg}"
                context_lines.append(status_msg)
                continue  # 失败直接跳过 status 请求

            # 查询状态
            r2 = session.get(status_url, timeout=15)
            data = r2.json().get("data", {})

            email = data.get("email", "unknown")
            left_days = data.get("leftDays", "NA")

            context_lines.append(
                f"{email} | {status_msg} | 剩余 {left_days} 天"
            )

            time.sleep(2)  # 降低风控风险

        except Exception as e:
            fail += 1
            context_lines.append(f"异常: {str(e)}")

    title = f"GLaDOS: 成功{success} 重复{repeat} 失败{fail}"
    context = "<br>".join(context_lines)

    print("\n=== Summary ===")
    print(title)
    print(context)

    if sckey:
        send_wechat(sckey, title, context)
    else:
        print("未设置 SENDKEY，不推送")
