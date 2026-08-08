import streamlit as st
from streamlit_option_menu import option_menu
import re
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
    

# ============================================================
# BARRA LATERAL: SOLO EL SELECTOR DE APARTADOS
# ============================================================
with st.sidebar:
    seccion = option_menu(
        menu_title="Superior App",
        options=["Trading", "Largo Plazo"],
        icons=["graph-up-arrow", "bank2"],
        menu_icon="bar-chart-line",
        default_index=0,
    )


# ============================================================
# APARTADO: TRADING (todo lo que ya tenías)
# ============================================================
def mostrar_trading():
    # --- BARRA LATERAL ---
    st.sidebar.header("💰 Gestión de Capital")
    capital_total = st.sidebar.number_input("Dinero en Portafolio ($)", value=1000.0, step=100.0)
    dinero_en_riesgo = capital_total * 0.02
    meta_ganancia = capital_total * 0.04

    st.sidebar.header("📋 Configuración")
    dias_vencimiento = st.sidebar.selectbox("Vencimiento", ("Hoy (0DTE)", "1 a 3 días", "1 semana", "1 mes o más"), index=0)
    tiempos = {"Hoy (0DTE)": ("1m", "1d"), "1 a 3 días": ("5m", "5d"), "1 semana": ("30m", "1mo"), "1 mes o más": ("1d", "1y")}
    v_intervalo, v_periodo = tiempos[dias_vencimiento]

    # --- NUEVA LÓGICA DE AGREGAR TICKER POR SECTOR ---
    st.sidebar.subheader("➕ Añadir Activo Personalizado")
    nuevo_t = st.sidebar.text_input("Ticker (Ej: BABA, PFE)", value="").upper().strip()
    sector_destino = st.sidebar.selectbox("Selecciona el Sector", ("💻 Tecnología", "🏦 Financiero", "📦 Consumo", "⚡ Energía/Otros"))

    # Inicializamos una lista en la memoria de la sesión para guardar lo que agregues
    if "tickers_personalizados" not in st.session_state:
        st.session_state["tickers_personalizados"] = []

    if st.sidebar.button("Agregar al Monitor"):
        if nuevo_t:
            # Guardamos el ticker junto con su sector asignado
            st.session_state["tickers_personalizados"].append({"ticker": nuevo_t, "sector": sector_destino})
            st.sidebar.success(f"¡{nuevo_t} agregado a {sector_destino}!")
        else:
            st.sidebar.error("Escribe un ticker válido.")

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
    st.title("🚀 SUPERIOR SCANNERR")

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

    # Base de empresas por sector fijo
    sectores = {
        "💻 Tecnología": ["AAPL", "NVDA", "MSFT", "GOOGL", "AMD"],
        "🏦 Financiero": ["JPM", "GS", "BAC", "V", "MA"],
        "📦 Consumo": ["WMT", "COST", "AMZN", "PG", "KO"],
        "⚡ Energía/Otros": ["XOM", "TSLA", "META", "NFLX", "SPY"]
    }

    # Inyectamos dinámicamente los tickers personalizados que guardaste en la sesión
    if "tickers_personalizados" in st.session_state:
        for item in st.session_state["tickers_personalizados"]:
            sec = item["sector"]
            tk = item["ticker"]
            # Evitamos duplicados en las listas
            if sec in sectores and tk not in sectores[sec]:
                sectores[sec].append(tk)


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
    # --- COLOCAR AL FINAL DE TU ARCHIVO SUSTITUYENDO EL ANTERIOR ---

    st.markdown("---")
    st.header("📊 Laboratorio Estadístico (Backtesting de Datos)")

    archivo_datos = st.file_uploader("Sube tu archivo CSV histórico (Ej: Datos históricos NVDA.csv)", type=["csv"])

    if archivo_datos is not None:
        with st.spinner("Analizando patrones históricos con tus criterios exactos..."):
            try:
                # Leer datos
                df_hist = pd.read_csv(archivo_datos)

                # Limpieza de datos (Formato Investing con puntos y comas)
                for col in ['Cierre', 'Apertura', 'Máximo', 'Mínimo']:
                    if col in df_hist.columns and df_hist[col].dtype == 'object':
                        df_hist[col] = df_hist[col].astype(str).str.replace('.', '').str.replace(',', '.').astype(float)

                # Invertimos para orden cronológico correcto (Viejo -> Nuevo)
                df_hist = df_hist.iloc[::-1].reset_index(drop=True)

                # CÁLCULO DE MEDIAS MÓVILES
                df_hist['MA20'] = df_hist['Cierre'].rolling(window=20).mean()
                df_hist['MA40'] = df_hist['Cierre'].rolling(window=40).mean()
                df_hist['MA100'] = df_hist['Cierre'].rolling(window=100).mean()
                df_hist['MA200'] = df_hist['Cierre'].rolling(window=200).mean()

                total_call, aciertos_call = 0, 0
                total_put, aciertos_put = 0, 0

                fechas_martillos_call = []
                fechas_martillos_put = []

                escenarios_exito_call = []
                escenarios_exito_put = []

                # --- ESCANEO HISTÓRICO CON COLA REDUCIDA (50% DEL CUERPO) ---
                for i in range(200, len(df_hist) - 1):
                    fila = df_hist.iloc[i]
                    fecha_actual = fila['Fecha']
                    cuerpo = abs(fila['Apertura'] - fila['Cierre'])
                    mecha_superior = fila['Máximo'] - max(fila['Apertura'], fila['Cierre'])
                    mecha_inferior = min(fila['Apertura'], fila['Cierre']) - fila['Mínimo']
                    if cuerpo == 0: cuerpo = 0.001

                    vela_siguiente = df_hist.iloc[i+1]

                    # Estados de las medias móviles
                    orden_alcista = fila['MA20'] > fila['MA40'] > fila['MA100'] > fila['MA200']
                    orden_bajista = fila['MA20'] < fila['MA40'] < fila['MA100'] < fila['MA200']
                    abajo_de_todas = fila['Cierre'] < min(fila['MA20'], fila['MA40'], fila['MA100'], fila['MA200'])
                    arriba_de_todas = fila['Cierre'] > max(fila['MA20'], fila['MA40'], fila['MA100'], fila['MA200'])

                    # --- 🔨 MARTILLO CALL MODIFICADO (Cola >= 50% del Cuerpo) ---
                    # Ahora la mecha inferior solo necesita ser la mitad de la caja (cuerpo * 0.5)
                    if (mecha_inferior >= (cuerpo * 0.5) and 
                        mecha_superior < (cuerpo * 0.40) and 
                        fila['Cierre'] > fila['Apertura']):

                        total_call += 1
                        ganó = vela_siguiente['Cierre'] > fila['Cierre']
                        resultado_txt = "✅ GANADORA" if ganó else "❌ PERDEDORA"
                        fechas_martillos_call.append(f"📅 {fecha_actual} | Cierre Hoy: ${fila['Cierre']:.2f} -> Mañana: ${vela_siguiente['Cierre']:.2f} ({resultado_txt})")

                        if ganó:
                            aciertos_call += 1
                            escenarios_exito_call.append({
                                "orden": orden_alcista,
                                "abajo_todas": abajo_de_todas,
                                "arriba_200": fila['Cierre'] > fila['MA200']
                            })

                    # --- ☄️ MARTILLO INVERTIDO PUT MODIFICADO (Cola >= 50% del Cuerpo) ---
                    # Ahora la mecha superior solo necesita ser la mitad de la caja (cuerpo * 0.5)
                    if (mecha_superior >= (cuerpo * 0.5) and 
                        mecha_inferior < (cuerpo * 0.40) and 
                        fila['Cierre'] < fila['Apertura']):

                        total_put += 1
                        ganó = vela_siguiente['Cierre'] < fila['Cierre']
                        resultado_txt = "✅ GANADORA" if ganó else "❌ PERDEDORA"
                        fechas_martillos_put.append(f"📅 {fecha_actual} | Cierre Hoy: ${fila['Cierre']:.2f} -> Mañana: ${vela_siguiente['Cierre']:.2f} ({resultado_txt})")

                        if ganó:
                            aciertos_put += 1
                            escenarios_exito_put.append({
                                "orden": orden_bajista,
                                "arriba_todas": arriba_de_todas,
                                "abajo_200": fila['Cierre'] < fila['MA200']
                            })

                # 3. MOSTRAR RESULTADOS CON PORCENTAJES REALES DE ÉXITO
                st.subheader("📊 Reporte Técnico Realista (Evaluación a 1 Vela Adelante)")

                pct_call = 0.0
                pct_put = 0.0

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("### 🔨 Patrón Martillo (CALL)")
                    if total_call > 0:
                        pct_call = (aciertos_call / total_call) * 100
                        st.metric("Efectividad Histórica General", f"{pct_call:.1f}%", f"{aciertos_call}/{total_call} Señales")

                        with st.expander("🔍 Historial de Fechas y Cierres (CALL)"):
                            for f in fechas_martillos_call:
                                st.write(f)

                        df_ex_call = pd.DataFrame(escenarios_exito_call)
                        if not df_ex_call.empty:
                            st.markdown("**Análisis de Contexto Ganador:**")

                            a_orden = int(df_ex_call['orden'].sum())
                            a_piso = int(df_ex_call['abajo_todas'].sum())
                            a_tendencia = int(df_ex_call['arriba_200'].sum())

                            p_orden_call = (a_orden / aciertos_call) * 100 if aciertos_call > 0 else 0
                            p_piso_call = (a_piso / aciertos_call) * 100 if aciertos_call > 0 else 0
                            p_tend_call = (a_tendencia / aciertos_call) * 100 if aciertos_call > 0 else 0

                            st.write(f"- Con Medias Ordenadas (20>40>100>200): **{a_orden} aciertos**")
                            st.caption(f"📢 *En el {p_orden_call:.1f}% de los casos ganadores, el martillo funcionó teniendo las medias ordenadas a favor.*")

                            st.write(f"- Comprando abajo de todas las medias (Piso): **{a_piso} aciertos**")
                            st.caption(f"📢 *En el {p_piso_call:.1f}% de los casos ganadores, el martillo funcionó estando por debajo de todas las medias.*")

                            st.write(f"- A favor de tendencia (Arriba de MA200): **{a_tendencia} aciertos**")
                            st.caption(f"📢 *En el {p_tend_call:.1f}% de los casos ganadores, el martillo funcionó estando por encima de la media de 200.*")
                    else:
                        st.info("No se encontraron martillos con estas especificaciones.")

                with c2:
                    st.markdown("### ☄️ Martillo Invertido (PUT)")
                    if total_put > 0:
                        pct_put = (aciertos_put / total_put) * 100
                        st.metric("Efectividad Histórica General", f"{pct_put:.1f}%", f"{aciertos_put}/{total_put} Señales")

                        with st.expander("🔍 Historial de Fechas y Cierres (PUT)"):
                            for f in fechas_martillos_put:
                                st.write(f)

                        df_ex_put = pd.DataFrame(escenarios_exito_put)
                        if not df_ex_put.empty:
                            st.markdown("**Análisis de Contexto Ganador:**")

                            p_orden = int(df_ex_put['orden'].sum())
                            p_techo = int(df_ex_put['arriba_todas'].sum())
                            p_tendencia = int(df_ex_put['abajo_200'].sum())

                            p_orden_put = (p_orden / aciertos_put) * 100 if aciertos_put > 0 else 0
                            p_techo_put = (p_techo / aciertos_put) * 100 if aciertos_put > 0 else 0
                            p_tend_put = (p_tendencia / aciertos_put) * 100 if aciertos_put > 0 else 0

                            st.write(f"- Con Medias Ordenadas (20<40<100<200): **{p_orden} aciertos**")
                            st.caption(f"📢 *En el {p_orden_put:.1f}% de los casos ganadores, el martillo invertido funcionó teniendo las medias ordenadas a favor.*")

                            st.write(f"- Cazando el techo (Arriba de todas las medias): **{p_techo} aciertos**")
                            st.caption(f"📢 *En el {p_techo_put:.1f}% de los casos ganadores, el martillo invertido funcionó estando por encima de todas las medias.*")

                            st.write(f"- A favor de tendencia (Debajo de MA200): **{p_tendencia} aciertos**")
                            st.caption(f"📢 *En el {p_tend_put:.1f}% de los casos ganadores, el martillo invertido funcionó estando por debajo de la media de 200.*")
                    else:
                        st.info("No se encontraron martillos invertidos con estas especificaciones.")

                # --- NUEVA SECCIÓN: CLASIFICADOR DE ESCENARIOS DE PRECISIÓN ---
                st.markdown("---")
                st.subheader("🎯 Matriz de Micro-Contextos (Análisis Avanzado Inter-Medias)")

                micro_datos_call = []
                micro_datos_put = []

                for i in range(200, len(df_hist) - 1):
                    f = df_hist.iloc[i]
                    cuerpo = abs(f['Apertura'] - f['Cierre'])
                    m_sup = f['Máximo'] - max(f['Apertura'], f['Cierre'])
                    m_inf = min(f['Apertura'], f['Cierre']) - f['Mínimo']
                    if cuerpo == 0: cuerpo = 0.001

                    es_call = (m_inf >= (cuerpo * 0.5) and m_sup < (cuerpo * 0.4) and f['Cierre'] > f['Apertura'])
                    es_put = (m_sup >= (cuerpo * 0.5) and m_inf < (cuerpo * 0.4) and f['Cierre'] < f['Apertura'])

                    if es_call:
                        ganó = df_hist.iloc[i+1]['Cierre'] > f['Cierre']
                        if f['Cierre'] > f['MA200'] and f['Cierre'] < f['MA40']:
                            cat = "Arriba MA200 + Debajo MA40 (Retroceso Profundo)"
                        elif f['Cierre'] > f['MA200'] and f['Cierre'] < f['MA20'] and f['Cierre'] > f['MA40']:
                            cat = "Arriba MA200 + Debajo MA20 (Retroceso Corto)"
                        elif f['Cierre'] > max(f['MA20'], f['MA40'], f['MA100'], f['MA200']):
                            cat = "Arriba de todas las Medias (Fuerza Máxima)"
                        else:
                            cat = "Otros escenarios (Bajo la MA200 / Rangos)"
                        micro_datos_call.append({"Escenario": cat, "Resultado": 1 if ganó else 0, "Tipo": "CALL"})

                    if es_put:
                        ganó = df_hist.iloc[i+1]['Cierre'] < f['Cierre']
                        if f['Cierre'] < f['MA200'] and f['Cierre'] > f['MA40']:
                            cat = "Debajo MA200 + Encima MA40 (Rebote a Resistencia)"
                        elif f['Cierre'] < min(f['MA20'], f['MA40'], f['MA100'], f['MA200']):
                            cat = "Debajo de todas las Medias (Caída Libre)"
                        else:
                            cat = "Otros escenarios"
                        micro_datos_put.append({"Escenario": cat, "Resultado": 1 if ganó else 0, "Tipo": "PUT"})

                col_m1, col_m2 = st.columns(2)
                df_final_combinado = pd.DataFrame() # DataFrame para unificar y buscar el ganador absoluto

                with col_m1:
                    st.write("**🔍 Desglose de Precisión para CALL:**")
                    if micro_datos_call:
                        df_mc = pd.DataFrame(micro_datos_call)
                        df_res = df_mc.groupby("Escenario")["Resultado"].agg(['count', 'sum']).reset_index()
                        df_res['% Efectividad'] = (df_res['sum'] / df_res['count']) * 100
                        df_res.columns = ["Configuración de Medias", "Señales Totales", "Aciertos", "% Efectividad"]
                        st.dataframe(df_res.style.format({"% Efectividad": "{:.1f}%"}), hide_index=True)

                        df_res['Tipo'] = "CALL"
                        df_final_combinado = pd.concat([df_final_combinado, df_res])
                    else:
                        st.caption("Sin datos.")

                with col_m2:
                    st.write("**🔍 Desglose de Precisión para PUT:**")
                    if micro_datos_put:
                        df_mp = pd.DataFrame(micro_datos_put)
                        df_res_p = df_mp.groupby("Escenario")["Resultado"].agg(['count', 'sum']).reset_index()
                        df_res_p['% Efectividad'] = (df_res_p['sum'] / df_res_p['count']) * 100
                        df_res_p.columns = ["Configuración de Medias", "Señales Totales", "Aciertos", "% Efectividad"]
                        st.dataframe(df_res_p.style.format({"% Efectividad": "{:.1f}%"}), hide_index=True)

                        df_res_p['Tipo'] = "PUT"
                        df_final_combinado = pd.concat([df_final_combinado, df_res_p])
                    else:
                        st.caption("Sin datos.")

                # --- NUEVA LÓGICA DE VEREDICTO POR MAXIMA EFECTIVIDAD DE MATRIZ ---
                st.markdown("---")
                st.subheader("🏆 Veredicto de Máxima Certeza Histórica")

                if df_final_combinado.empty:
                    st.warning("No hay suficientes datos analizados para extraer una ventaja estadística.")
                else:
                    # Filtro de seguridad: Exigimos un mínimo de 3 señales para que sea estadísticamente válido
                    df_filtrado = df_final_combinado[df_final_combinado["Señales Totales"] >= 3]

                    if not df_filtrado.empty:
                        # Encontramos la fila con el mayor porcentaje de efectividad
                        mejor_escenario = df_filtrado.sort_values(by="% Efectividad", ascending=False).iloc[0]

                        nombre_config = mejor_escenario["Configuración de Medias"]
                        efectividad_top = mejor_escenario["% Efectividad"]
                        aciertos_top = mejor_escenario["Aciertos"]
                        totales_top = mejor_escenario["Señales Totales"]
                        tipo_operacion = mejor_escenario["Tipo"]

                        icono = "🟢 [CALL]" if tipo_operacion == "CALL" else "🔴 [PUT]"

                        st.success(
                            f"👑 **ESTRATEGIA ÓPTIMA DETECTADA:** El escenario más certero en la historia de este activo es cuando se opera un **{tipo_operacion}** bajo la configuración: \n\n"
                            f"👉 **{nombre_config}** \n\n"
                            f"Este micro-contexto específico arrojó una efectividad quirúrgica del **{efectividad_top:.1f}%** "
                            f"({aciertos_top}/{totales_top} aciertos). Cuando detectes este escenario en el monitor, tu probabilidad de éxito es máxima."
                        )
                    else:
                        st.info("⚠️ Los escenarios con mayor porcentaje tienen muy pocas señales en el archivo. Se requiere una muestra histórica más amplia para emitir un veredicto seguro.")

            except Exception as e:
                st.error(f"Error procesando el archivo CSV: {e}")

# ============================================================
# APARTADO: INVERSIÓN A LARGO PLAZO
# ============================================================

# Lista de métricas fundamentales a capturar (id_interno, etiqueta visible)
METRICAS_LP = [
    ("gross_margin", "Gross Margin (%)"),
    ("operative_margin", "Operating Margin (%)"),
    ("net_margin", "Net Margin (%)"),
    ("roa", "ROA (%)"),
    ("roe", "ROE (%)"),
    ("roic", "ROIC (%)"),
    ("eps", "EPS ($)"),
    ("fcf_sales", "Free Cash Flow / Sales (%)"),
    ("fcf_net_income", "Free Cash Flow / Net Income (%)"),
    ("fcf_share", "Free Cash Flow / Share ($)"),
    ("quick_ratio", "Quick Ratio"),
    ("current_ratio", "Current Ratio"),
    ("debt_equity", "Debt to Equity"),
    ("pe_ratio", "PE Ratio"),
    ("ps_ratio", "PS Ratio"),
    ("pe_cash_flow_ratio", "PE Cash Flow Ratio"),
    ("price_book_ratio", "Price to Book Ratio"),
    ("peg_ratio", "PEG Ratio"),
]


def _parsear_valores(texto):
    """Convierte '12 13 14' en [12.0, 13.0, 14.0]. Acepta coma decimal."""
    valores = []
    for token in texto.strip().split():
        token = token.replace(",", ".")
        valores.append(float(token))
    return valores


# Campos donde Morningstar pega el dato con el signo % pegado (ej. "71.07%\t74.99%")
CAMPOS_CON_SIMBOLO_PORCENTAJE = {
    "gross_margin", "operative_margin", "net_margin",
    "roa", "roe", "roic", "fcf_sales",
}


def _parsear_valores_porcentaje(texto):
    """Convierte '71.07%\t71.07%\t74.99%' en [71.07, 71.07, 74.99].
    Usa el símbolo % (o cualquier espacio/tab) como separador, ignorando el signo."""
    texto = texto.replace(",", ".")
    tokens = re.findall(r'-?\d+(?:\.\d+)?', texto)
    return [float(t) for t in tokens]


def _resumen_metricas_texto(nombre_empresa, datos):
    """Arma un bloque de texto plano con las métricas de una empresa, para usarlo en el prompt de la IA."""
    lineas = [f"Empresa: {nombre_empresa}"]
    for info in datos.values():
        if info["promedio"] is None:
            continue
        etiqueta_extra = " (dato único / promedio de 5 años)" if info["es_promedio_5y"] else f" (promedio de {len(info['valores'])} dato(s): {info['valores']})"
        lineas.append(f"- {info['label']}: {info['promedio']:.2f}{etiqueta_extra}")
    return "\n".join(lineas)


def _extraer_calificacion(texto, etiqueta):
    """Busca una línea tipo 'ETIQUETA: 7.5/10' en el texto de respuesta de la IA y devuelve el número."""
    match = re.search(rf'{etiqueta}:\s*([\d.]+)\s*/\s*10', texto)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def mostrar_largo_plazo():
    st.title("💼 Análisis Fundamental - Inversión a Largo Plazo")
    st.caption("Captura los indicadores fundamentales de una empresa, guárdalos, compara contra otras y pide un análisis con IA (incluyendo contexto cualitativo de noticias).")

    # --- Estado de sesión ---
    if "lp_empresas_guardadas" not in st.session_state:
        st.session_state["lp_empresas_guardadas"] = {}

    st.markdown("---")
    ticker_lp = st.text_input("🏷️ Ticker o Nombre de la Empresa", key="lp_ticker_actual", placeholder="Ej: AAPL")

    st.info("✏️ Ingresa los valores de cada indicador separados por un simple espacio (Ej: '12 13 14' para 3 años, se calculará el promedio automáticamente). Si solo tienes el promedio de los últimos 5 años ya calculado, marca la casilla '5Y' e ingresa un único dato.")

    datos_actuales = {}
    for key, label in METRICAS_LP:
        col1, col2 = st.columns([4, 1])
        with col1:
            valor_input = st.text_input(label, key=f"lp_input_{key}", placeholder="Ej: 12 13 14")
        with col2:
            es_promedio_5y = st.checkbox("5Y", key=f"lp_chk_{key}", help="Marca si el dato ingresado ya es el promedio de los últimos 5 años")

        valores, promedio = [], None
        if valor_input.strip():
            try:
                if key in CAMPOS_CON_SIMBOLO_PORCENTAJE:
                    valores = _parsear_valores_porcentaje(valor_input)
                else:
                    valores = _parsear_valores(valor_input)
                if es_promedio_5y and len(valores) > 1:
                    st.warning(f"⚠️ '{label}' está marcado como promedio de 5 años, pero ingresaste varios datos. Se usará el promedio de todos ellos igualmente.")
                promedio = sum(valores) / len(valores)
            except ValueError:
                st.error(f"⚠️ Revisa el formato de '{label}': deben ser números separados por espacio. (Texto recibido: '{valor_input}')")

        datos_actuales[key] = {
            "label": label,
            "valores": valores,
            "promedio": promedio,
            "es_promedio_5y": es_promedio_5y,
        }

    st.markdown("---")
    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        guardar = st.button("💾 Guardar Empresa", use_container_width=True)
    with col_g2:
        nueva = st.button("🆕 Limpiar Formulario", use_container_width=True)
    with col_g3:
        borrar_todo = st.button("🗑️ Borrar Comparaciones", use_container_width=True)

    if guardar:
        if not ticker_lp.strip():
            st.error("Escribe un ticker o nombre para identificar la empresa antes de guardar.")
        else:
            st.session_state["lp_empresas_guardadas"][ticker_lp.strip().upper()] = datos_actuales
            st.success(f"✅ Datos de {ticker_lp.strip().upper()} guardados. Puedes limpiar el formulario y capturar otra empresa para comparar.")

    if nueva:
        for key, _ in METRICAS_LP:
            st.session_state[f"lp_input_{key}"] = ""
            st.session_state[f"lp_chk_{key}"] = False
        st.session_state["lp_ticker_actual"] = ""
        st.rerun()

    if borrar_todo:
        st.session_state["lp_empresas_guardadas"] = {}
        st.success("Comparaciones borradas.")
        st.rerun()

    # --- Resumen de lo capturado actualmente ---
    with st.expander("📋 Ver resumen de los datos capturados en el formulario actual"):
        hay_datos = False
        for info in datos_actuales.values():
            if info["promedio"] is not None:
                hay_datos = True
                etiqueta = "promedio 5 años (dato único)" if info["es_promedio_5y"] else f"promedio de {len(info['valores'])} año(s)"
                st.write(f"**{info['label']}:** {info['promedio']:.2f}  _( {etiqueta} )_")
        if not hay_datos:
            st.caption("Aún no has llenado ningún indicador.")

    # --- Tabla comparativa de empresas guardadas ---
    empresas_guardadas = st.session_state["lp_empresas_guardadas"]
    if empresas_guardadas:
        st.markdown("---")
        st.subheader("📊 Comparación de Empresas Guardadas")

        tabla = {}
        for emp, datos in empresas_guardadas.items():
            tabla[emp] = {
                info["label"]: (round(info["promedio"], 2) if info["promedio"] is not None else "-")
                for info in datos.values()
            }
        df_comparacion = pd.DataFrame(tabla)
        st.dataframe(df_comparacion, use_container_width=True)

    # --- Análisis con IA ---
    st.markdown("---")
    st.subheader("🤖 Análisis con IA")

    opciones_analisis = ["Empresa actual (sin guardar)"]
    if len(empresas_guardadas) >= 2:
        opciones_analisis.append("Comparar empresas guardadas")

    modo_analisis = st.radio("¿Qué quieres analizar?", opciones_analisis, horizontal=True)
    incluir_cualitativo = st.checkbox("🌐 Incluir análisis cualitativo (buscar noticias e info reciente de la empresa)", value=True)

    if st.button("🔍 Generar Análisis"):
        if not model:
            st.error("IA no configurada.")

        elif modo_analisis == "Empresa actual (sin guardar)":
            nombre_emp = ticker_lp.strip().upper() if ticker_lp.strip() else "la empresa analizada"
            resumen = _resumen_metricas_texto(nombre_emp, datos_actuales)
            hay_datos_cuant = any(info["promedio"] is not None for info in datos_actuales.values())

            if not hay_datos_cuant:
                st.warning("⚠️ No llenaste ningún indicador cuantitativo. Llena al menos uno antes de generar el análisis.")
            else:
                # --- PROMPT 1: ANÁLISIS CUANTITATIVO ---
                prompt_cuant = f"""
                Actúa como un analista financiero experto en inversión fundamental a largo plazo (estilo value/growth investing).
                Habla en español, con lenguaje claro y sencillo, sin dejar de ser técnicamente riguroso.

                DATOS FUNDAMENTALES DE {nombre_emp}:
                {resumen}

                TAREA:
                1. Evalúa la rentabilidad (márgenes, ROA, ROE, ROIC).
                2. Evalúa la salud financiera (liquidez: Quick/Current Ratio; apalancamiento: Debt to Equity).
                3. Evalúa la valuación (PE, PS, PEG, Price to Book, PE Cash Flow).
                4. Evalúa la generación y calidad del flujo de caja libre (Free Cash Flow).
                5. IMPORTANTE: evalúa si los márgenes y demás indicadores son CONSISTENTES en el tiempo o
                   presentan alta volatilidad/tendencia negativa. Usa los datos por año que vienen entre paréntesis
                   junto a cada indicador (no solo el promedio) para juzgar esta consistencia.

                Termina con una sección '📢 CONCLUSIÓN CUANTITATIVA' explicando el resultado.
                Después, en su propia línea y SIN NADA MÁS en esa línea, escribe exactamente:
                CALIFICACIÓN_CUANTITATIVA: X/10
                (reemplaza X por tu calificación del 1 al 10 sobre la solidez cuantitativa de la empresa)
                """

                with st.spinner("Analizando indicadores cuantitativos..."):
                    try:
                        texto_cuant = model.generate_content(prompt_cuant).text
                    except Exception as e:
                        st.error(f"Error en el análisis cuantitativo: {e}")
                        texto_cuant = None

                texto_cual = None
                if incluir_cualitativo and texto_cuant is not None:
                    # --- PROMPT 2: ANÁLISIS CUALITATIVO (4 pilares) ---
                    prompt_cual = f"""
                    Realiza un análisis cualitativo profundo de {nombre_emp} usando Google Search para investigar
                    noticias, reportes financieros, entrevistas, foros de inversión y su información pública más
                    reciente. Evalúa los siguientes 4 pilares con evidencia real (no supuestos):

                    1. MODELO DE NEGOCIO
                    - ¿Su propuesta de valor genera baja o alta tasa de abandono (churn) de clientes?
                    - ¿Su crecimiento es orgánico o depende de fuertes campañas de publicidad/marketing?
                    - ¿El cliente usa el producto o servicio de forma recurrente?
                    - ¿La empresa puede subir precios (inelástica) o es sensible al precio (elástica)?
                    - ¿Tiene bajo o alto costo de adquisición de clientes (CAC)?
                    - ¿Tiene altas devoluciones o quejas de clientes?
                    - ¿Tiene capacidad real de innovar?
                    - ¿Se ve obligada a hacer descuentos constantemente?
                    - ¿Sus productos se perciben distintos a los de la competencia?
                    - ¿Qué tan fácil es para la competencia copiar sus innovaciones?
                    - ¿Necesita invertir masivamente solo para mantener su posición actual?
                    - ¿Sus ingresos son recurrentes o dependen de compras grandes y únicas?
                    - ¿Gana más por cliente conforme crece?
                    - ¿Tiene productos o servicios diversificados?
                    - ¿Sus ingresos están distribuidos geográficamente o dependen de una sola región?
                    - ¿Algún cliente representa más del 5% de los ingresos totales? (excepto negocios B2B)

                    2. VENTAJA COMPETITIVA (MOAT)
                    - ¿Tiene un monopolio natural o el mercado es fácil de fragmentar?
                    - ¿El costo de adquisición de clientes se reduce con el tiempo?
                    - ¿Sus productos o servicios son fáciles de sustituir?
                    - ¿Qué tan fácil es para un cliente migrar a la competencia?
                    - ¿La marca tiene valor emocional/lealtad?
                    - ¿Sus patentes son fuertes o débiles?
                    - ¿Posee datos exclusivos o propietarios?
                    - ¿Tiene economías de escala reales?
                    - ¿Tiene acceso exclusivo a materias primas o insumos clave?
                    - ¿Tiene procesos propios únicos o son estándar de la industria?

                    3. EQUIPO DIRECTIVO Y CULTURA EMPRESARIAL
                    - ¿El equipo directivo tiene varios años de experiencia o hay alta rotación?
                    - ¿Las compensaciones son a largo plazo (acciones) o a corto plazo?
                    - ¿Los directivos tienen participación accionaria significativa?
                    - ¿La gerencia es transparente con inversionistas?
                    - ¿El CEO es prudente en la asignación de capital?
                    - ¿La junta directiva es independiente y justa, o son familiares/amigos?
                    - ¿La empresa tiene baja rotación de empleados?
                    - ¿La organización se enfoca en resolver problemas del cliente o en intereses propios?
                    - ¿Son éticos y reconocidos por ello?

                    4. OPORTUNIDADES Y RIESGOS DE LA INDUSTRIA
                    - ¿El mercado está creciendo o cayendo?
                    - ¿El mercado está fragmentado con oportunidad de crecimiento, o dominado por 2-3 grandes
                      jugadores? (evalúa si la empresa analizada es uno de ellos)
                    - ¿La empresa se beneficia o se ve perjudicada por cambios demográficos futuros?
                    - ¿La empresa forma parte de un oligopolio?
                    - ¿Tiene poder real sobre los precios de su industria?
                    - ¿Tiene baja o alta amenaza de productos sustitutos?
                    - ¿La regulación de su industria es amigable o agresiva hacia la empresa?
                    - ¿El país donde opera tiene un sistema legal fuerte o débil?

                    FORMATO DE RESPUESTA: Para cada uno de los 4 pilares, da un resumen breve con evidencia
                    encontrada y ciérralo con una etiqueta: 🟢 Fuerte / 🟡 Moderado / 🔴 Débil.

                    Termina con una sección '🌐 CONCLUSIÓN CUALITATIVA' resumiendo los 4 pilares.
                    Después, en su propia línea y SIN NADA MÁS en esa línea, escribe exactamente:
                    CALIFICACIÓN_CUALITATIVA: X/10
                    (reemplaza X por tu calificación del 1 al 10 sobre la calidad cualitativa del negocio)
                    """
                    with st.spinner("Investigando y analizando el contexto cualitativo..."):
                        try:
                            texto_cual = model.generate_content(prompt_cual).text
                        except Exception as e:
                            if "429" in str(e) or "quota" in str(e).lower():
                                st.warning("⚠️ Cuota de búsqueda excedida. Generando el análisis cualitativo sin Google Search.")
                                try:
                                    prompt_cual_sin_busqueda = prompt_cual.replace("usando Google Search para investigar", "basándote en tu conocimiento general sobre")
                                    texto_cual = model.generate_content(prompt_cual_sin_busqueda).text
                                except Exception as e2:
                                    st.error(f"Error en el análisis cualitativo: {e2}")
                            else:
                                st.error(f"Error en el análisis cualitativo: {e}")

                # --- Mostrar resultados individuales ---
                if texto_cuant is not None:
                    score_cuant = _extraer_calificacion(texto_cuant, "CALIFICACIÓN_CUANTITATIVA")
                    st.markdown("### 📐 Análisis Cuantitativo")
                    st.markdown(texto_cuant)
                    if score_cuant is not None:
                        st.metric("Calificación Cuantitativa", f"{score_cuant:.1f}/10")

                score_cual = None
                if texto_cual is not None:
                    score_cual = _extraer_calificacion(texto_cual, "CALIFICACIÓN_CUALITATIVA")
                    st.markdown("---")
                    st.markdown("### 🌐 Análisis Cualitativo")
                    st.markdown(texto_cual)
                    if score_cual is not None:
                        st.metric("Calificación Cualitativa", f"{score_cual:.1f}/10")

                # --- PROMPT 3: SÍNTESIS / CONCLUSIÓN GENERAL ---
                if texto_cuant is not None and texto_cual is not None:
                    score_cuant_local = _extraer_calificacion(texto_cuant, "CALIFICACIÓN_CUANTITATIVA")
                    score_cual_local = _extraer_calificacion(texto_cual, "CALIFICACIÓN_CUALITATIVA")
                    promedio_general = (
                        round((score_cuant_local + score_cual_local) / 2, 1)
                        if (score_cuant_local is not None and score_cual_local is not None) else None
                    )

                    prompt_sintesis = f"""
                    Eres un analista financiero senior. Tienes dos análisis independientes de {nombre_emp}:

                    === ANÁLISIS CUANTITATIVO (calificación {score_cuant_local}/10) ===
                    {texto_cuant}

                    === ANÁLISIS CUALITATIVO (calificación {score_cual_local}/10) ===
                    {texto_cual}

                    TAREA: Da una CONCLUSIÓN GENERAL en español, sencilla y directa, combinando ambos análisis:
                    indica si {nombre_emp} es una buena opción de inversión a largo plazo, qué pesa más
                    (lo cuantitativo o lo cualitativo) y por qué. No repitas todo el detalle, sintetiza lo esencial.

                    Después de tu conclusión, en su propia línea y SIN NADA MÁS en esa línea, escribe exactamente:
                    CALIFICACIÓN_PROMEDIO: {promedio_general if promedio_general is not None else "X"}/10
                    """
                    with st.spinner("Generando conclusión general..."):
                        try:
                            texto_sintesis = model.generate_content(prompt_sintesis).text
                            st.markdown("---")
                            st.markdown("### 🏁 Conclusión General")
                            st.markdown(texto_sintesis)
                            if promedio_general is not None:
                                st.metric("Calificación Promedio General", f"{promedio_general:.1f}/10")
                        except Exception as e:
                            st.error(f"Error generando la conclusión general: {e}")

        else:
            # --- Modo: Comparar empresas guardadas (análisis cuantitativo comparativo) ---
            bloques = [_resumen_metricas_texto(emp, datos) for emp, datos in empresas_guardadas.items()]
            resumen_total = "\n\n".join(bloques)
            instruccion_busqueda = (
                "Usa Google Search para investigar noticias recientes (últimos 3-6 meses), posición competitiva, "
                "riesgos, ventajas competitivas (moat) y catalizadores relevantes de cada empresa. "
                "Incluye una sección de '🌐 Contexto Cualitativo' con lo que encuentres para cada una."
            ) if incluir_cualitativo else ""

            prompt = f"""
            Actúa como un analista financiero experto en inversión fundamental a largo plazo (estilo value/growth investing).
            Habla en español, con lenguaje claro y sencillo, sin dejar de ser técnicamente riguroso.

            Compara las siguientes empresas con base en sus datos fundamentales:

            {resumen_total}

            {instruccion_busqueda}

            TAREA: Compara rentabilidad, salud financiera, valuación y generación de caja entre todas las empresas.
            Evalúa también si los márgenes de cada una son consistentes en el tiempo o volátiles, usando los
            datos por año que vienen entre paréntesis junto a cada indicador.

            Termina SIEMPRE con una sección '🏆 VEREDICTO' indicando cuál es la mejor opción de inversión a largo plazo
            entre las analizadas, y por qué, en lenguaje sencillo.
            """

            with st.spinner("Analizando y comparando empresas..."):
                try:
                    response = model.generate_content(prompt)
                    st.markdown(response.text)
                except Exception as e:
                    if "429" in str(e) or "quota" in str(e).lower():
                        st.warning("⚠️ Cuota excedida en la búsqueda. Generando análisis solo con los datos numéricos.")
                        try:
                            prompt_sin_busqueda = prompt.replace(instruccion_busqueda, "")
                            response = model.generate_content(prompt_sin_busqueda)
                            st.markdown(response.text)
                        except Exception as e2:
                            st.error(f"Error: {e2}")
                    else:
                        st.error(f"Error generando el análisis: {e}")

    # --- Chat libre sobre la empresa / comparación ---
    st.markdown("---")
    with st.container():
        st.subheader("💬 Pregúntale al Analista")
        duda_lp = st.chat_input("Pregunta algo sobre esta empresa o comparación...")
        if duda_lp:
            nombre_emp = ticker_lp.strip().upper() if ticker_lp.strip() else "la empresa actual"
            contexto_chat = f"""
            Eres un analista financiero fundamental. Habla en español, con lenguaje claro y sencillo.

            DATOS DE LA EMPRESA EN EL FORMULARIO ({nombre_emp}):
            {_resumen_metricas_texto(nombre_emp, datos_actuales)}

            EMPRESAS GUARDADAS PARA COMPARAR: {", ".join(empresas_guardadas.keys()) if empresas_guardadas else "Ninguna guardada aún"}

            PREGUNTA DEL USUARIO: {duda_lp}

            Responde con base en los datos disponibles. Si la pregunta requiere información externa reciente, usa Google Search.
            """
            with st.chat_message("assistant"):
                if model:
                    try:
                        resp = model.generate_content(contexto_chat)
                        st.write(resp.text)
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.error("IA no configurada.")



# ============================================================
# RUTEO PRINCIPAL SEGÚN EL APARTADO SELECCIONADO
# ============================================================
if seccion == "Trading":
    mostrar_trading()
elif seccion == "Largo Plazo":
    mostrar_largo_plazo()
