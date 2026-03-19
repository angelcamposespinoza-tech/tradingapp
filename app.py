import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

# 1. Configuración de la página
st.set_page_config(page_title="Scanner Pro - Ángel", layout="wide", page_icon="📈")

# ESTILOS
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    [data-testid="stMetricValue"] { color: #ffffff !important; font-size: 28px !important; font-weight: bold; }
    [data-testid="stMetricLabel"] { color: #ffffff !important; font-size: 16px !important; opacity: 1; }
    div[data-testid="stMetric"] {
        background-color: #161b22; border: 1px solid #30363d;
        padding: 15px; border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# FUNCIONES MANUALES
def calcular_rsi(series, periods=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calcular_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

# --- BARRA LATERAL ---
st.sidebar.header("📋 Configuración de Opciones")

# Nueva función: Tiempo al vencimiento
dias_vencimiento = st.sidebar.selectbox(
    "¿Cuándo vence tu opción?",
    ("Hoy (0DTE)", "1 a 3 días", "1 semana", "1 mes o más"),
    index=0
)

# Lógica automática de temporalidad según el vencimiento
if dias_vencimiento == "Hoy (0DTE)":
    v_intervalo, v_periodo = "1m", "1d"
    zoom_msg = "Análisis Ultra Rápido (Scalping)"
elif dias_vencimiento == "1 a 3 días":
    v_intervalo, v_periodo = "5m", "5d"
    zoom_msg = "Análisis de Corto Plazo"
elif dias_vencimiento == "1 semana":
    v_intervalo, v_periodo = "30m", "1mo"
    zoom_msg = "Análisis Semanal (Swing)"
else:
    v_intervalo, v_periodo = "1d", "1y"
    zoom_msg = "Análisis de Tendencia Maestra"

st.sidebar.info(f"Foco: {zoom_msg}")

# Tickers adicionales
nuevos_tickers = st.sidebar.text_input("Agregar Tickers (separados por coma)", value="").upper()
EMPRESAS_BASE = ["AAPL", "TSLA", "NVDA", "META", "AMZN", "MSFT", "GOOGL", "NFLX", "AMD", "BTC-USD"]
EMPRESAS_TOP = EMPRESAS_BASE + ([t.strip() for t in nuevos_tickers.split(",") if t.strip()] if nuevos_tickers else [])

st.title("🚀 Smart Scanner: Modo Opciones")

# 2. MONITOR DE SEÑALES (AJUSTADO POR VENCIMIENTO)
@st.cache_data(ttl=60) # Actualización rápida para 0DTE
def escanear_mercado(lista, inter, peri):
    resultados = []
    for t in lista:
        try:
            df = yf.download(t, period=peri, interval=inter, progress=False)
            if not df.empty:
                if df.columns.nlevels > 1: df.columns = df.columns.get_level_values(0)
                rsi_s = calcular_rsi(df['Close'])
                if not rsi_s.empty:
                    rsi = rsi_s.iloc[-1]
                    precio = df['Close'].iloc[-1]
                    señal = "🔥 CALL" if rsi < 30 else "⚠️ PUT" if rsi > 70 else "⚖️ Neutral"
                    resultados.append({"T": t, "P": float(precio), "R": float(rsi), "S": señal})
        except: continue
    return resultados

datos_resumen = escanear_mercado(EMPRESAS_TOP, v_intervalo, v_periodo)
cols = st.columns(5)
for i, res in enumerate(datos_resumen):
    with cols[i % 5]:
        st.metric(res['T'], f"${res['P']:,.2f}", f"RSI ({v_intervalo}): {res['R']:.1f}")
        if "CALL" in res['S']: st.success(res['S'])
        elif "PUT" in res['S']: st.error(res['S'])
        else: st.info(res['S'])

st.markdown("---")

# 3. ANÁLISIS DETALLADO
st.sidebar.header("🔍 Gráfico Manual")
ticker_ind = st.sidebar.text_input("Ticker para Graficar", value="META").upper()

data = yf.download(ticker_ind, period=v_periodo, interval=v_intervalo, progress=False)
if not data.empty and data.columns.nlevels > 1: data.columns = data.columns.get_level_values(0)

if not data.empty and len(data) > 15:
    data['RSI'] = calcular_rsi(data['Close'])
    data['EMA_20'] = calcular_ema(data['Close'], 20)
    data['EMA_200'] = calcular_ema(data['Close'], 200)
    
    # Gráfica
    col_graf, col_info = st.columns([4, 1])
    with col_graf:
        st.subheader(f"Vista {v_intervalo} - {ticker_ind} ({zoom_msg})")
        fig = go.Figure(data=[go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Precio")])
        fig.add_trace(go.Scatter(x=data.index, y=data['EMA_20'], name="EMA 20", line=dict(color='orange')))
        fig.add_trace(go.Scatter(x=data.index, y=data['EMA_200'], name="EMA 200", line=dict(color='purple', width=2)))
        fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=600)
        st.plotly_chart(fig, use_container_width=True)
    
    with col_info:
        st.subheader("🎯 Señal")
        v = data['RSI'].iloc[-1]
        st.metric("RSI Actual", f"{v:.2f}")
        if v < 30: st.success("🎯 CALL")
        elif v > 70: st.error("🎯 PUT")
        else: st.info("⚖️ Neutral")
else:
    st.error("⚠️ Sin datos suficientes.")
