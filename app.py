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

# --- BARRA LATERAL ---
st.sidebar.header("💰 Gestión de Capital")
capital_total = st.sidebar.number_input("Dinero en Portafolio ($)", value=1000.0, step=100.0)
dinero_en_riesgo = capital_total * 0.02
meta_ganancia = capital_total * 0.04

st.sidebar.info(f"Riesgo Máximo (2%): **${dinero_en_riesgo:.2f}**")
st.sidebar.success(f"Meta Ganancia (4%): **${meta_ganancia:.2f}**")

st.sidebar.header("📋 Configuración")
dias_vencimiento = st.sidebar.selectbox("Vencimiento", ("Hoy (0DTE)", "1 a 3 días", "1 semana", "1 mes o más"), index=0)

tiempos = {"Hoy (0DTE)": ("1m", "1d"), "1 a 3 días": ("5m", "5d"), "1 semana": ("30m", "1mo"), "1 mes o más": ("1d", "1y")}
v_intervalo, v_periodo = tiempos[dias_vencimiento]

nuevos_tickers = st.sidebar.text_input("Agregar Tickers (ej: COIN, MSTR)", value="").upper()
EMPRESAS_BASE = ["AAPL", "TSLA", "NVDA", "META", "AMZN", "MSFT", "GOOGL", "NFLX", "AMD", "BTC-USD"]
EMPRESAS_TOP = EMPRESAS_BASE + ([t.strip() for t in nuevos_tickers.split(",") if t.strip()] if nuevos_tickers else [])

st.title("🚀 Smart Scanner: Estrategia 2%/4% + Volumen")

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

# 3. ANÁLISIS DETALLADO, VOLUMEN Y ESTRATEGIA
st.sidebar.header("🔍 Gráfico Detallado")
ticker_ind = st.sidebar.text_input("Ticker para Graficar", value="META").upper()

data = yf.download(ticker_ind, period=v_periodo, interval=v_intervalo, progress=False)
if not data.empty and len(data) > 15:
    if data.columns.nlevels > 1: data.columns = data.columns.get_level_values(0)
    
    precio_actual = data['Close'].iloc[-1]
    rsi_val = calcular_rsi(data['Close']).iloc[-1]
    
    # Análisis de Volumen
    vol_promedio = data['Volume'].rolling(window=20).mean().iloc[-1]
    vol_actual = data['Volume'].iloc[-1]
    fuerza_volumen = vol_actual / vol_promedio

    mov_accion_sl = dinero_en_riesgo / 100
    mov_accion_tp = meta_ganancia / 100
    
    if rsi_val < 50:
        sl, tp, tipo = precio_actual - mov_accion_sl, precio_actual + mov_accion_tp, "CALL"
    else:
        sl, tp, tipo = precio_actual + mov_accion_sl, precio_actual - mov_accion_tp, "PUT"

    col_graf, col_info = st.columns([4, 1])
    
    with col_graf:
        # Gráfico con Subplots para incluir Volumen
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_width=[0.2, 0.7])
        
        # Velas
        fig.add_trace(go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Precio"), row=1, col=1)
        
        # Volumen
        colors = ['green' if row['Open'] < row['Close'] else 'red' for _, row in data.iterrows()]
        fig.add_trace(go.Bar(x=data.index, y=data['Volume'], name="Volumen", marker_color=colors, opacity=0.5), row=2, col=1)
        
        # Medias Móviles
        fig.add_trace(go.Scatter(x=data.index, y=calcular_ema(data['Close'], 20), name="EMA 20", line=dict(color='orange', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=calcular_ema(data['Close'], 200), name="EMA 200", line=dict(color='purple', width=2)), row=1, col=1)
        
        # Líneas TP/SL
        fig.add_hline(y=tp, line_dash="dot", line_color="green", annotation_text="GANANCIA", row=1, col=1)
        fig.add_hline(y=sl, line_dash="dot", line_color="red", annotation_text="STOP LOSS", row=1, col=1)
        
        fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=750, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)
    
    with col_info:
        st.subheader("🎯 Plan")
        st.metric("RSI", f"{rsi_val:.2f}")
        st.write(f"Sugerencia: **{tipo}**")
        
        # RECUADRO DE VOLUMEN
        st.write("---")
        st.subheader("📊 Volumen")
        if fuerza_volumen > 1.5:
            st.success(f"FUERZA ALTA ({fuerza_volumen:.1f}x)")
            st.write("✅ Los bancos están operando. Movimiento confirmado.")
        elif fuerza_volumen > 0.8:
            st.info(f"FUERZA NORMAL ({fuerza_volumen:.1f}x)")
            st.write("⚖️ Volumen sano. Sigue el plan.")
        else:
            st.warning(f"SIN FUERZA ({fuerza_volumen:.1f}x)")
            st.write("⚠️ Poco interés. Cuidado con señales falsas.")
            
        st.write("---")
        st.error(f"SL: ${sl:.2f}")
        st.success(f"TP: ${tp:.2f}")
        st.info(f"Compra: **{int(dinero_en_riesgo/(abs(precio_actual-sl)))}** unidades")

else:
    st.error("No hay datos suficientes.")
