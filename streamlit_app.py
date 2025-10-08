import streamlit as st
import httpx

st.set_page_config(page_title="Streamlit 外网取回器", layout="centered")

st.title("🌐 Streamlit 外网抓取演示")

url = st.text_input("输入要抓取的 URL：", "https://www.google.com")

if st.button("开始抓取"):
    st.info("正在请求，请稍候...")
    try:
        with httpx.Client(follow_redirects=True, timeout=20) as c:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            }
            r = c.get(url, headers=headers)
            st.success(f"状态码: {r.status_code}")
            st.write(f"响应头: {r.headers.get('content-type', '未知')}")
            if "text" in r.headers.get("content-type", ""):
                st.code(r.text[:2000], language="html")
            else:
                st.warning("非文本内容（可能是图片或视频），未展示。")
    except Exception as e:
        st.error(str(e))
