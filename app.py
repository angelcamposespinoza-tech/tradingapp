import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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

# Función para detectar Soportes y Resistencias (Puntos de giro)
def detectar_niveles(df, window=10):
    niveles = []
    for i in range(window, len(df) - window):
        # Detectar Techo (Resistencia)
        if df['High'].iloc[i] == df['High'].iloc[i-window:i+window].max():
            niveles.append(df['High'].iloc[i])
        # Detectar Piso (Soporte)
        if df['Low'].iloc[i] == df['Low'].iloc[i-window:i+window].min():
            niveles.append(df['Low'].iloc[i])
    return sorted(list(set(niveles)))

# --- BARRA LATERAL ---
st.sidebar.header("💰 Gestión de Capital")
capital_total = st.sidebar.number_input("Dinero en Portafolio ($)", value=1000.0, step=100.0)
dinero_en_riesgo = capital_total * 0.02
meta_ganancia = capital_total * 0.04

st.sidebar.header("📋 Configuración")
dias_vencimiento = st.sidebar.selectbox("Vencimiento", ("Hoy (0DTE)", "1 a 3 días", "1 semana", "1 mes o más"), index=0)
tiempos = {"Hoy (0DTE)": ("1m", "1d"), "1 a 3 días": ("5m", "5d"), "1 semana": ("30m", "1mo"), "1 mes o más": ("1d", "1y")}
v_intervalo, v_periodo = tiempos[dias_vencimiento]

nuevos_tickers = st.sidebar.text_input("Agregar Tickers (ej: COIN, MSTR)", value="").upper()
EMPRESAS_BASE = ["AAPL", "TSLA", "NVDA", "META", "AMZN", "MSFT", "GOOGL", "NFLX", "AMD", "BTC-USD"]
EMPRESAS_TOP = EMPRESAS_BASE + ([t.strip() for t in nuevos_tickers.split(",") if t.strip()] if nuevos_tickers else [])

st.title("🚀 Smart Scanner: Estrategia Pro (Trend + Support)")

# 2. MONITOR DE SEÑALES
@st.cache_data(ttl=60)
def escanear_mercado(lista, inter, peri):
    resultados = []
    for t in lista:
        try:
            df = yf.download(t, period=peri, interval=inter, progress=False)
            if not df.empty:
                if df.columns.nlevels > 1: df.columns = df.columns.get_level_values(0)
                rsi = calcular_rsi(df['Close']).iloc[-1]
                precio = df['Close'].iloc[-1]
                ema200 = calcular_ema(df['Close'], 200).iloc[-1]
                
                # Lógica avanzada: RSI + Tendencia EMA 200
                if rsi < 35 and precio > ema200: señal = "🔥 CALL (Fuerte)"
                elif rsi < 35: señal = "🌱 CALL (Rebote)"
                elif rsi > 65 and precio < ema200: señal = "⚠️ PUT (Fuerte)"
                elif rsi > 65: señal = "☁️ PUT (Técnico)"
                else: señal = "⚖️ Neutral"
                
                resultados.append({"T": t, "P": float(precio), "R": float(rsi), "S": señal})
        except: continue
    return resultados

datos_resumen = escanear_mercado(EMPRESAS_TOP, v_intervalo, v_periodo)
cols = st.columns(5)
for i, res in enumerate(datos_resumen):
    with cols[i % 5]:
        st.metric(res['T'], f"${res['P']:,.2f}", f"RSI: {res['R']:.1f}")
        st.caption(res['S'])

st.markdown("---")

# 3. ANÁLISIS DETALLADO
st.sidebar.header("🔍 Gráfico Detallado")
ticker_ind = st.sidebar.text_input("Ticker para Graficar", value="META").upper()
data = yf.download(ticker_ind, period=v_periodo, interval=v_intervalo, progress=False)

if not data.empty and len(data) > 15:
    if data.columns.nlevels > 1: data.columns = data.columns.get_level_values(0)
    precio_actual = data['Close'].iloc[-1]
    ema200_actual = calcular_ema(data['Close'], 200).iloc[-1]
    rsi_val = calcular_rsi(data['Close']).iloc[-1]
    
    # Cálculos TP/SL (Basado en 2%/4% portafolio)
    mov_sl = dinero_en_riesgo / 100
    mov_tp = meta_ganancia / 100
    if rsi_val < 50:
        sl, tp, tipo = precio_actual - mov_sl, precio_actual + mov_tp, "CALL"
    else:
        sl, tp, tipo = precio_actual + mov_sl, precio_actual - mov_tp, "PUT"

    col_graf, col_info = st.columns([4, 1])
    
    with col_graf:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_width=[0.2, 0.7])
        fig.add_trace(go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Precio"), row=1, col=1)
        
        # EMA 200 (Morada - La Ley) y EMA 20 (Naranja)
        fig.add_trace(go.Scatter(x=data.index, y=calcular_ema(data['Close'], 200), name="EMA 200", line=dict(color='purple', width=3)), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=calcular_ema(data['Close'], 20), name="EMA 20", line=dict(color='orange', width=1)), row=1, col=1)
        
        # Soportes y Resistencias (Líneas grises sutiles)
        niveles = detectar_niveles(data)
        for nivel in niveles:
            if abs(nivel - precio_actual) / precio_actual < 0.05: # Solo mostrar niveles cerca del precio
                fig.add_hline(y=nivel, line_width=0.5, line_dash="dash", line_color="gray", opacity=0.3, row=1, col=1)

        # Volumen
        v_colors = ['green' if r['Open'] < r['Close'] else 'red' for _, r in data.iterrows()]
        fig.add_trace(go.Bar(x=data.index, y=data['Volume'], name="Volumen", marker_color=v_colors, opacity=0.4), row=2, col=1)
        
        fig.add_hline(y=tp, line_dash="dot", line_color="green", annotation_text="TAKE PROFIT", row=1, col=1)
        fig.add_hline(y=sl, line_dash="dot", line_color="red", annotation_text="STOP LOSS", row=1, col=1)
        
        fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=800)
        st.plotly_chart(fig, use_container_width=True)
    
    with col_info:
        st.subheader("🎯 Análisis")
        st.metric("RSI", f"{rsi_val:.1f}")
        
        # RECUADRO DE TENDENCIA
        if precio_actual > ema200_actual:
            st.success("📈 TENDENCIA ALCISTA")
            st.write("Favor de CALLs")
        else:
            st.error("📉 TENDENCIA BAJISTA")
            st.write("Favor de PUTs")
        
        st.write("---")
        st.write(f"Sugerencia: **{tipo}**")
        
        # Alerta de Proximidad a Soporte/Resistencia
        prox_nivel = min(niveles, key=lambda x: abs(x - precio_actual))
        dist_nivel = ((prox_nivel - precio_actual) / precio_actual) * 100
        st.write(f"📍 Nivel más cercano: **{dist_nivel:.1f}%**")

        st.write("---")
        st.error(f"SL: ${sl:.2f}")
        st.success(f"TP: ${tp:.2f}")
        st.info(f"Compra: **{int(dinero_en_riesgo/(abs(precio_actual-sl)))}** contratos")
else:
    st.error("Esperando datos...")
