# import streamlit as st
# import httpx

# st.set_page_config(page_title="Streamlit 外网取回器", layout="centered")

# st.title("🌐 Streamlit 外网抓取演示")

# url = st.text_input("输入要抓取的 URL：", "https://www.google.com")

# if st.button("开始抓取"):
#     st.info("正在请求，请稍候...")
#     try:
#         with httpx.Client(follow_redirects=True, timeout=20) as c:
#             headers = {
#                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
#             }
#             r = c.get(url, headers=headers)
#             st.success(f"状态码: {r.status_code}")
#             st.write(f"响应头: {r.headers.get('content-type', '未知')}")
#             if "text" in r.headers.get("content-type", ""):
#                 st.code(r.text[:2000], language="html")
#             else:
#                 st.warning("非文本内容（可能是图片或视频），未展示。")
#     except Exception as e:
#         st.error(str(e))
# streamlit_inline_proxy.py
# 依赖: pip install streamlit httpx beautifulsoup4 lxml

import streamlit as st
import httpx, base64, urllib.parse
from bs4 import BeautifulSoup

st.set_page_config(page_title="Inline Proxy (weak)", layout="wide")
st.title("Inline Proxy — 将资源内联到 HTML（受限）")

url = st.text_input("目标 URL", "https://example.com")
if st.button("抓取并展示（Inline）"):
    try:
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            r = client.get(url, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code != 200:
            st.error(f"状态码: {r.status_code}")
        else:
            soup = BeautifulSoup(r.text, "lxml")
            base = urllib.parse.urljoin(url, "/")
            # inline css/js/img
            # handle link rel=stylesheet
            for link in list(soup.find_all("link", rel="stylesheet")):
                href = link.get("href")
                abs_url = urllib.parse.urljoin(base, href)
                try:
                    rr = client.get(abs_url, timeout=10)
                    style_tag = soup.new_tag("style")
                    style_tag.string = rr.text
                    link.replace_with(style_tag)
                except Exception:
                    link.decompose()
            # handle scripts
            for s in list(soup.find_all("script", src=True)):
                src = s.get("src")
                abs_url = urllib.parse.urljoin(base, src)
                try:
                    rr = client.get(abs_url, timeout=10)
                    new_s = soup.new_tag("script")
                    new_s.string = rr.text
                    s.replace_with(new_s)
                except Exception:
                    s.decompose()
            # handle images
            for img in list(soup.find_all("img", src=True)):
                src = img.get("src")
                abs_url = urllib.parse.urljoin(base, src)
                try:
                    rr = client.get(abs_url, timeout=10)
                    data = base64.b64encode(rr.content).decode("ascii")
                    mime = rr.headers.get("content-type","image/png")
                    img['src'] = f"data:{mime};base64,{data}"
                except Exception:
                    img.decompose()
            # final HTML
            final_html = str(soup)
            st.components.v1.html(final_html, height=800, scrolling=True)
    except Exception as e:
        st.error(str(e))

