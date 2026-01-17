import streamlit as st
import requests

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="AI RAG Eval Platform", layout="centered")
st.title("AI RAG Eval Platform")
st.caption("Thin-slice UI: sends a question to FastAPI /query and displays the response.")

question = st.text_input("Ask a question", placeholder="e.g., What is our refund policy?")

col1, col2 = st.columns([1, 1])
with col1:
    ask = st.button("Ask")
with col2:
    st.write("")

if ask:
    if not question.strip():
        st.warning("Type a question first.")
    else:
        try:
            r = requests.post(f"{API_BASE}/query", json={"question": question}, timeout=30)
            r.raise_for_status()
            data = r.json()
            st.subheader("Answer")
            st.write(data.get("answer", ""))

            st.subheader("Citations")
            st.write(data.get("citations", []))

            st.subheader("Raw response")
            st.json(data)
        except Exception as e:
            st.error(f"Request failed: {e}")
