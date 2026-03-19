import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

# 1. Configuración de la página
st.set_page_config(page_title="Scanner Pro - Ángel", layout="wide", page_icon="📈")

# ESTILOS: Recuadros negros con texto blanco puro
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    [data-testid="stMetricValue"] { color: #ffffff !important; font-size: 28px !important; font-weight: bold; }
    [data-testid="stMetricLabel"] { color: #ffffff !important; font-size: 16px !important; opacity: 1; }
    div[data-testid="stMetric"] {
        background-color: #161b22; 
        border: 1px solid #30363d;
        padding: 15px; 
        border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# FUNCIONES MANUALES (Para evitar el error de pandas_ta)
def calcular_rsi(series, periods=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calcular_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

# LISTA DE MONITOREO TOP 10
EMPRESAS_TOP = ["AAPL", "TSLA", "NVDA", "META", "AMZN", "MSFT", "GOOGL", "NFLX", "AMD", "BTC-USD"]

st.title("🚀 Smart Scanner: Enfoque en Tendencia")

# 2. MONITOR DE SEÑALES (TOP 10)
@st.cache_data(ttl=300)
def escanear_mercado(lista):
    resultados = []
    for t in lista:
        df = yf.download(t, period="1y", interval="1d", progress=False)
        if not df.empty:
            if df.columns.nlevels > 1: df.columns = df.columns.get_level_values(0)
            rsi_s = calcular_rsi(df['Close'])
            if not rsi_s.empty:
                rsi = rsi_s.iloc[-1]
                precio = df['Close'].iloc[-1]
                señal = "🔥 CALL" if rsi < 35 else "⚠️ PUT" if rsi > 65 else "⚖️ Neutral"
                resultados.append({"T": t, "P": float(precio), "R": float(rsi), "S": señal})
    return resultados

datos_resumen = escanear_mercado(EMPRESAS_TOP)
cols = st.columns(5)
for i, res in enumerate(datos_resumen):
    with cols[i % 5]:
        st.metric(res['T'], f"${res['P']:,.2f}", f"RSI: {res['R']:.1f}")
        if "CALL" in res['S']: st.success(res['S'])
        elif "PUT" in res['S']: st.error(res['S'])
        else: st.info(res['S'])

st.markdown("---")

# 3. ANÁLISIS DETALLADO
st.sidebar.header("🔍 Configuración")
ticker_ind = st.sidebar.text_input("Ticker", value="META").upper()
intervalo = st.sidebar.selectbox("Vela", ("1m", "5m", "15m", "1h", "1d", "1wk"), index=4)
periodo = st.sidebar.selectbox("Rango", ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "max"), index=5)

data = yf.download(ticker_ind, period=periodo, interval=intervalo, progress=False)
if not data.empty and data.columns.nlevels > 1: data.columns = data.columns.get_level_values(0)

if not data.empty and len(data) > 15:
    # Indicadores calculados manualmente
    data['RSI'] = calcular_rsi(data['Close'])
    data['EMA_20'] = calcular_ema(data['Close'], 20)
    data['EMA_50'] = calcular_ema(data['Close'], 50)
    data['EMA_200'] = calcular_ema(data['Close'], 200)
    
    # Lógica de Martillos
    body = abs(data['Close'] - data['Open'])
    uw = data['High'] - data[['Close', 'Open']].max(axis=1)
    lw = data[['Close', 'Open']].min(axis=1) - data['Low']
    es_v = data['Close'] > data['Open']
    es_r = data['Close'] < data['Open']
    
    data['Hammer'] = (lw > (body * 2)) & (uw < (body * 0.5)) & (es_v)
    data['Inv_Hammer'] = (uw > (body * 2)) & (lw < (body * 0.5)) & (es_r)

    col_graf, col_info = st.columns([4, 1])
    
    with col_graf:
        st.subheader(f"Gráfico de Tendencia: {ticker_ind}")
        fig = go.Figure(data=[go.Candlestick(
            x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Precio"
        )])
        
        fig.add_trace(go.Scatter(x=data.index, y=data['EMA_20'], name="EMA 20", line=dict(color='orange', width=1.5)))
        fig.add_trace(go.Scatter(x=data.index, y=data['EMA_50'], name="EMA 50", line=dict(color='cyan', width=1.5)))
        fig.add_trace(go.Scatter(x=data.index, y=data['EMA_200'], name="EMA 200", line=dict(color='#9370DB', width=3)))

        h = data[data['Hammer'] == True]
        fig.add_trace(go.Scatter(x=h.index, y=h['Low']*0.99, mode='markers', 
                                 marker=dict(symbol='triangle-up', size=15, color='#00ff00'), name="Martillo Verde"))
        ih = data[data['Inv_Hammer'] == True]
        fig.add_trace(go.Scatter(x=ih.index, y=ih['High']*1.01, mode='markers', 
                                 marker=dict(symbol='triangle-down', size=15, color='#ff4b4b'), name="Martillo Rojo"))

        fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=800, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
    
    with col_info:
        st.subheader("🎯 Señal")
        r_val = data['RSI'].dropna()
        if not r_val.empty:
            v = r_val.iloc[-1]
            st.metric("RSI Actual", f"{v:.2f}")
            if v < 35: st.success("🎯 Sugerencia: CALL")
            elif v > 65: st.error("🎯 Sugerencia: PUT")
            else: st.info("⚖️ Neutral")
        
        st.write("---")
        st.write("**Guía Rápida:**")
        st.write("🟠 **20:** Corto plazo.")
        st.write("🔵 **50:** Mediano plazo.")
        st.write("🟣 **200:** Tendencia Maestra.")
else:
    st.error("⚠️ Datos insuficientes para este rango.")
