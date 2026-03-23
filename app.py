import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import google.generativeai as genai

# --- CONFIGURACIÓN DE IA (CON BÚSQUEDA EN INTERNET) ---
genai.configure(api_key="AIzaSyBK1aeiT7nlyP6GW7gUX_GoZv45dzlhN7g")

@st.cache_resource
def configurar_ia():
    try:
        modelos = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        seleccionado = next((m for m in modelos if "flash" in m.lower()), modelos[0])
        
  # ACTIVAMOS LA HERRAMIENTA DE BÚSQUEDA DE GOOGLE (FORMATO CORRECTO)
        return genai.GenerativeModel(
            model_name=seleccionado,
            tools=[{"google_search_retrieval": {}}] 
        )
    except Exception as e:
        st.error(f"Error de conexión con IA: {e}")
        return None

model = configurar_ia()

# 1. Configuración de la página
st.set_page_config(page_title="Scanner Superior - Ángel", layout="wide", page_icon="📈")

# ESTILOS: Ajuste de colores para máxima legibilidad
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    [data-testid="stMetricValue"] { color: #ffffff !important; font-size: 28px !important; font-weight: bold; }
    [data-testid="stMetricLabel"] { color: #ffffff !important; font-size: 16px !important; opacity: 1; }
    div[data-testid="stMetric"] {
        background-color: #161b22; border: 1px solid #30363d;
        padding: 15px; border-radius: 10px;
    }
    .stAlert p { color: #000000 !important; font-weight: bold !important; }
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

def detectar_niveles(df, window=10):
    niveles = []
    for i in range(window, len(df) - window):
        if df['High'].iloc[i] == df['High'].iloc[i-window:i+window].max():
            niveles.append(df['High'].iloc[i])
        if df['Low'].iloc[i] == df['Low'].iloc[i-window:i+window].min():
            niveles.append(df['Low'].iloc[i])
    return sorted(list(set(niveles)))

def obtener_etiqueta_pro(rsi, precio, ema200):
    if rsi < 35 and precio > ema200: return "🔥 CALL (Fuerte)"
    elif rsi < 35: return "🌱 CALL (Rebote)"
    elif rsi > 65 and precio < ema200: return "⚠️ PUT (Fuerte)"
    elif rsi > 65: return "☁️ PUT (Técnico)"
    else: return "⚖️ Neutral"

# --- BARRA LATERAL ---
st.sidebar.header("💰 Gestión de Capital")
capital_total = st.sidebar.number_input("Dinero en Portafolio ($)", value=1000.0, step=100.0)
dinero_en_riesgo = capital_total * 0.02
meta_ganancia = capital_total * 0.04

st.sidebar.header("📋 Configuración")
dias_vencimiento = st.sidebar.selectbox("Vencimiento", ("Hoy (0DTE)", "1 a 3 días", "1 semana", "1 mes o más"), index=0)
tiempos = {"Hoy (0DTE)": ("1m", "1d"), "1 a 3 días": ("5m", "5d"), "1 semana": ("30m", "1mo"), "1 mes o más": ("1d", "1y")}
v_intervalo, v_periodo = tiempos[dias_vencimiento]

nuevos_tickers = st.sidebar.text_input("Agregar Tickers", value="").upper()
EMPRESAS_BASE = ["AAPL", "TSLA", "NVDA", "META", "AMZN", "MSFT", "GOOGL", "NFLX", "AMD", "SPY"]
EMPRESAS_TOP = EMPRESAS_BASE + ([t.strip() for t in nuevos_tickers.split(",") if t.strip()] if nuevos_tickers else [])

st.title("🚀 SUPERIOR SCANNER")

# 2. MONITOR DE SEÑALES (ARRIBA)
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
                señal = obtener_etiqueta_pro(rsi, precio, ema200)
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

# 3. ANÁLISIS DETALLADO
st.sidebar.header("🔍 Gráfico Detallado")
ticker_ind = st.sidebar.text_input("Ticker para Graficar", value="META").upper()
data = yf.download(ticker_ind, period=v_periodo, interval=v_intervalo, progress=False)

if not data.empty and len(data) > 15:
    if data.columns.nlevels > 1: data.columns = data.columns.get_level_values(0)
    precio_actual = data['Close'].iloc[-1]
    ema200_actual = calcular_ema(data['Close'], 200).iloc[-1]
    rsi_val = calcular_rsi(data['Close']).iloc[-1]
    etiqueta_ind = obtener_etiqueta_pro(rsi_val, precio_actual, ema200_actual)
    
    mov_sl = dinero_en_riesgo / 100
    mov_tp = meta_ganancia / 100
    if rsi_val < 50:
        sl, tp = precio_actual - mov_sl, precio_actual + mov_tp
    else:
        sl, tp = precio_actual + mov_sl, precio_actual - mov_tp

    # --- FILA 1: GRÁFICO Y MINI PANEL ---
    col_graf, col_info = st.columns([4, 1])
    with col_graf:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_width=[0.2, 0.7])
        fig.add_trace(go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Precio"), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=calcular_ema(data['Close'], 200), name="EMA 200", line=dict(color='purple', width=3)), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=calcular_ema(data['Close'], 20), name="EMA 20", line=dict(color='orange', width=1)), row=1, col=1)
        
        niveles = detectar_niveles(data)
        prox_nivel = min(niveles, key=lambda x: abs(x - precio_actual))
        for n in niveles:
            if abs(n - precio_actual) / precio_actual < 0.05:
                fig.add_hline(y=n, line_width=0.5, line_dash="dash", line_color="gray", opacity=0.3, row=1, col=1)

        v_colors = ['green' if r['Open'] < r['Close'] else 'red' for _, r in data.iterrows()]
        fig.add_trace(go.Bar(x=data.index, y=data['Volume'], name="Volumen", marker_color=v_colors, opacity=0.4), row=2, col=1)
        fig.add_hline(y=tp, line_dash="dot", line_color="green", annotation_text="TP", row=1, col=1)
        fig.add_hline(y=sl, line_dash="dot", line_color="red", annotation_text="SL", row=1, col=1)
        fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=600)
        st.plotly_chart(fig, use_container_width=True)

    with col_info:
        st.subheader("🎯 Señal")
        st.write(f"Estado: **{etiqueta_ind}**")
        st.metric("RSI", f"{rsi_val:.1f}")
        if precio_actual > ema200_actual:
            st.success("📈 ALCISTA")
        else:
            st.error("📉 BAJISTA")
        st.write("---")
        st.error(f"SL: ${sl:.2f}")
        st.success(f"TP: ${tp:.2f}")

    # --- FILA 2: NOTICIAS (ANCHO COMPLETO) ---
    st.markdown("---")
    st.subheader(f"📰 Central de Noticias: {ticker_ind}")
    c1, c2, c3 = st.columns(3)
    c1.link_button(f"🌐 Yahoo Finance", f"https://finance.yahoo.com/quote/{ticker_ind}/news", use_container_width=True)
    c2.link_button(f"🔍 Google Finance", f"https://www.google.com/finance/quote/{ticker_ind}", use_container_width=True)
    c3.link_button(f"🧠 Seeking Alpha", f"https://seekingalpha.com/symbol/{ticker_ind}", use_container_width=True)

    # --- FILA 3: COPILOTO IA (ANCHO COMPLETO ABAJO) ---
    st.markdown("---")
    with st.container():
        st.subheader("🤖 Pregúntame tus dudas")
        
        # Obtenemos noticias para la IA
        try:
            raw_news = yf.Ticker(ticker_ind).news
            resumen_noticias = "\n".join([n['title'] for n in raw_news[:3]]) if raw_news else "Sin noticias."
        except:
            resumen_noticias = "No se pudieron cargar noticias."

        duda = st.chat_input(f"Pregúntale a Gemini sobre {ticker_ind}...")
        
if duda:
            # El prompt ahora le ordena a Gemini buscar en internet
            contexto = f"""
            INVESTIGACIÓN EN TIEMPO REAL: Usa Google Search para encontrar noticias de las últimas 24h sobre {ticker_ind}.
            
            DATOS TÉCNICOS ACTUALES:
            - Precio: ${precio_actual:.2f} | RSI: {rsi_val:.1f}
            - Tendencia: {"ALCISTA" if precio_actual > ema200_actual else "BAJISTA"}
            - Soporte: ${prox_nivel:.2f}
            - Estrategia: Vencimiento a {dias_vencimiento}, riesgo 2% (${dinero_en_riesgo:.2f}), meta 4%.
            
            TAREA: Analiza si las noticias de internet apoyan o contradicen la señal técnica y responde: {duda}
            """
            
            with st.chat_message("assistant"):
                if model:
                    try:
                        # La IA navegará automáticamente para responder
                        response = model.generate_content(contexto)
                        st.write(response.text)
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.error("IA no configurada.")
else:
    st.error("Esperando datos...")
