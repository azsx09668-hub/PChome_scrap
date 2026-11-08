# -*- coding: utf-8 -*-
import time

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# 基本設定
# ---------------------------------------------------------------------------
st.set_page_config(page_title="PChome 商品價格分析", page_icon="🛒", layout="wide")

API_URL = "https://ecshweb.pchome.com.tw/search/v3.3/all/results"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

SORT_OPTIONS = {
    "銷量高到低": "sale/dc",
    "價格低到高": "prc/ac",
    "價格高到低": "prc/dc",
    "相關度": "rnk/dc",
}


# ---------------------------------------------------------------------------
# 資料爬取（CODE01）
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def fetch_page(keyword: str, page: int, sort: str) -> list[dict]:
    """抓取單一頁的商品資料（快取 10 分鐘）。"""
    params = {"q": keyword, "page": page, "sort": sort}
    resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("prods", []) or []


def fetch_all(keyword: str, pages: int, sort: str, delay: float) -> pd.DataFrame:
    """依序抓取多頁資料並合併成 DataFrame。"""
    frames = []
    progress = st.progress(0.0, text="開始抓取資料...")
    for i in range(1, pages + 1):
        progress.progress((i - 1) / pages, text=f"正在抓取第 {i} / {pages} 頁...")
        prods = fetch_page(keyword, i, sort)
        if not prods:  # 沒有更多資料就提前結束
            break
        frames.append(pd.DataFrame(prods))
        if i < pages:
            time.sleep(delay)  # 避免請求過於頻繁
    progress.empty()

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# 資料處理（CODE02）
# ---------------------------------------------------------------------------
def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """只保留商品名稱與價格，並清理資料。"""
    out = df[["name", "price"]].copy()
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    out = out.dropna().reset_index(drop=True)
    out["id"] = out.index + 1
    out["short_name"] = out["id"].astype(str) + ". " + out["name"].str.slice(0, 18)
    return out


def add_price_range(df: pd.DataFrame, bins: int = 5) -> pd.DataFrame:
    """依價格範圍分成 N 個區間，供圓餅圖與旭日圖使用。"""
    out = df.copy()
    lo, hi = out["price"].min(), out["price"].max()
    if lo == hi:
        out["price_range"] = f"{int(lo):,}"
        return out

    edges = np.linspace(lo, hi, bins + 1)
    labels = [f"{int(edges[i]):,} ~ {int(edges[i + 1]):,}" for i in range(bins)]
    out["price_range"] = pd.cut(
        out["price"], bins=edges, labels=labels, include_lowest=True
    ).astype(str)
    return out


# ---------------------------------------------------------------------------
# 介面
# ---------------------------------------------------------------------------
st.title("🛒 PChome 商品價格查詢與視覺化")

with st.sidebar:
    st.header("查詢條件")
    keyword = st.text_input("商品關鍵字", value="冰箱")
    pages = st.number_input("抓取頁數", min_value=1, max_value=20, value=2, step=1)
    sort_label = st.selectbox("排序方式", list(SORT_OPTIONS.keys()))
    delay = st.slider("每頁間隔秒數", 0.0, 5.0, 1.0, 0.5,
                      help="間隔太短可能被網站暫時封鎖")
    bins = st.slider("價格區間數量", 3, 10, 5)
    run = st.button("🔍 查詢", type="primary", use_container_width=True)

# 查詢結果存入 session_state，避免調整元件時重新查詢
if run:
    if not keyword.strip():
        st.warning("請輸入商品關鍵字。")
    else:
        try:
            raw = fetch_all(keyword.strip(), int(pages), SORT_OPTIONS[sort_label], delay)
        except requests.exceptions.RequestException as e:
            st.error(f"抓取資料失敗：{e}")
            st.stop()
        except ValueError:
            st.error("網站回傳的資料格式無法解析，請稍後再試。")
            st.stop()

        if raw.empty or not {"name", "price"}.issubset(raw.columns):
            st.warning(f"找不到「{keyword}」的商品資料，請換個關鍵字試試。")
            st.session_state.pop("result", None)
        else:
            st.session_state["result"] = {
                "keyword": keyword.strip(),
                "df": prepare(raw),
            }

if "result" not in st.session_state:
    st.info("👈 請在左側輸入商品與頁數，然後按下「查詢」。")
    st.stop()

kw = st.session_state["result"]["keyword"]
df = st.session_state["result"]["df"]
if df.empty:
    st.warning("沒有可用的價格資料。")
    st.stop()

mean_price = df["price"].mean()

# ---- 統計摘要 ----
st.subheader(f"「{kw}」查詢結果")
c1, c2, c3, c4 = st.columns(4)
c1.metric("商品數量", f"{len(df):,}")
c2.metric("平均價格", f"{mean_price:,.0f}")
c3.metric("最高價格", f"{df['price'].max():,.0f}")
c4.metric("最低價格", f"{df['price'].min():,.0f}")

tab_line, tab_pie, tab_sun, tab_table = st.tabs(
    ["📈 折線圖", "🥧 圓餅圖", "☀️ 旭日圖", "📋 資料表"]
)

# ---- 折線圖 ----
with tab_line:
    fig = px.line(
        df, x="id", y="price", markers=True,
        hover_data={"name": True, "id": False},
        labels={"id": "商品序號", "price": "價格"},
        title=f"PChome 電商網站上「{kw}」售價",
    )
    fig.add_hline(
        y=mean_price, line_dash="dash", line_color="red",
        annotation_text=f"平均價 {mean_price:,.0f}",
        annotation_position="top left",
    )
    st.plotly_chart(fig, use_container_width=True)

# 圓餅圖與旭日圖共用的價格區間資料
ranged = add_price_range(df, bins)

# ---- 圓餅圖 ----
with tab_pie:
    pie_df = ranged.groupby("price_range", sort=False).size().reset_index(name="count")
    fig = px.pie(
        pie_df, names="price_range", values="count", hole=0.3,
        title=f"「{kw}」價格區間分布（商品數量）",
    )
    fig.update_traces(textinfo="percent+label+value")
    st.plotly_chart(fig, use_container_width=True)

# ---- 旭日圖 ----
with tab_sun:
    sun_df = ranged.copy()
    sun_df["root"] = f"{kw}（全部）"
    fig = px.sunburst(
        sun_df, path=["root", "price_range", "short_name"], values="price",
        title=f"「{kw}」價格區間 → 商品（面積代表價格）",
    )
    fig.update_layout(height=700)
    st.plotly_chart(fig, use_container_width=True)

# ---- 資料表 ----
with tab_table:
    show = df[["id", "name", "price"]].rename(
        columns={"id": "序號", "name": "商品名稱", "price": "價格"}
    )
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ 下載 CSV",
        data=show.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"PCHOME_{kw}.csv",
        mime="text/csv",
    )
