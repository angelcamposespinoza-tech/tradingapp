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
st.sidebar.header("💰 Gestión de Capital")
capital_total = st.sidebar.number_input("Dinero en Portafolio ($)", value=1000.0, step=100.0)
# Esta es la barra que ahora sí controla la distancia de las líneas en la gráfica:
pct_riesgo_val = st.sidebar.slider("% Máximo a perder por trade", 0.5, 10.0, 2.0)
pct_riesgo = pct_riesgo_val / 100
dinero_en_riesgo = capital_total * pct_riesgo

st.sidebar.header("📋 Configuración de Opciones")
dias_vencimiento = st.sidebar.selectbox(
    "¿Cuándo vence tu opción?",
    ("Hoy (0DTE)", "1 a 3 días", "1 semana", "1 mes o más"),
    index=0
)

# Lógica automática de temporalidad
tiempos = {
    "Hoy (0DTE)": ("1m", "1d"),
    "1 a 3 días": ("5m", "5d"),
    "1 semana": ("30m", "1mo"),
    "1 mes o más": ("1d", "1y")
}
v_intervalo, v_periodo = tiempos[dias_vencimiento]

# Tickers adicionales
nuevos_tickers = st.sidebar.text_input("Agregar Tickers (ej: COIN, MSTR)", value="").upper()
EMPRESAS_BASE = ["AAPL", "TSLA", "NVDA", "META", "AMZN", "MSFT", "GOOGL", "NFLX", "AMD", "BTC-USD"]
EMPRESAS_TOP = EMPRESAS_BASE + ([t.strip() for t in nuevos_tickers.split(",") if t.strip()] if nuevos_tickers else [])

st.title("🚀 Smart Scanner: Gestión y Tendencia")

# 2. MONITOR DE SEÑALES (ARRIBA)
@st.cache_data(ttl=60)
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
        st.metric(res['T'], f"${res['P']:,.2f}", f"RSI: {res['R']:.1f}")
        if "CALL" in res['S']: st.success(res['S'])
        elif "PUT" in res['S']: st.error(res['S'])
        else: st.info(res['S'])

st.markdown("---")

# 3. ANÁLISIS DETALLADO Y CALCULADORA DE RIESGO
st.sidebar.header("🔍 Gráfico Detallado")
ticker_ind = st.sidebar.text_input("Ticker para Graficar", value="META").upper()

data = yf.download(ticker_ind, period=v_periodo, interval=v_intervalo, progress=False)
if not data.empty and len(data) > 15:
    if data.columns.nlevels > 1: data.columns = data.columns.get_level_values(0)
    
    precio_actual = data['Close'].iloc[-1]
    data['RSI'] = calcular_rsi(data['Close'])
    rsi_val = data['RSI'].iloc[-1]
    data['EMA_20'] = calcular_ema(data['Close'], 20)
    data['EMA_200'] = calcular_ema(data['Close'], 200)

    # NUEVA LÓGICA DE RIESGO: El Stop Loss se calcula basado en el % que elegiste
    # Distancia en dinero basada en el % de riesgo sobre el precio actual
    distancia_sl = precio_actual * pct_riesgo
    
    # Determinar si sugerimos CALL o PUT para dibujar las líneas
    if rsi_val < 50: # Sesgo Alcista (CALL)
        sl = precio_actual - distancia_sl
        tp = precio_actual + (distancia_sl * 2) # Ratio 2:1
        tipo = "CALL"
    else: # Sesgo Bajista (PUT)
        sl = precio_actual + distancia_sl
        tp = precio_actual - (distancia_sl * 2) # Ratio 2:1
        tipo = "PUT"

    col_graf, col_info = st.columns([4, 1])
    
    with col_graf:
        st.subheader(f"Gráfico: {ticker_ind} ({v_intervalo})")
        fig = go.Figure(data=[go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Precio")])
        fig.add_trace(go.Scatter(x=data.index, y=data['EMA_20'], name="EMA 20", line=dict(color='orange')))
        fig.add_trace(go.Scatter(x=data.index, y=data['EMA_200'], name="EMA 200", line=dict(color='purple', width=2)))
        
        # Líneas de Riesgo dinámicas
        fig.add_hline(y=tp, line_dash="dot", line_color="green", annotation_text="GANANCIA (TP)")
        fig.add_hline(y=sl, line_dash="dot", line_color="red", annotation_text="PÉRDIDA (SL)")
        
        fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=650)
        st.plotly_chart(fig, use_container_width=True)
    
    with col_info:
        st.subheader("🎯 Plan")
        st.metric("RSI", f"{rsi_val:.2f}")
        st.write(f"**Sugerencia:** {tipo}")
        st.write("---")
        st.write(f"Riesgo x Trade: **${dinero_en_riesgo:.2f}**")
        st.error(f"SL: ${sl:.2f}")
        st.success(f"TP: ${tp:.2f}")
        
        # Cálculo de cantidad de acciones
        distancia_puntos = abs(precio_actual - sl)
        cantidad = int(dinero_en_riesgo / distancia_puntos) if distancia_puntos > 0 else 0
        st.info(f"Compra: **{cantidad}** unidades")

else:
    st.error("No hay datos suficientes para graficar.")
