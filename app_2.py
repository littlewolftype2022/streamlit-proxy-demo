
# app_2.py
# 依赖：streamlit, requests, beautifulsoup4
import streamlit as st
import requests, os, io, re, base64, shutil, tempfile, mimetypes
from urllib.parse import urljoin, urlparse, urlencode, parse_qs
from bs4 import BeautifulSoup

st.set_page_config(page_title="交互抓取与打包", layout="wide")
st.title("🧩 交互抓取（表单提交）+ 资源打包 ZIP")

# --------- 会话与工具 ---------
def get_session():
    if "cookie_dict" not in st.session_state:
        st.session_state.cookie_dict = {}
    s = requests.Session()
    # 恢复 cookie
    for k,v in st.session_state.cookie_dict.items():
        s.cookies.set(k, v)
    # 常见请求头
    s.headers.update({
        "User-Agent": st.session_state.get("ua","Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
        "Accept": "*/*",
        "Accept-Language": st.session_state.get("al","zh-CN,zh;q=0.9,en;q=0.8"),
    })
    return s

def save_cookies(session):
    st.session_state.cookie_dict = {c.name:c.value for c in session.cookies}

def abs_url(base, link):
    return urljoin(base, link)

def safe_name_from_url(u):
    p = urlparse(u).path
    name = os.path.basename(p) or "index"
    q = urlparse(u).query
    if q: name += "_" + str(abs(hash(q)))[:8]
    if "." not in name:
        ext = mimetypes.guess_extension(os.path.basename(p)) or ""
        name += ext or ".bin"
    return name

# --------- 抓取页面 ---------
def fetch_page(url, method="GET", data=None):
    s = get_session()
    try:
        if method.upper() == "GET":
            r = s.get(url, params=data, allow_redirects=True, timeout=20)
        else:
            r = s.post(url, data=data, allow_redirects=True, timeout=20)
        save_cookies(s)
        base = f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}"
        return r, base
    except Exception as e:
        st.error(f"请求失败: {e}")
        return None, None

# --------- 解析表单 ---------
def parse_forms(html, base):
    soup = BeautifulSoup(html, "html.parser")
    forms = []
    for f in soup.find_all("form"):
        method = (f.get("method") or "GET").upper()
        action = f.get("action") or ""
        action = abs_url(base, action) if action else base
        inputs = {}
        meta = {}
        # input
        for inp in f.find_all("input"):
            t = (inp.get("type") or "text").lower()
            name = inp.get("name")
            if not name: continue
            val = inp.get("value") or ""
            if t in ("checkbox","radio"):
                if inp.has_attr("checked"):
                    inputs[name] = val or "on"
                else:
                    # 未选的先不提交；也可以建布尔开关
                    pass
            else:
                inputs[name] = val
            meta[name] = t
        # textarea
        for ta in f.find_all("textarea"):
            name = ta.get("name")
            if not name: continue
            inputs[name] = ta.text or ""
            meta[name] = "textarea"
        # select
        for se in f.find_all("select"):
            name = se.get("name")
            if not name: continue
            opt = se.find("option", selected=True) or se.find("option")
            val = opt.get("value") if opt else ""
            inputs[name] = val or ""
            meta[name] = "select"
        forms.append({"method":method, "action":action, "inputs":inputs, "meta":meta})
    return forms

# --------- 打包与重写（抓取资源 → 重写引用 → ZIP）---------
def pack_page(html, base, size_limit_mb=20, single_limit_mb=20, inline_small=True):
    soup = BeautifulSoup(html, "html.parser")
    tmpdir = tempfile.mkdtemp(prefix="pkg_")
    assets = os.path.join(tmpdir, "assets")
    os.makedirs(assets, exist_ok=True)

    total = 0
    s = get_session()

    def fetch_write(u):
        nonlocal total
        try:
            rr = s.get(u, timeout=15)
        except Exception:
            return None
        if rr.status_code != 200: return None
        if len(rr.content) > single_limit_mb*1024*1024: return None
        total += len(rr.content)
        name = safe_name_from_url(u)
        path = os.path.join(assets, name)
        with open(path, "wb") as f:
            f.write(rr.content)
        return path, rr.headers.get("content-type","application/octet-stream")

    # 标签映射
    tag_attr = {"img":"src","script":"src","link":"href","source":"src","video":"src","audio":"src","iframe":"src"}
    for tag, attr in tag_attr.items():
        for node in soup.find_all(tag):
            if not node.has_attr(attr): continue
            v = node.get(attr)
            if not v or v.startswith("data:") or v.startswith("javascript:"): continue
            u = abs_url(base, v)
            saved = fetch_write(u)
            if saved:
                p, ctype = saved
                # 小文件可 data:URI 内联
                if inline_small and os.path.getsize(p) < 256*1024:
                    with open(p, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("ascii")
                    mime = ctype or "application/octet-stream"
                    node[attr] = f"data:{mime};base64,{b64}"
                else:
                    node[attr] = f"assets/{os.path.basename(p)}"

    # link rel=stylesheet → 内联 css，并处理 url(...) 里的资源
    css_url_pat = re.compile(r'url\((.*?)\)', re.I)
    for link in list(soup.find_all("link", rel=lambda x: x and "stylesheet" in x)):
        href = link.get("href")
        if not href:
            link.decompose();
            continue
        css_url = abs_url(base, href)
        got = fetch_write(css_url)
        if not got:
            link.decompose();
            continue
        path, _ = got
        text = ""
        try:
            text = open(path,"r",encoding="utf-8",errors="ignore").read()
        except Exception:
            text = ""
        # 处理 url(...)
        for frag in css_url_pat.findall(text):
            frag_clean = frag.strip(' "\'')
            if frag_clean.startswith("data:"):
                continue
            full = abs_url(css_url, frag_clean)
            sub = fetch_write(full)
            if sub:
                spath, sctype = sub
                if inline_small and os.path.getsize(spath) < 200*1024:
                    b64 = base64.b64encode(open(spath,"rb").read()).decode("ascii")
                    mime = sctype or "application/octet-stream"
                    text = text.replace(frag, f"data:{mime};base64,{b64}")
                else:
                    text = text.replace(frag, f"assets/{os.path.basename(spath)}")
        style = soup.new_tag("style")
        style.string = text
        link.replace_with(style)

    # 保存重写后的 HTML
    index_path = os.path.join(tmpdir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(str(soup))

    # 体积提示
    total_mb = total/(1024*1024)
    zip_path = os.path.join(tmpdir, "site.zip")
    shutil.make_archive(zip_path[:-4], "zip", tmpdir)

    return index_path, zip_path, total_mb, tmpdir

# --------- UI ---------
with st.sidebar:
    st.header("会话设置")
    st.session_state.ua = st.text_input("User-Agent", value=st.session_state.get("ua","Mozilla/5.0 (Windows NT 10.0; Win64; x64)"))
    st.session_state.al = st.text_input("Accept-Language", value=st.session_state.get("al","zh-CN,zh;q=0.9,en;q=0.8"))
    clear = st.button("清空会话（Cookies）")
    if clear:
        st.session_state.cookie_dict = {}
        st.success("已清空 Cookie")

url = st.text_input("初始 URL（例如 https://www.google.com/）", "https://www.google.com/")
go = st.button("抓取该页面")

if go:
    r, base = fetch_page(url, "GET")
    if r:
        st.session_state.last_html = r.text
        st.session_state.last_base = base
        st.success(f"已抓取：{r.url}")

if "last_html" in st.session_state:
    html = st.session_state.last_html
    base = st.session_state.last_base
    forms = parse_forms(html, base)
    st.subheader(f"检测到表单：{len(forms)} 个")
    if forms:
        idx = st.number_input("选择表单序号（从 0 开始）", min_value=0, max_value=len(forms)-1, value=0, step=1)
        f = forms[idx]
        st.write(f"Method: {f['method']}   Action: {f['action']}")
        # 生成可编辑字段
        with st.form(key=f"form_{idx}"):
            fields = {}
            for name, val in f["inputs"].items():
                # 常见搜索字段名给个示例
                placeholder = "（修改）"
                if name in ("q","query","wd","keyword","search"):
                    placeholder = "例如：苹果"
                fields[name] = st.text_input(name, value=val, placeholder=placeholder)
            submitted = st.form_submit_button("提交此表单")
        if submitted:
            data = {k:v for k,v in fields.items() if v is not None}
            if f["method"] == "GET":
                r2, base2 = fetch_page(f["action"], "GET", data=data)
            else:
                r2, base2 = fetch_page(f["action"], "POST", data=data)
            if r2:
                st.session_state.last_html = r2.text
                st.session_state.last_base = base2
                st.success(f"表单提交成功：{r2.url}")

    # 链接快速跟随（可选）
    soup_view = BeautifulSoup(st.session_state.last_html, "html.parser")
    links = [(a.get_text(strip=True)[:40], urljoin(st.session_state.last_base, a.get("href")))
             for a in soup_view.find_all("a") if a.get("href")]
    if links:
        st.subheader("页面链接（前20条）")
        for i,(txt,href) in enumerate(links[:20]):
            st.write(f"{i}. {txt or '(无标题)'} — {href}")
        jump = st.text_input("输入要打开的链接序号（0-19）后回车", "")
        if jump.isdigit():
            i = int(jump)
            if 0 <= i < min(20,len(links)):
                _, href = links[i]
                r3, base3 = fetch_page(href, "GET")
                if r3:
                    st.session_state.last_html = r3.text
                    st.session_state.last_base = base3
                    st.success(f"已打开：{r3.url}")

    # 打包并预览
    st.subheader("打包与预览")
    limit_all = st.number_input("打包资源总体上限 (MB)", min_value=1, value=20)
    limit_one = st.number_input("单个资源上限 (MB)", min_value=1, value=20)
    inline_small = st.checkbox("小文件内联(data:URI)", value=True)
    if st.button("开始打包（ZIP）并预览"):
        idx_path, zip_path, total_mb, tmpdir = pack_page(
            st.session_state.last_html, st.session_state.last_base,
            size_limit_mb=limit_all, single_limit_mb=limit_one, inline_small=inline_small
        )
        st.write(f"资源抓取体积约：{total_mb:.2f} MB")
        # 预览
        try:
            html_preview = open(idx_path, "r", encoding="utf-8").read()
            st.components.v1.html(html_preview, height=800, scrolling=True)
        except Exception:
            st.info("页面过大/含复杂脚本，预览可能不完整，请直接下载 ZIP 本地打开。")
        # 下载
        with open(zip_path, "rb") as f:
            st.download_button("下载 ZIP", f, file_name="site.zip", mime="application/zip")
        st.caption(f"临时目录：{tmpdir}（部署端的临时路径，稍后会清理）")
