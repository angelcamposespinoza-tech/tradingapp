import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import google.generativeai as genai


def guardar_en_sheets(ticker, precio, duda, direccion):
    # Ya no hace nada, así no pide secretos
    pass

def verificar_aciertos():
    # Retorna cero para no dar error en la barra lateral
    return 0, 0
      
# --- CONFIGURACIÓN DE IA (CON BÚSQUEDA EN INTERNET) ---
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])


@st.cache_resource
def configurar_ia():
    try:
        modelos = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        seleccionado = next((m for m in modelos if "flash" in m.lower()), modelos[0])
        
        # Intentamos activar la búsqueda, si falla por cuota, cargamos el modelo normal
        try:
            return genai.GenerativeModel(
                model_name=seleccionado,
                tools=[{"google_search": {}}] 
            )
        except:
            return genai.GenerativeModel(seleccionado)
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

def calcular_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(window=period).mean()

def evaluar_volatilidad(df):
    atr = calcular_atr(df).iloc[-1]
    precio = df['Close'].iloc[-1]
    # Si el movimiento es mayor al 1% del precio, es volatilidad alta
    if atr > (precio * 0.01):
        return "⚠️ Volatilidad ALTA", "error"
    return "✅ Volatilidad Normal", "success"

def obtener_etiqueta_pro(rsi, precio, ema200):
    if rsi < 35 and precio > ema200: return "🔥 CALL (Fuerte)"
    elif rsi < 35: return "🌱 CALL (Rebote)"
    elif rsi > 65 and precio < ema200: return "⚠️ PUT (Fuerte)"
    elif rsi > 65: return "☁️ PUT (Técnico)"
    else: return "⚖️ Neutral"
        
def analizar_volumen(df):
    """
    Aplica la regla del profesor ajustada a opciones:
    - Alto volumen + Alza = Confirmación CALL
    - Alto volumen + Baja = Confirmación PUT
    - Bajo volumen = Paciencia (Theta te puede comer)
    """
    vol_actual = df['Volume'].iloc[-1]
    vol_media = df['Volume'].rolling(window=20).mean().iloc[-1]
    precio_actual = df['Close'].iloc[-1]
    precio_anterior = df['Close'].iloc[-2]
    
    # El volumen es 'alto' si supera en 20% su media de las últimas 20 velas
    es_volumen_alto = vol_actual > (vol_media * 1.2)
    es_alza = precio_actual > precio_anterior
    
    if es_volumen_alto and es_alza:
        return "🚀 VOLUMEN FUERTE (CALL)", "success"
    elif es_volumen_alto and not es_alza:
        return "📉 VOLUMEN FUERTE (PUT)", "error"
    else:
        return "😴 Bajo Volumen (Espera)", "warning"

def generar_mini_conclusion(res):
    """
    Analiza de forma integral los indicadores calculados para ofrecer una recomendación
    con lenguaje profesional y directo.
    """
    # Escenario 1: Alta volatilidad - Riesgo elevado
    if "ALTA" in res['VOLATILIDAD']:
        if "CALL" in res['S'] or res['MA'] or res['MP']:
            return "⚠️ OPERACIÓN DE ALTO RIESGO: Patrón alcista con volatilidad extrema. Si entras, reduce la posición."
        if "PUT" in res['S']:
            return "⚠️ OPERACIÓN DE ALTO RIESGO: Fuerza bajista con volatilidad elevada. Ajusta bien el Stop Loss."
        return "⏳ ESPERA: Volatilidad muy alta sin dirección clara."

    # Escenario 2: Rupturas fuertes y confirmadas con volumen
    if res['RUPTURA'] == "🚀 TECHO ROTO" and "success" in res['VT']:
        return "🚀 COMPRA CONFIRMADA: Ruptura de techo con volumen fuerte. Movimiento alcista con alta probabilidad."
    if res['RUPTURA'] == "📉 PISO ROTO" and "error" in res['VT']:
        return "📉 VENTA CONFIRMADA: Ruptura de piso con volumen fuerte. Movimiento bajista con alta probabilidad."

    # Escenario 3: Patrones perfectos de velas (Martillos) en zonas clave
    if res['MP'] == "🔨 MARTILLO PERFECTO (CALL)" or (res['MA'] == "🔨 MARTILLO PERFECTO (CALL)" and "CALL" in res['S']):
        return "🎯 COMPRA TÉCNICA: Martillo perfecto detectado en zona de descuento. Buena relación riesgo/beneficio."
    if res['MP'] == "☄️ MARTILLO INV. PERFECTO (PUT)" or (res['MA'] == "☄️ MARTILLO INV. PERFECTO (PUT)" and "PUT" in res['S']):
        return "🎯 VENTA TÉCNICA: Martillo invertido en zona de resistencia. Alta probabilidad de retroceso."

    # Escenario 4: Señales fuertes por tendencia y RSI, pero volumen bajo
    if "Fuerte" in res['S'] and "Espera" in res['V']:
        return "⏳ PACIENCIA: Los indicadores técnicos son muy buenos, pero el volumen es bajo. Espera confirmación institucional."

    # Escenario 5: Alineación estándar alcista/bajista
    if "🔥 CALL" in res['S'] and "success" in res['VT']:
        return "📈 COMPRA ESTÁNDAR: Tendencia alcista alineada con volumen fuerte."
    if "⚠️ PUT" in res['S'] and "error" in res['VT']:
        return "📉 VENTA ESTÁNDAR: Tendencia bajista alineada con volumen de venta."

    # Escenario por defecto
    return "⚖️ OBSERVACIÓN: El mercado se encuentra en rango neutral. No hay una ventaja estadística clara."
    
def detectar_martillos(df):
    ultimo = df.iloc[-1]
    cuerpo = abs(ultimo['Open'] - ultimo['Close'])
    mecha_superior = ultimo['High'] - max(ultimo['Open'], ultimo['Close'])
    mecha_inferior = min(ultimo['Open'], ultimo['Close']) - ultimo['Low']
    
    if cuerpo == 0: cuerpo = 0.001 

    # --- MARTILLO CALL (Cierre en Máximos) ---
    # 1. Mecha inferior es al menos 2.5x el cuerpo.
    # 2. La mecha superior es casi inexistente (máximo un 10% del cuerpo).
    # 3. La vela DEBE ser verde.
    if (mecha_inferior > (cuerpo * 2.5) and 
        mecha_superior < (cuerpo * 0.1) and 
        ultimo['Close'] > ultimo['Open']):
        return "🔨 MARTILLO PERFECTO (CALL)"

    # --- MARTILLO PUT (Cierre en Mínimos) ---
    # 1. Mecha superior es al menos 2.5x el cuerpo.
    # 2. La mecha inferior es casi inexistente (máximo un 10% del cuerpo).
    # 3. La vela DEBE ser roja.
    if (mecha_superior > (cuerpo * 2.5) and 
        mecha_inferior < (cuerpo * 0.1) and 
        ultimo['Close'] < ultimo['Open']):
        return "☄️ MARTILLO INV. PERFECTO (PUT)"

    return None
    
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
# --- COPIAR DESDE AQUÍ ---
st.sidebar.markdown("---")
st.sidebar.header("📊 Auditoría de Estrategia")
if st.sidebar.button("Actualizar Historial y Aciertos"):
    with st.spinner("Calculando efectividad..."):
        aciertos, total = verificar_aciertos()
        if total > 0:
            porcentaje = (aciertos / total) * 100
            st.sidebar.metric("Efectividad IA", f"{porcentaje:.1f}%", f"{aciertos}/{total} Aciertos")
        else:
            st.sidebar.info("Aún no hay datos para auditar.")
# --- HASTA AQUÍ ---
st.title("🚀 SUPERIOR SCANNER")

# 2. MONITOR DE SEÑALES ORGANIZADO POR SECTORES

@st.cache_data(ttl=60)
def escanear_mercado(lista, inter, peri):
    resultados = []
    for t in lista:
        try:
            df = yf.download(t, period=peri, interval=inter, progress=False)
            if not df.empty and len(df) > 10:
                if df.columns.nlevels > 1: df.columns = df.columns.get_level_values(0)
                
                # 1. Datos base
                precio = float(df['Close'].iloc[-1])
                rsi = float(calcular_rsi(df['Close']).iloc[-1])
                ema200 = float(calcular_ema(df['Close'], 200).iloc[-1])
                
                # 2. Techos, pisos y rupturas del periodo
                mitad = len(df) // 2
                datos_pasados = df.iloc[:mitad]
                techo_ref = float(datos_pasados['High'].max())
                piso_ref = float(datos_pasados['Low'].min())
                
                ruptura = "⚖️ Dentro de Rango"
                if precio > techo_ref:
                    ruptura = "🚀 TECHO ROTO"
                elif precio < piso_ref:
                    ruptura = "📉 PISO ROTO"
                
                # 3. Solución a Incongruencias (Candado de estrategia)
                # Si rompe piso o es bajista fuerte, no permitimos CALL falso por RSI
                señal_base = obtener_etiqueta_pro(rsi, precio, ema200)
                if ruptura == "📉 PISO ROTO" and "CALL" in señal_base:
                    señal = "📉 PUT (Caída Libre / Ruptura)"
                elif ruptura == "🚀 TECHO ROTO" and "PUT" in señal_base:
                    señal = "🚀 CALL (Rally / Ruptura)"
                else:
                    señal = señal_base
                
                # 4. Volumen, Volatilidad y Tendencia
                vol_txt, vol_tipo = analizar_volumen(df)
                txt_volatilidad, _ = evaluar_volatilidad(df)
                tendencia = "📈 ALCISTA" if precio > ema200 else "📉 BAJISTA"
                
                # 5. Martillos
                m_actual = detectar_martillos(df.iloc[[-1]])
                m_pasada = detectar_martillos(df.iloc[[-2]])

                resultados.append({
                    "T": t, "P": precio, "R": rsi, "S": señal, 
                    "V": vol_txt, "VT": vol_tipo, "MA": m_actual, "MP": m_pasada,
                    "TECHO": techo_ref, "PISO": piso_ref, "RUPTURA": ruptura,
                    "VOLATILIDAD": txt_volatilidad, "TENDENCIA": tendencia
                })
        except: continue
    return resultados

st.subheader("📊 Monitor de Sectores")

# Definimos los grupos de empresas por sector
sectores = {
    "💻 Tecnología": ["AAPL", "NVDA", "MSFT", "GOOGL", "AMD"],
    "🏦 Financiero": ["JPM", "GS", "BAC", "V", "MA"],
    "📦 Consumo": ["WMT", "COST", "AMZN", "PG", "KO"],
    "⚡ Energía/Otros": ["XOM", "TSLA", "META", "NFLX", "SPY"]
}


tabs = st.tabs(list(sectores.keys()))

for i, (nombre_sector, lista_tickers) in enumerate(sectores.items()):
    with tabs[i]:
        datos_sector = escanear_mercado(lista_tickers, v_intervalo, v_periodo)
        cols = st.columns(5)
        for j, res in enumerate(datos_sector):
            with cols[j % 5]:
                # 1. Encabezado principal
                st.metric(res['T'], f"${res['P']:,.2f}", f"RSI: {res['R']:.1f}")
                
                # 2. Señal Inteligente Corregida
                if "CALL" in res['S']: 
                    st.success(res['S'])
                elif "PUT" in res['S']: 
                    st.error(res['S'])
                else: 
                    st.info(res['S'])
                
                # 3. Alertas Rápidas de Martillos
                if res.get('MP'): st.warning(f"✅ Conf: {res['MP']}")
                if res.get('MA'): st.info(f"⏳ Form: {res['MA']}")
                
                # 4. VIÑETA DESPLEGABLE CON COMPLEMENTOS Y CONCLUSIÓN
                with st.expander("🔍 Ver Datos Técnicos"):
                    # Generamos el veredicto en tiempo real con los datos guardados
                    conclusion_final = generar_mini_conclusion(res)
                    
                    st.markdown("**📋 Veredicto del Scanner:**")
                    st.info(conclusion_final)  # Destaca la conclusión en un recuadro limpio
                    st.write("---")
                    
                    st.markdown(f"**Ruptura:** {res['RUPTURA']}")
                    st.markdown(f"**Tendencia (EMA 200):** {res['TENDENCIA']}")
                    st.markdown(f"**Volatilidad:** {res['VOLATILIDAD']}")
                    st.markdown(f"**Volumen:** {res['V']}")
                    st.write("---")
                    st.caption(f"🏔️ Techo Ref: ${res['TECHO']:.2f}")
                    st.caption(f"📉 Piso Ref: ${res['PISO']:.2f}")
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
    
    # 1. DEFINICIÓN DE TECHOS Y PISOS (Calculamos antes de graficar)
    mitad = len(data) // 2
    datos_pasados = data.iloc[:mitad]
    techo_ref = datos_pasados['High'].max()
    piso_ref = datos_pasados['Low'].min()
    techo_periodo = data['High'].max() # Para el panel lateral
    piso_periodo = data['Low'].min()   # Para el panel lateral

    # 2. GESTIÓN DE RIESGO (Definimos SL y TP)
    mov_sl = dinero_en_riesgo / 100
    mov_tp = meta_ganancia / 100
    if rsi_val < 50:
        sl, tp = precio_actual - mov_sl, precio_actual + mov_tp
    else:
        sl, tp = precio_actual + mov_sl, precio_actual - mov_tp

    # 3. LÓGICA DE RUPTURA
    ruptura_texto = ""
    if precio_actual > techo_ref:
        ruptura_texto = "🚀 ¡TECHO ROTO! (Posible Rally)"
    elif precio_actual < piso_ref:
        ruptura_texto = "📉 ¡PISO ROTO! (Caída Libre)"

    # --- FILA 1: GRÁFICO Y MINI PANEL ---
    col_graf, col_info = st.columns([4, 1])
    with col_graf:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_width=[0.2, 0.7])
        fig.add_trace(go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Precio"), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=calcular_ema(data['Close'], 200), name="EMA 200", line=dict(color='purple', width=3)), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=calcular_ema(data['Close'], 20), name="EMA 20", line=dict(color='orange', width=1)), row=1, col=1)
        
        # Dibujamos SL y TP ahora que ya están definidos
        fig.add_hline(y=tp, line_dash="dot", line_color="green", annotation_text="TP", row=1, col=1)
        fig.add_hline(y=sl, line_dash="dot", line_color="red", annotation_text="SL", row=1, col=1)
        
        # Niveles detectados
        niveles = detectar_niveles(data)
        prox_nivel = min(niveles, key=lambda x: abs(x - precio_actual))
        for n in niveles:
            if abs(n - precio_actual) / precio_actual < 0.05:
                fig.add_hline(y=n, line_width=0.5, line_dash="dash", line_color="gray", opacity=0.3, row=1, col=1)

        v_colors = ['green' if r['Open'] < r['Close'] else 'red' for _, r in data.iterrows()]
        fig.add_trace(go.Bar(x=data.index, y=data['Volume'], name="Volumen", marker_color=v_colors, opacity=0.4), row=2, col=1)
        fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=600)
        st.plotly_chart(fig, use_container_width=True)

    with col_info:
        st.subheader(f"🏷️ {ticker_ind}")
        st.metric("Precio Actual", f"${precio_actual:,.2f}")
        if ruptura_texto: st.warning(ruptura_texto) # Mostramos el aviso si hay ruptura
        
        st.write("---")
        st.subheader("🎯 Señal")
        st.write(f"Estado: **{etiqueta_ind}**")
        st.metric("RSI", f"{rsi_val:.1f}")
        
        st.write("---")
        st.markdown(f"**Referencia ({dias_vencimiento})**")
        st.metric("🏔️ Techo", f"${techo_ref:.2f}")
        st.metric("📉 Piso", f"${piso_ref:.2f}")
        
        # --- 1. NUEVO: Lógica de Volumen del Profesor ---
        vol_txt_ind, vol_tipo_ind = analizar_volumen(data)
        if vol_tipo_ind == "success":
            st.success(vol_txt_ind)
        elif vol_tipo_ind == "error":
            st.error(vol_txt_ind)
        else:
            st.warning(vol_txt_ind)
            
        # --- 2. LO QUE YA TENÍAS: Volatilidad ---
        texto_vol, color_vol = evaluar_volatilidad(data)
        if color_vol == "error":
            st.error(texto_vol)
        else:
            st.success(texto_vol)
            
        # --- 3. LO QUE YA TENÍAS: Tendencia EMA ---
        if precio_actual > ema200_actual:
            st.success("📈 ALCISTA")
        else:
            st.error("📉 BAJISTA")
            
        st.write("---")
        
        # --- 4. LO QUE YA TENÍAS: Gestión de Riesgo ---
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
 # --- FILA 3: COPILOTO IA (ANCHO COMPLETO ABAJO) ---
    # --- FILA 3: COPILOTO IA ---
    st.markdown("---")
    with st.container():
        st.subheader("🤖 Pregúntame tus dudas")
        
        try:
            raw_news = yf.Ticker(ticker_ind).news
            resumen_noticias = "\n".join([n['title'] for n in raw_news[:3]]) if raw_news else "Sin noticias."
        except:
            resumen_noticias = "No se pudieron cargar noticias."
        texto_vol, color_vol = evaluar_volatilidad(data)
        vol_info = "ALTA (Cuidado con el riesgo)" if color_vol == "error" else "Normal/Baja"
        duda = st.chat_input(f"Pregúntale a Gemini sobre {ticker_ind}...")
        
        if duda:
            # 1. Definimos el contexto solo si el usuario escribió algo
            contexto = f"""
            INVESTIGACIÓN EN TIEMPO REAL: Usa Google Search para encontrar noticias de las últimas 24h sobre {ticker_ind}.
            DATOS TÉCNICOS ACTUALES:
            - Precio: ${precio_actual:.2f} | RSI: {rsi_val:.1f}
            - Tendencia: {"ALCISTA" if precio_actual > ema200_actual else "BAJISTA"}
            - VOLUMEN: {vol_info}  <-- NUEVO DATO
            - Soporte: ${prox_nivel:.2f}
            - REFERENCIA DEL PERIODO ({dias_vencimiento}): Techo ${techo_ref:.2f} | Piso ${piso_ref:.2f}
            - ESTADO DE RUPTURA: {ruptura_texto if ruptura_texto else "Dentro de rangos normales"}
            - Estrategia: Vencimiento a {dias_vencimiento}, riesgo 2% (${dinero_en_riesgo:.2f}), meta 4%.
            - Quiero que siempre hables con lenguaje muy sencillo y fácil de entender para cualquier persona aún sin tener conocimientos de trading
            
            TAREA: Analiza los datos y responde a: {duda}
            
            REGLA DE FORMATO: Al final de tu respuesta, DEBES incluir una sección llamada 
            '📢 CONCLUSIÓN SIMPLE Y PLAN DE ACCIÓN' con este formato:
            1. ¿Qué significa esto?
            2. ¿Qué hacer HOY con la bolsa cerrada?
            3. ¿Qué hacer MAÑANA a las 8:00 AM?
            """
            
            # 2. El mensaje del asistente ahora vive dentro del 'if duda'
            with st.chat_message("assistant"):
                if model:
                    try:
                        response = model.generate_content(contexto)
                        st.write(response.text)
                        # Guardamos en la nube
                    except Exception as e:
                        if "429" in str(e) or "quota" in str(e).lower():
                            st.warning("⚠️ Cuota excedida. Respondiendo con datos técnicos.")
                            res_simple = model.generate_content(contexto.replace("Usa Google Search", "Ignora la búsqueda"))
                            st.write(res_simple.text)
                        else:
                            st.error(f"Error: {e}")
                else:
                    st.error("IA no configurada.")
