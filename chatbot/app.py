"""Chạy: .venv\\Scripts\\streamlit.exe run app.py"""
import pandas as pd
import streamlit as st

from src.answer import MAX_DETAILED
from src.bot import SCOPE_NOTE, answer
from src.config import OLLAMA_MODEL

st.set_page_config(page_title="Hỏi đáp giờ lễ", page_icon="⛪")
st.title("⛪ Hỏi đáp nhà thờ & giờ lễ")
st.caption(SCOPE_NOTE + " Câu trả lời chỉ dựa trên dữ liệu này.")

with st.sidebar:
    model = st.text_input("Model Ollama", OLLAMA_MODEL)
    use_intro = st.toggle("LLM viết câu mở đầu", value=False,
                          help="Chậm hơn khoảng 6 giây/câu và văn phong không ổn định. Giờ lễ luôn lấy từ dữ liệu.")
    show_debug = st.toggle("Hiện bộ lọc đã trích", value=False)
    if st.button("Xóa hội thoại"):
        st.session_state.messages = []
        st.session_state.context = None
    st.markdown("**Ví dụ:**\n- Giờ lễ nhà thờ Tân Định?\n- nha tho nao o go vap co le sang chua nhat\n"
                "- Nhà thờ trên đường Lê Văn Sỹ\n- Lễ tối thứ 7 ở quận 10\n\n"
                "**Hỏi nối tiếp:** “còn buổi tối thì sao?”, “nhà thờ đó ở đâu?”, "
                "“trong đó nhà thờ nào có lễ sau 19h?”")

st.session_state.setdefault("messages", [])
st.session_state.setdefault("context", None)  # bộ lọc + kết quả câu trước, cho câu hỏi nối tiếp


def render(msg: dict) -> None:
    st.markdown(msg["content"])
    if msg.get("table") and len(msg["table"]) > MAX_DETAILED:
        st.dataframe(pd.DataFrame(msg["table"]), hide_index=True, width="stretch",
                     column_config={"Nguồn": st.column_config.LinkColumn("Nguồn")})
    if show_debug and msg.get("debug"):
        with st.expander("Bộ lọc"):
            st.json(msg["debug"])


for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        render(m)

if question := st.chat_input("Hỏi về nhà thờ, giờ lễ..."):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Đang tra cứu..."):
            try:
                r = answer(question, use_llm_intro=use_intro, model=model, context=st.session_state.context)
                st.session_state.context = r.context
                msg ={"role": "assistant", "content": r.text, "table": r.table, "debug": r.debug}
            except Exception as e:  # Ollama tắt, chưa build DB...
                msg = {"role": "assistant", "content": f"Lỗi: {e}"}
        render(msg)
    st.session_state.messages.append(msg)
