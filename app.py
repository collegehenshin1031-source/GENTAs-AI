"""
HAGETAKA SCOPE - 統合版（英字コード完全対応・高度キャッシュシステム搭載）
"""

import json
import re
import smtplib
import io
import requests
import random
import unicodedata
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional
from pathlib import Path
import streamlit as st
from datetime import datetime
import pytz
import base64
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Google Sheets連携
from streamlit_gsheets import GSheetsConnection
import gspread
from google.oauth2.service_account import Credentials

# 暗号化
from cryptography.fernet import Fernet

# ==========================================
# 定数
# ==========================================
JST = pytz.timezone("Asia/Tokyo")
MARKET_CAP_MIN = 300
MARKET_CAP_MAX = 2000

FLOW_SCORE_HIGH = 70
FLOW_SCORE_MEDIUM = 40

LEVEL_COLORS = {4: "#C41E3A", 3: "#FF9800", 2: "#FFC107", 1: "#5C6BC0", 0: "#9E9E9E"}

MASTER_PASSWORD = "88888"
DISCLAIMER_TEXT = "本ツールは市場データの可視化を目的とした補助ツールです。<br>銘柄推奨・売買助言ではありません。最終判断は利用者ご自身で行ってください。"

# ==========================================
# UI設定・CSS
# ==========================================
st.set_page_config(page_title="源太AI🤖ハゲタカSCOPE", page_icon="🦅", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
header { visibility: hidden !important; display: none !important; }
#MainMenu, footer, .stDeployButton { display: none !important; }
.stApp { font-family: 'Inter', sans-serif !important; }

/* カードデザイン */
.spike-card{
    background-color: var(--secondary-background-color) !important; 
    border-radius: 16px; padding: 1rem; margin-bottom: .75rem; 
    border: 1px solid rgba(128,128,128,0.2) !important;
    box-shadow: 0 10px 30px rgba(0,0,0,0.05);
}
.ticker-name a{ font-weight: 800; color: var(--text-color) !important; text-decoration:none; font-size: 1.1rem; }
.price-val { color: #ff4b4b !important; font-weight: 800; }
.level-badge { padding: 3px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; color: white !important; }

/* 診断カード枠 */
div[data-testid="stVerticalBlock"]:has(> div:nth-child(1) .diagnosis-card-marker) {
    background-color: var(--secondary-background-color) !important;
    border: 2px solid rgba(128, 128, 128, 0.2) !important;
    border-radius: 16px !important;
    padding: 1.5rem !important;
    margin-bottom: 2rem !important;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 共通ヘルパー関数
# ==========================================

def get_fernet() -> Fernet: return Fernet(st.secrets["encryption"]["key"].encode())

def get_gsheets_connection(): return st.connection("gsheets", type=GSheetsConnection)

def get_gspread_client():
    try:
        cd = dict(st.secrets["connections"]["gsheets"])
        cd.pop("spreadsheet", None); cd.pop("worksheet", None)
        creds = Credentials.from_service_account_info(cd, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds)
    except: return None

def save_settings_to_sheet(email: str, app_password: str) -> bool:
    try:
        client = get_gspread_client()
        url = st.secrets["connections"]["gsheets"].get("spreadsheet")
        ws = client.open_by_url(url).worksheet("settings")
        enc_pw = get_fernet().encrypt(app_password.encode()).decode()
        all_emails = ws.col_values(1)
        row_index = next((i + 1 for i, ce in enumerate(all_emails) if ce and ce.lower().strip() == email.lower().strip()), -1)
        if row_index > 1: ws.update_cell(row_index, 2, enc_pw)
        else: ws.append_row([email.lower().strip(), enc_pw])
        return True
    except: return False

def delete_settings_from_sheet(email: str) -> bool:
    try:
        client = get_gspread_client()
        url = st.secrets["connections"]["gsheets"].get("spreadsheet")
        ws = client.open_by_url(url).worksheet("settings")
        all_emails = ws.col_values(1)
        row_index = next((i + 1 for i, ce in enumerate(all_emails) if ce and ce.lower().strip() == email.lower().strip()), -1)
        if row_index > 1: ws.delete_rows(row_index); return True
    except: pass
    return False

# ==========================================
# ハゲタカ診断エンジン用関数
# ==========================================

@st.cache_data(ttl=86400)
def get_jpx_data():
    try:
        html_url = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(html_url, headers=headers, timeout=10)
        match = re.search(r'href="([^"]+data_j\.xls)"', res.text)
        if not match: return {}, []
        df = pd.read_excel("https://www.jpx.co.jp" + match.group(1))
        
        def safe_code(x):
            if pd.isnull(x): return ""
            s = str(x).strip()
            if s.endswith('.0'): return s[:-2]
            return s
            
        codes = df.iloc[:, 1].apply(safe_code)
        return dict(zip(codes, df.iloc[:, 2])), list(codes)
    except: return {}, []

jpx_names, _ = get_jpx_data()

def format_market_cap(oku_val):
    oku_val = int(oku_val)
    if oku_val >= 10000:
        cho, oku = divmod(oku_val, 10000)
        return f"{cho}兆{oku}億円" if oku else f"{cho}兆円"
    return f"{oku_val}億円"

def normalize_input(input_text):
    if not input_text: return []
    text = unicodedata.normalize('NFKC', input_text).upper()
    text = re.sub(r'[\s,、\n\r]+', ' ', text)
    codes = [c.strip() for c in text.split(' ') if c.strip()]
    return list(dict.fromkeys(codes))


# 🚨 成功したデータのみを保持するカスタムキャッシュ領域
_SUCCESS_CACHE = {}
_CACHE_TTL_SECONDS = 900  # 15分（ブロック回避のための保護期間）

def evaluate_stock(ticker):
    now = datetime.now(JST)
    
    # 1. キャッシュの確認（成功データのみがここを通る）
    if ticker in _SUCCESS_CACHE:
        cached_time, cached_data = _SUCCESS_CACHE[ticker]
        if (now - cached_time).total_seconds() < _CACHE_TTL_SECONDS:
            return cached_data

    # 2. 実際のデータ取得と計算
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="2y")
        
        if hist is None or hist.empty: 
            return {"status": "not_found"}
            
        info = stock.info or {}
        
        try:
            current_price = float(hist['Close'].iloc[-1])
            current_vol = float(hist['Volume'].iloc[-1])
        except IndexError:
            return {"status": "not_found"}
        
        avg_vol_100 = hist['Volume'][-100:].mean() if len(hist) >= 100 else hist['Volume'].mean()
        
        shares = info.get('sharesOutstanding')
        shares = float(shares) if shares is not None else 0.0
        
        mc = info.get('marketCap')
        mc = float(mc) if mc is not None else (current_price * shares)
        market_cap_oku = mc / 1e8
        
        is_tob = False
        if len(hist) >= 5:
            recent_5 = hist.tail(5)
            if current_price > 0 and (recent_5['High'].max() - recent_5['Low'].min()) / current_price * 100 < 1.0 and current_vol > 10000:
                is_tob = True

        div_rate = info.get('dividendRate') or info.get('trailingAnnualDividendRate')
        div_rate = float(div_rate) if div_rate is not None else 0.0
        
        payout = info.get('payoutRatio')
        payout = float(payout) if payout is not None else 0.0
        
        if div_rate > 0 and current_price > 0:
            yield_str = f"{(div_rate / current_price) * 100:.2f}%"
            dividend_text = f"{div_rate}円 (利回り: {yield_str} / 配当性向: {payout*100:.1f}%)"
        else:
            dividend_text = "無配"

        turnover = (current_vol / shares * 100) if shares > 0 else 0
        if turnover >= 10: turn_str = f"🔥🔥🔥 {turnover:.2f}% (超異常値)"
        elif turnover >= 5: turn_str = f"🔥🔥 {turnover:.2f}% (大口介入期待)"
        elif turnover >= 2: turn_str = f"🔥 {turnover:.2f}% (動意)"
        else: turn_str = f"💤 {turnover:.2f}% (平常)"

        score = 10
        if 500 <= market_cap_oku <= 2000: score += 35
        if avg_vol_100 > 0 and current_vol / avg_vol_100 >= 3: score += 40
        elif avg_vol_100 > 0 and current_vol / avg_vol_100 >= 1.5: score += 25
        score = min(90, score)

        hist_6mo = hist.tail(125)
        
        try:
            unique_prices = hist_6mo['Close'].unique()
            if len(unique_prices) > 1:
                bins_count = min(15, len(unique_prices))
                price_bins = pd.cut(hist_6mo['Close'], bins=bins_count)
                max_vol_price = hist_6mo.groupby(price_bins, observed=False)['Volume'].sum().idxmax().mid
            else:
                max_vol_price = current_price
        except Exception:
            max_vol_price = current_price

        deviation = ((current_price - max_vol_price) / max_vol_price) * 100 if max_vol_price > 0 else 0.0
        
        stars = "★" * min(5, int((max_vol_price/current_price-1)*10)+1) if current_price < max_vol_price else "★★★★★"

        result = {
            "status": "success",
            "コード": ticker.replace(".T",""), "銘柄名": jpx_names.get(ticker.replace(".T",""), ticker),
            "現在値": int(current_price), "時価総額_表示": format_market_cap(market_cap_oku),
            "dividend_text": dividend_text, "turnover_str": turn_str, "ランク": "S" if score > 80 else "A" if score > 60 else "B",
            "乖離率": float(deviation), "hist": hist, "max_vol_price": float(max_vol_price), 
            "recent_20_low": float(hist['Low'][-20:].min()) if len(hist) >= 20 else float(hist['Low'].min()),
            "intervention_score": int(score), "safe_judgment": "🚀 安全圏" if 0 < deviation < 10 else "📉 割安" if deviation < 0 else "⚠️ 警戒",
            "is_tob_suspected": is_tob, "star_rating": stars
        }
        
        # 🚨 3. 成功した場合にのみ、15分キャッシュ領域へ保存
        _SUCCESS_CACHE[ticker] = (now, result)
        return result
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==========================================
# 画面描画
# ==========================================

def show_main_page():
    st.sidebar.title("🦅 ハゲタカ戦略室")
    st.sidebar.markdown(f"""
    <div style='border: 1px solid #ff4b4b; border-radius: 10px; padding: 12px; background: rgba(255,75,75,0.05);'>
    <h4 style='color:#ff4b4b; margin:0;'>🦅 記号の解説</h4>
    <ul style='font-size:0.85rem; padding-left:15px; margin:10px 0 0 0;'>
        <li><b>💎 プラチナ</b>: 500億～2000億<br><span style='color:#888;'>最も仕掛けやすい黄金サイズ</span></li>
        <li style='margin-top:8px;'><b>🦅 ハゲタカ参戦？</b>: 出来高1.5倍↑<br><span style='color:#888;'>水面下での「仕込み」疑惑あり</span></li>
        <li style='margin-top:8px;'><b>🧬 DNA</b>: 過去急騰実績あり<br><span style='color:#888;'>「主」が住み着いている可能性</span></li>
    </ul>
    </div>
    """, unsafe_allow_html=True)
    
    current_month = datetime.now(JST).month
    strategies = {3: "📉 **3月：彼岸底＆仕込み**\n中旬の調整は優良株を拾う最大のチャンス！", 4: "🔥 **4月：ニューマネー流入**\n新年度予算で中小型株が吹き上がります。"}
    st.sidebar.info(strategies.get(current_month, "戦略待機中"))

    tab1, tab2, tab3 = st.tabs(["📊 M&A候補", "🦅 ハゲタカ診断", "🔔 通知設定"])

    with tab1:
        data = Path("data/ratios.json")
        if data.exists():
            d = json.load(data.open(encoding="utf-8"))
            st.caption(f"最終更新: {d.get('updated_at')}")
            for tk, it in list(d.get("data", {}).items())[:20]:
                st.markdown(f"""
                <div class="spike-card">
                    <div style="display:flex; justify-content:space-between;">
                        <b>{tk.replace('.T','')} {it.get('name')}</b>
                        <span class="level-badge" style="background:{LEVEL_COLORS.get(it.get('level',0))}">LEVEL {it.get('level')}</span>
                    </div>
                    <div style="margin-top:8px; font-size:0.9rem;">
                        現在値: <span class="price-val">¥{it.get('price'):,.0f}</span> | 需給スコア: <b>{it.get('flow_score')}</b>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    with tab2:
        st.markdown("##### 🔍 銘柄診断（複数可）")
        with st.form("diag"):
            input_text = st.text_area("銘柄コード", placeholder="例: 7011 7203\n151a 151A\n改行やスペース区切りで入力")
            submit = st.form_submit_button("🦅 ハゲタカAIで診断する")
            
            if submit and input_text:
                codes = normalize_input(input_text)
                if not codes:
                    st.error("銘柄コードを入力してください")
                elif len(codes) > 5:
                    st.error("⚠️ サーバー負荷軽減のため、一度に診断できるのは最大5銘柄までです。銘柄数を減らして再度お試しください。")
                else:
                    for c in codes:
                        res = evaluate_stock(f"{c}.T")
                        
                        # 🚨 厳密にステータスを判定して表示を分ける
                        if res["status"] == "not_found":
                            st.error(f"❌ 【 {c} 】 : 存在しない銘柄です。")
                        
                        elif res["status"] == "error":
                            st.error(f"❌ 【 {c} 】 : 分析中に通信・計算エラーが発生しました。({res.get('message', '')})")
                        
                        elif res["status"] == "success":
                            st.markdown('<div class="diagnosis-card-marker"></div>', unsafe_allow_html=True)
                            if res['is_tob_suspected']: st.warning("🚨 TOB・MBOの可能性が高い値動きです。")
                            col1, col2 = st.columns([1, 2])
                            with col1:
                                st.subheader(f"{res['コード']} {res['銘柄名']}")
                                st.write(f"判定: **{res['ランク']}**")
                                st.write(f"利回り: {res['dividend_text']}")
                                st.write(f"熱量: {res['turnover_str']}")
                                st.write(f"介入期待度: {res['intervention_score']}%")
                                st.progress(res['intervention_score']/100)
                            with col2:
                                st.write(f"上値余地: {res['star_rating']}")
                                st.info(f"安全性: {res['safe_judgment']} (壁から {res['乖離率']:.1f}%)")
                                fig = go.Figure(data=[go.Candlestick(x=res['hist'].index, open=res['hist']['Open'], high=res['hist']['High'], low=res['hist']['Low'], close=res['hist']['Close'])])
                                fig.update_layout(height=250, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                                st.plotly_chart(fig, use_container_width=True)

    with tab3:
        email = st.text_input("Gmail", value=st.session_state.get("email_address", ""))
        pw = st.text_input("App Password", type="password")
        if st.button("💾 保存"):
            if save_settings_to_sheet(email, pw): st.success("保存完了")
            else: st.error("失敗")

# ==========================================
# ログイン・メイン制御
# ==========================================
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    _, col, _ = st.columns([1,2,1])
    with col:
        st.title("🦅 ハゲタカSCOPE")
        pw = st.text_input("Password", type="password")
        if st.button("Login"):
            if pw == MASTER_PASSWORD: st.session_state["logged_in"] = True; st.rerun()
            else: st.error("Invalid")
else:
    show_main_page()
