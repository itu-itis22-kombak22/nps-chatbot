"""
NPS Chatbot — Streamlit UI

Çalıştır:
    streamlit run ui/app.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import pandas as pd
import plotly.express as px

from chatbot.engine import NPSChatbot
from chatbot.data_loader import get_raw, get_summary_table
from chatbot.intent_router import State

# ──────────────────────────────────────────────────────────────────────────────
# Sayfa yapılandırması
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NPS Chatbot",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────────────────────────────────────
if "bot" not in st.session_state:
    st.session_state.bot = NPSChatbot(use_llm=True)
if "messages" not in st.session_state:
    st.session_state.messages = []
if "use_llm" not in st.session_state:
    st.session_state.use_llm = True

# ──────────────────────────────────────────────────────────────────────────────
# Sidebar — Ayarlar ve Metrikler
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Ayarlar")

    use_llm = st.toggle("LLM Kullan (Groq / On-prem)", value=True,
                        help="Kapalıysa sadece keyword eşleşmesi, selamlama ve genel sorular çalışmaz.")
    if use_llm != st.session_state.use_llm:
        st.session_state.use_llm = use_llm
        st.session_state.bot = NPSChatbot(use_llm=use_llm)

    if st.button("🔄 Konuşmayı Sıfırla"):
        st.session_state.messages = []
        st.session_state.bot.reset()
        st.rerun()

    st.divider()

    # Chatbot state göstergesi
    bot_state = st.session_state.bot.router.current_state
    state_color = {
        State.DIRECT:   "🟢",
        State.DETAIL:   "🟡",
        State.RESPONSE: "🔵",
    }
    st.markdown(f"**Bot State:** {state_color.get(bot_state, '⚪')} `{bot_state.name}`")

    st.divider()
    st.subheader("📈 Hızlı Metrikler")

    try:
        df_all = get_raw()
        total  = len(df_all)
        avg    = df_all["NPS_SCORE"].mean()
        det    = len(df_all[df_all["NPS_SCORE"] <= 6]) / total * 100
        pro    = len(df_all[df_all["NPS_SCORE"] >= 9]) / total * 100

        col1, col2 = st.columns(2)
        col1.metric("Toplam Yorum", f"{total:,}")
        col2.metric("Ort. NPS", f"{avg:.1f}")
        col1.metric("Detractor", f"%{det:.1f}")
        col2.metric("Promoter", f"%{pro:.1f}")
    except Exception:
        st.warning("Metrikler yüklenemedi.")

    st.divider()

    # Örnek sorular
    st.subheader("💡 Örnek Sorular")
    examples = [
        "Bu haftaki NPS özeti nedir?",
        "Mobil bankacılık şikayetleri neler?",
        "Detractor müşterilerden örnek yorum göster",
        "Aylık segment dağılımı nasıl?",
        "Kızgın müşteriler hangi konuları şikayet ediyor?",
    ]
    for ex in examples:
        if st.button(ex, key=f"ex_{ex[:20]}"):
            st.session_state._quick_msg = ex
            st.rerun()

# ──────────────────────────────────────────────────────────────────────────────
# Ana alan — iki sekme: Chat | Dashboard
# ──────────────────────────────────────────────────────────────────────────────
tab_chat, tab_dash = st.tabs(["💬 Chatbot", "📊 Dashboard"])

# ── Chat sekmesi ──────────────────────────────────────────────────────────────
with tab_chat:
    st.title("📊 NPS Chatbot")
    st.caption("Banka NPS verisi üzerine sorular sorun.")

    # Geçmiş mesajları göster
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Sidebar'dan hızlı mesaj geldi mi?
    quick = st.session_state.pop("_quick_msg", None)
    prompt = st.chat_input("Sorunuzu yazın…") or quick

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Düşünüyorum…"):
                response = st.session_state.bot.chat(prompt)
            st.markdown(response)

        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()

# ── Dashboard sekmesi ─────────────────────────────────────────────────────────
with tab_dash:
    st.title("📊 NPS Dashboard")

    try:
        period_sel = st.selectbox("Periyot", ["haftalık", "aylık", "tümü"])
        df = get_raw(period=None if period_sel == "tümü" else period_sel)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Yorum", f"{len(df):,}")
        col2.metric("Ort. NPS", f"{df['NPS_SCORE'].mean():.2f}")
        col3.metric("Detractor %", f"{len(df[df['NPS_SCORE']<=6])/len(df)*100:.1f}%")
        col4.metric("Promoter %",  f"{len(df[df['NPS_SCORE']>=9])/len(df)*100:.1f}%")

        st.divider()
        c1, c2 = st.columns(2)

        with c1:
            st.subheader("NPS Dağılımı")
            nps_dist = df["NPS_SCORE"].value_counts().sort_index().reset_index()
            nps_dist.columns = ["NPS", "Adet"]
            fig = px.bar(nps_dist, x="NPS", y="Adet",
                         color="NPS",
                         color_continuous_scale=["#e74c3c","#f39c12","#2ecc71"],
                         labels={"NPS": "NPS Skoru", "Adet": "Yorum Sayısı"})
            fig.update_layout(showlegend=False, height=300)
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.subheader("Yorum Tipi Dağılımı")
            ct = df["COMMENT_TYPE"].value_counts().reset_index()
            ct.columns = ["Tip", "Adet"]
            fig2 = px.pie(ct, values="Adet", names="Tip", hole=0.4)
            fig2.update_layout(height=300)
            st.plotly_chart(fig2, use_container_width=True)

        st.divider()
        c3, c4 = st.columns(2)

        with c3:
            st.subheader("Top 10 Ana Kategori")
            cat = df["FIRST_MAIN_CATEGORY"].value_counts().head(10).reset_index()
            cat.columns = ["Kategori", "Adet"]
            fig3 = px.bar(cat, x="Adet", y="Kategori", orientation="h",
                          color="Adet", color_continuous_scale="Blues")
            fig3.update_layout(showlegend=False, height=350, yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig3, use_container_width=True)

        with c4:
            st.subheader("Duygu Durumu Dağılımı")
            em = df["EMOTION"].value_counts().reset_index()
            em.columns = ["Duygu", "Adet"]
            colors = {
                "Mutlu": "#2ecc71", "Minnettar": "#27ae60", "Umutlu": "#3498db",
                "Mutsuz": "#e67e22", "Kızgın": "#e74c3c", "Endişeli": "#9b59b6",
                "Veri Yetersiz": "#95a5a6",
            }
            fig4 = px.bar(em, x="Duygu", y="Adet",
                          color="Duygu",
                          color_discrete_map=colors)
            fig4.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig4, use_container_width=True)

        st.divider()
        st.subheader("Haftalık NPS Trendi")
        trend = get_summary_table("haftalik_trend")
        fig5 = px.line(trend, x="hafta", y="ort_nps",
                       labels={"hafta": "Hafta", "ort_nps": "Ortalama NPS"},
                       markers=True)
        fig5.update_layout(height=300)
        st.plotly_chart(fig5, use_container_width=True)

    except Exception as e:
        st.error(f"Dashboard yüklenemedi: {e}")
