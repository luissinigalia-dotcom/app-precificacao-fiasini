import streamlit as st

st.title("Olá, Fiasini! 👋")
st.write("Se você está vendo esta tela, o deploy funcionou. 🚀")

st.subheader("Teste rápido de interação")
nome = st.text_input("Seu nome", "")
if nome:
    st.success(f"Bem-vindo(a), {nome}!")
