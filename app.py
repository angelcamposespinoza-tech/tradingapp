import streamlit as st
import yfinance as yf
import pandas as pd

st.title("🧪 Diagnóstico de Conexión")

ticker = st.text_input("Introduce un Ticker para probar:", value="AAPL")

if st.button("Ejecutar Prueba"):
    try:
        st.write(f"Intentando descargar datos de {ticker}...")
        
        # Prueba 1: Descarga simple con timeout
        data = yf.download(ticker, period="1d", interval="1m", timeout=5)
        
        if not data.empty:
            st.success("✅ ¡CONEXIÓN EXITOSA!")
            st.write("Último precio detectado:")
            st.dataframe(data.tail())
        else:
            st.error("❌ Yahoo respondió, pero los DATOS ESTÁN VACÍOS.")
            st.info("Esto suele pasar si Yahoo bloqueó la IP del servidor o el Ticker está mal escrito.")
            
    except Exception as e:
        st.error(f"🚨 FALLO TOTAL DE CONEXIÓN: {e}")
        st.write("El problema es la librería yfinance o la red del servidor.")
