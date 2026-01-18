import streamlit as st
import unicodedata

# ==========================================
# 🔑 パスワード設定
# ==========================================
LOGIN_PASSWORD = "88888"
ADMIN_CODE = "888888"

# ==========================================
# ページ設定
# ==========================================
st.set_page_config(page_title="GENTAs-AI", layout="wide")

# ==========================================
# 🔐 認証機能（門番）
# ==========================================
def check_password():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    
    if not st.session_state["logged_in"]:
        st.markdown("## 🔒 ACCESS RESTRICTED")
        password_input = st.text_input("パスワードを入力してください", type="password")
        
        if st.button("ログイン"):
            input_norm = unicodedata.normalize('NFKC', password_input).upper().strip()
            secret_norm = unicodedata.normalize('NFKC', LOGIN_PASSWORD).upper().strip()
            
            if input_norm == secret_norm:
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("パスワードが違います 🙅")
        st.stop()

# -----------------------------
# 実行！
# -----------------------------
check_password()


# ==========================================
# 🎉 ここから下に「中身」を書く
# ==========================================

st.title("🚀 GENTAs-AI へようこそ！")
st.success("認証成功！ここはパスワードを知っている人だけの秘密基地です。")

# ↓↓↓ ここに新しいツールのコードを書いていく ↓↓↓

st.write("まずはここからスタートしましょう！")
if st.button("クリックしてみて！"):
    st.balloons()

# ------------------------------------------
# 🔧 管理者メニュー
# ------------------------------------------
st.divider()
with st.expander("🔧 管理者メニュー"):
    admin_input = st.text_input("管理者コード", type="password")
    if admin_input == ADMIN_CODE:
        st.success("管理者認証OK！")
        if st.button("キャッシュ削除"):
            st.cache_data.clear()
            st.success("削除しました")
