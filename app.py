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
    ("ebit", "EBIT Margin (%)"),
    ("ebitda", "EBITDA Margin (%)"),
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
    "roa", "roe", "roic", "fcf_sales", "ebit", "ebitda",
}


def _parsear_valores_porcentaje(texto):
    """Convierte '71.07%\t71.07%\t74.99%' en [71.07, 71.07, 74.99].
    Usa el símbolo % (o cualquier espacio/tab) como separador, ignorando el signo."""
    texto = texto.replace("−", "-").replace(",", ".")
    tokens = re.findall(r'-?\d+(?:\.\d+)?', texto)
    if not tokens:
        raise ValueError("sin números")
    return [float(t) for t in tokens]


def _resumen_metricas_texto(nombre_empresa, datos):
    """Arma un bloque de texto plano con las métricas de una empresa, para usarlo en el prompt de la IA."""
    lineas = [f"Empresa: {nombre_empresa}"]
    for info in datos.values():
        if info["promedio"] is None:
            continue
        if info.get("dato_unico"):
            etiqueta_extra = " (dato actual)"
        elif info["es_promedio_5y"]:
            etiqueta_extra = " (dato único / promedio de 5 años)"
        else:
            valores_txt = ", ".join(f"{v:.2f}" for v in info["valores"])
            etiqueta_extra = f" (datos año por año, DE MÁS RECIENTE A MÁS ANTIGUO: [{valores_txt}])"
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


# ============================================================
# MOTOR DE TRES TRIBUNALES: CALIDAD -> SALUD FINANCIERA -> PRECIO
# Reglas fijas basadas en el método de la skill AAI. No usa IA ni tokens.
# ============================================================

# Indicadores nuevos que necesita el motor (un solo dato: el valor actual)
METRICAS_MOTOR = [
    ("precio_actual", "PRECIO ACTUAL ($)", "EJ: 185.50  (VACÍO = SE TOMA DE YFINANCE)"),
    ("fair_value", "FAIR VALUE ($)", "EJ: 210"),
    ("ev_ebit", "EV / EBIT", "EJ: 14.2"),
    ("fcf_yield", "FCF YIELD (%)", "EJ: 3.8"),
    ("roic_5y", "ROIC PROMEDIO 5 AÑOS (%)", "EJ: 24.5"),
    ("eps_growth_5y", "CRECIMIENTO EPS PROMEDIO 5 AÑOS (%)", "EJ: 12"),
    ("rev_cagr_5y", "CRECIMIENTO INGRESOS 5 AÑOS - CAGR (%)", "EJ: 9.5"),
    ("buyback_yield", "BUYBACK YIELD (%)", "EJ: 2.1  (NEGATIVO SI EMITE ACCIONES)"),
    ("piotroski", "PIOTROSKI SCORE (0 A 9)", "EJ: 7"),
    ("altman_z", "ALTMAN Z-SCORE", "EJ: 4.3"),
    ("beneish_m", "BENEISH M-SCORE", "EJ: -2.4"),
]

# Explicación sencilla de cada indicador (se usa en el ícono de info y en el modo aprendizaje)
DEFINICIONES_MOTOR = {
    "roic": "CUÁNTO GANA LA EMPRESA POR CADA 100 QUE INVIERTE EN SU NEGOCIO. CON 20%, CADA 100 INVERTIDOS LE DEJAN 20 AL AÑO. META: 20% O MÁS.",
    "roic_5y": "EL MISMO ROIC PERO PROMEDIADO EN 5 AÑOS. SIRVE PARA DESCARTAR QUE UN SOLO BUEN AÑO INFLE EL RESULTADO. META: 20% O MÁS.",
    "roe": "CUÁNTO GANA POR CADA 100 QUE PUSIERON LOS ACCIONISTAS. META: 15% O MÁS SIN DEUDA ALTA, PORQUE LA DEUDA PUEDE INFLAR ESTE NÚMERO.",
    "deuda_capital": "QUÉ PARTE DE LA EMPRESA ESTÁ FINANCIADA CON PRÉSTAMOS. SE CALCULA SOLO A PARTIR DE TU DEBT TO EQUITY. MÁS DE 60% ES MUCHA DEUDA.",
    "gross_margin": "DE CADA 100 QUE VENDE, CUÁNTO LE QUEDA DESPUÉS DE PAGAR LO QUE CUESTA PRODUCIRLO. 40% O MÁS SUELE INDICAR ALGO DIFÍCIL DE COPIAR.",
    "fcf_net_income": "SI LAS GANANCIAS QUE REPORTA SE CONVIERTEN EN EFECTIVO REAL. 0.8 O MÁS SIGNIFICA QUE AL MENOS 80% DE LA GANANCIA ES DINERO EN CAJA.",
    "eps_growth_5y": "CUÁNTO HA CRECIDO LA GANANCIA POR ACCIÓN, EN PROMEDIO, EN LOS ÚLTIMOS 5 AÑOS. POSITIVO = GANA MÁS QUE ANTES.",
    "rev_cagr_5y": "CUÁNTO HAN CRECIDO LAS VENTAS POR AÑO, EN PROMEDIO, EN LOS ÚLTIMOS 5 AÑOS. POSITIVO = VENDE MÁS QUE ANTES.",
    "buyback_yield": "SI LA EMPRESA RECOMPRA SUS ACCIONES (POSITIVO) O EMITE NUEVAS (NEGATIVO). AL RECOMPRAR, TU PEDAZO DE LA EMPRESA CRECE; AL EMITIR, SE DILUYE.",
    "piotroski": "LISTA DE 9 PREGUNTAS DE SÍ O NO SOBRE SI EL NEGOCIO MEJORÓ RESPECTO AL AÑO ANTERIOR: SI GANA MÁS, SI DEBE MENOS, SI ES MÁS EFICIENTE. 7 O MÁS ES BUENA SEÑAL; 3 O MENOS INDICA DETERIORO.",
    "altman_z": "TERMÓMETRO DEL RIESGO DE QUIEBRA. ARRIBA DE 3 = ZONA SEGURA; ENTRE 1.81 Y 3 = ZONA GRIS; ABAJO DE 1.81 = ZONA DE PELIGRO.",
    "beneish_m": "DETECTOR DE MAQUILLAJE CONTABLE: BUSCA PATRONES TÍPICOS DE EMPRESAS QUE INFLAN SUS NÚMEROS. -1.78 O MENOS = SIN ALERTA; ARRIBA DE ESO, REVISAR CON CUIDADO.",
    "upside": "DIFERENCIA ENTRE EL FAIR VALUE (VALOR ESTIMADO) Y EL PRECIO ACTUAL. +20% SIGNIFICA QUE EL VALOR ESTIMADO ESTÁ 20% ARRIBA DEL PRECIO DE HOY.",
    "ev_ebit": "CUÁNTOS AÑOS DE GANANCIA OPERATIVA COSTARÍA COMPRAR LA EMPRESA COMPLETA, INCLUIDA SU DEUDA. 10 O MENOS = BARATA; 20 O MÁS = CARA; NEGATIVO = PIERDE DINERO OPERANDO.",
    "fcf_yield": "CUÁNTO EFECTIVO LIBRE GENERA LA EMPRESA POR CADA 100 QUE PAGAS POR SUS ACCIONES. 4% O MÁS = ATRACTIVO; 2% O MENOS = CARO.",
    "precio_actual": "PRECIO AL QUE COTIZA HOY LA ACCIÓN. SI LO DEJAS VACÍO, LA APP LO BUSCA EN YFINANCE CON EL TICKER.",
    "fair_value": "VALOR JUSTO ESTIMADO DE LA ACCIÓN SEGÚN MODELOS O ANALISTAS (INVESTINGPRO, MORNINGSTAR, ETC.). SE COMPARA CONTRA EL PRECIO ACTUAL.",
}

TRIBUNALES_INFO = {
    "CALIDAD": {
        "titulo": "TRIBUNAL DE CALIDAD",
        "definicion": "MIDE SI ES UN BUEN NEGOCIO CON 3 PRUEBAS: GREENBLATT (ROIC ALTO HOY Y A 5 AÑOS), MSCI (ROE ALTO SIN DEPENDER DE DEUDA) Y AQR (RENTABLE, CRECE, SEGURA Y NO DILUYE). ES LA PUERTA: SIN CALIDAD EXCELENTE NO LLEGA A DEEP DIVE NI A WATCHLIST.",
        "frases": {
            "EXCELENTE": ("NEGOCIO DE ALTA CALIDAD: PASA LAS 3 PRUEBAS", "ok"),
            "BUENA": ("BUEN NEGOCIO, PERO NO EXCEPCIONAL: PASA 2 DE 3 PRUEBAS", "warn"),
            "DÉBIL": ("NEGOCIO DÉBIL SEGÚN SUS NÚMEROS", "bad"),
        },
    },
    "SALUD": {
        "titulo": "TRIBUNAL DE SALUD FINANCIERA",
        "definicion": "REVISA SI LA EMPRESA ESTÁ SANA CON 3 SEÑALES: PIOTROSKI 7 O MÁS, ALTMAN Z 3 O MÁS Y BENEISH SIN ALERTA. ES EL CINTURÓN DE SEGURIDAD: SI SALE DÉBIL, BLOQUEA DEEP DIVE Y WATCHLIST.",
        "frases": {
            "EXCELENTE": ("FINANZAS SANAS EN LAS 3 SEÑALES", "ok"),
            "MIXTA": ("FINANZAS ACEPTABLES CON ALGÚN PUNTO A VIGILAR", "warn"),
            "DÉBIL": ("FINANZAS CON SEÑALES DE RIESGO", "bad"),
        },
    },
    "PRECIO": {
        "titulo": "TRIBUNAL DE PRECIO",
        "definicion": "COMPARA SEÑALES A FAVOR (EV/EBIT 10 O MENOS, UPSIDE 20% O MÁS, FCF YIELD 4% O MÁS) CONTRA SEÑALES EN CONTRA (UPSIDE -10% O MENOS, EV/EBIT 20 O MÁS O NEGATIVO, FCF YIELD 2% O MENOS). DECIDE ENTRE DEEP DIVE Y WATCHLIST.",
        "frases": {
            "MUY BARATA": ("TODAS LAS SEÑALES DICEN QUE ESTÁ BARATA", "ok"),
            "BARATA": ("LA MAYORÍA DE LAS SEÑALES DICEN QUE ESTÁ BARATA", "ok"),
            "MIXTA": ("PRECIO SIN UNA SEÑAL CLARA", "warn"),
            "CARA": ("VARIAS SEÑALES DICEN QUE ESTÁ CARA", "bad"),
        },
    },
}

CATEGORIAS_INFO = {
    "DEEP DIVE": ("#3fb950", "BUEN NEGOCIO, SANO Y A BUEN PRECIO: VALE LA PENA INVESTIGARLA A FONDO",
                  "NO SIGNIFICA COMPRAR. SIGNIFICA QUE LOS NÚMEROS PASAN LOS 3 TRIBUNALES Y AHORA TOCA LA MITAD CUALITATIVA: NEGOCIO, VENTAJA COMPETITIVA, DIRECTIVOS Y RIESGOS."),
    "WATCHLIST": ("#58a6ff", "BUEN NEGOCIO Y SANO, PERO HOY NO ESTÁ BARATA: AL RADAR ESPERANDO MEJOR PRECIO",
                  "PASA CALIDAD Y SALUD, PERO EL TRIBUNAL DE PRECIO NO LA VE BARATA. SE MONITOREA HASTA QUE EL PRECIO SEA ATRACTIVO."),
    "NEUTRAL": ("#d29922", "NI EXCELENTE NI MALA: HOY NO ES CANDIDATA",
                "PUEDE SER UNA BUENA EMPRESA SIN LLEGAR A EXCELENTE, O UNA EXCELENTE CON SALUD DÉBIL. PUEDE SUBIR DE CATEGORÍA SI SU CALIDAD O SALUD MEJORAN."),
    "DESCARTADA": ("#f85149", "HOY NO PASA LOS FILTROS DE CALIDAD",
                   "NO ES UN PRONÓSTICO: UNA DESCARTADA PUEDE SUBIR DE PRECIO. SOLO SIGNIFICA QUE, CON ESTE MÉTODO Y LOS DATOS DE HOY, NO ES INTERESANTE."),
    "OMITIDA POR MÉTODO": ("#8b949e", "BANCO, ASEGURADORA O UTILITY: ESTE MÉTODO NO LAS MIDE BIEN",
                           "EN LOS BANCOS LA DEUDA ES SU MATERIA PRIMA (LOS DEPÓSITOS SON PASIVO) Y EN LAS UTILITIES LA GANANCIA ESTÁ REGULADA. MODELOS COMO ALTMAN O ROIC LAS CASTIGARÍAN INJUSTAMENTE. LOS INDICADORES SE MUESTRAN SOLO COMO REFERENCIA."),
}

ALERTAS_INFO = {
    "POSIBLE TRAMPA DE VALOR": "SE VE BARATA PERO EL NEGOCIO ES DÉBIL. CASI SIEMPRE LO BARATO TIENE UNA RAZÓN.",
    "¿DEMASIADO BARATA?": "ES EXCELENTE Y SE VE MUY BARATA. REVISA QUÉ SABE EL MERCADO QUE TÚ NO: PUEDE HABER UN PROBLEMA QUE LOS NÚMEROS AÚN NO MUESTRAN.",
    "M-SCORE": "EL DETECTOR DE MAQUILLAJE CONTABLE ENCENDIÓ LA ALERTA. REVISA SUS REPORTES CON CUIDADO.",
    "MEJORA DÉBIL": "ES EXCELENTE PERO SU PIOTROSKI ES 3 O MENOS: EL NEGOCIO SE ESTÁ DETERIORANDO RESPECTO AL AÑO ANTERIOR.",
    "ALTMAN ZONA DE RIESGO": "ALTMAN Z MENOR A 1.81: ZONA DE PELIGRO FINANCIERO.",
    "EXCELENTE PERO SALUD DÉBIL": "PASÓ LA PRUEBA DE CALIDAD PERO REPROBÓ LA DE SALUD: EL CINTURÓN DE SEGURIDAD LA FRENÓ.",
    "DATOS INSUFICIENTES": "FALTAN 5 O MÁS INDICADORES CLAVE: SE DESCARTA POR FALTA DE INFORMACIÓN, NO POR SER MALA.",
}

ESTADOS_INFO = {
    "ok": ("A FAVOR", "#3fb950", "rgba(63,185,80,.15)"),
    "warn": ("PRECAUCIÓN", "#d29922", "rgba(210,153,34,.15)"),
    "bad": ("EN CONTRA", "#f85149", "rgba(248,81,73,.15)"),
    "nd": ("SIN DATO", "#8b949e", "rgba(139,148,158,.15)"),
}


def _parsear_dato_unico(texto):
    """Toma el primer número del texto. Acepta coma decimal, signo menos y símbolos como % o $."""
    texto = texto.replace("−", "-").replace(",", ".")
    tokens = re.findall(r'-?\d+(?:\.\d+)?', texto)
    if not tokens:
        raise ValueError("sin número")
    return float(tokens[0])


@st.cache_data(ttl=600)
def _precio_yfinance(ticker):
    """Precio actual desde yfinance. Si falla, regresa None."""
    try:
        p = getattr(yf.Ticker(ticker).fast_info, "last_price", None)
        return float(p) if p else None
    except Exception:
        return None


def _dato(datos, key):
    info = datos.get(key)
    return info.get("promedio") if info else None


def _fila_indicador(key, nombre, valor, texto_valor, estado, frase):
    if valor is None:
        return {"key": key, "nombre": nombre, "valor": "N/D", "estado": "nd",
                "frase": "NO CAPTURADO: NO SE PUEDE EVALUAR"}
    return {"key": key, "nombre": nombre, "valor": texto_valor, "estado": estado, "frase": frase}


def evaluar_tribunales(datos, es_financiera=False):
    """Aplica los 3 tribunales con reglas fijas. Regresa None si no hay ningún dato."""
    info_roic = datos.get("roic") or {}
    if info_roic.get("es_promedio_5y"):
        roic = None  # si solo capturaste el promedio de 5 años, no hay dato "actual"
    elif info_roic.get("valores"):
        roic = info_roic["valores"][0]  # el dato más reciente (primero de la fila)
    else:
        roic = None
    roic5 = _dato(datos, "roic_5y")
    roe = _dato(datos, "roe")
    gm = _dato(datos, "gross_margin")
    fcfni = _dato(datos, "fcf_net_income")
    if fcfni is not None and abs(fcfni) > 5:
        fcfni = fcfni / 100  # si se capturó en % (ej. 95) se convierte a razón (0.95)
    de = _dato(datos, "debt_equity")
    if de is None:
        dc = None
    elif de < 0:
        dc = 100.0  # capital contable negativo: se trata como deuda muy alta
    else:
        dc = de / (1 + de) * 100
    epsg = _dato(datos, "eps_growth_5y")
    revg = _dato(datos, "rev_cagr_5y")
    bb = _dato(datos, "buyback_yield")
    fcfy = _dato(datos, "fcf_yield")
    evebit = _dato(datos, "ev_ebit")
    fv = _dato(datos, "fair_value")
    price = _dato(datos, "precio_actual")
    pio = _dato(datos, "piotroski")
    alt = _dato(datos, "altman_z")
    m = _dato(datos, "beneish_m")
    upside = (fv - price) / price if (fv is not None and price is not None and price > 0) else None

    todos = [roic, roic5, roe, gm, fcfni, dc, epsg, revg, bb, fcfy, evebit, fv, pio, alt, m]
    if all(x is None for x in todos):
        return None

    # --- TRIBUNAL DE CALIDAD: 3 lentes ---
    # Lente 1: Greenblatt (ROIC actual y a 5 años)
    if roic is None and roic5 is None:
        L1 = "N/D"
    elif roic is not None and roic5 is not None:
        L1 = "SÍ" if (roic >= 20 and roic5 >= 20) else ("NO" if (roic < 10 or roic5 < 10) else "MEDIO")
    else:
        v = roic if roic is not None else roic5
        L1 = "MEDIO" if v >= 20 else ("NO" if v < 10 else "MEDIO")
    # Lente 2: MSCI (ROE con deuda sana)
    lev = (dc is not None and dc > 60) or (dc is None and alt is not None and alt < 1.81)
    if roe is None:
        L2 = "N/D"
    elif roe >= 15 and not lev:
        L2 = "SÍ"
    elif roe < 10 or lev:
        L2 = "NO"
    else:
        L2 = "MEDIO"
    # Lente 3: AQR (4 pilares: rentable, crece, segura, recompra)
    conv = (fcfni is not None and fcfni >= 0.8 and fcfy is not None and fcfy > 0)
    rent = "v" if sum([roe is not None and roe >= 15, gm is not None and gm >= 40, conv]) >= 2 else "i"
    if epsg is None and revg is None:
        cre = "i"
    elif epsg is not None and revg is not None:
        cre = "v" if (epsg > 0 and revg > 0) else ("x" if (epsg < 0 or revg < 0) else "i")
    else:
        g = epsg if epsg is not None else revg
        cre = "v" if g > 0 else ("x" if g < 0 else "i")
    if alt is None:
        seg = "i"
    elif alt >= 3:
        seg = "v"
    elif alt < 1.81:
        seg = "x"
    else:
        seg = "i"
    if bb is None:
        pay = "i"
    elif bb >= 0:
        pay = "v"
    elif bb < -2:
        pay = "x"
    else:
        pay = "i"
    pilares = [rent, cre, seg, pay]
    L3 = "SÍ" if (pilares.count("v") >= 3 and pilares.count("x") == 0) else ("NO" if pilares.count("x") >= 2 else "MEDIO")
    n_cal = [L1, L2, L3].count("SÍ")
    cal = "EXCELENTE" if n_cal == 3 else ("BUENA" if n_cal == 2 else "DÉBIL")

    # --- TRIBUNAL DE PRECIO ---
    n_val = sum([evebit is not None and 0 < evebit <= 10,
                 upside is not None and upside >= 0.20,
                 fcfy is not None and fcfy >= 4])
    v_c = sum([upside is not None and upside <= -0.10,
               evebit is not None and (evebit >= 20 or evebit < 0),
               fcfy is not None and fcfy <= 2])
    if v_c >= 2 and v_c > n_val:
        precio = "CARA"
    elif n_val >= 3 and n_val > v_c:
        precio = "MUY BARATA"
    elif n_val == 2 and n_val > v_c:
        precio = "BARATA"
    else:
        precio = "MIXTA"

    # --- TRIBUNAL DE SALUD ---
    n_sal = sum([pio is not None and pio >= 7, alt is not None and alt >= 3, m is not None and m <= -1.78])
    salud = "DÉBIL" if ((alt is not None and alt < 1.81) or n_sal <= 1) else ("EXCELENTE" if n_sal == 3 else "MIXTA")

    # --- CATEGORÍA FINAL ---
    core = [roic, roic5, roe, gm, epsg, revg, fcfni, bb, evebit, fcfy, fv, pio]
    insuf = sum(1 for x in core if x is None) >= 5
    trampa = (cal == "DÉBIL" and precio in ("MUY BARATA", "BARATA"))
    if es_financiera:
        categoria = "OMITIDA POR MÉTODO"
    elif insuf:
        categoria = "DESCARTADA"
    elif cal == "EXCELENTE" and salud != "DÉBIL" and precio in ("MUY BARATA", "BARATA"):
        categoria = "DEEP DIVE"
    elif cal == "EXCELENTE" and salud != "DÉBIL":
        categoria = "WATCHLIST"
    elif cal in ("EXCELENTE", "BUENA"):
        categoria = "NEUTRAL"
    else:
        categoria = "DESCARTADA"

    alertas = []
    if not es_financiera:
        if trampa:
            alertas.append("POSIBLE TRAMPA DE VALOR")
        if cal == "EXCELENTE" and ((upside is not None and upside >= 0.40) or n_val >= 3):
            alertas.append("¿DEMASIADO BARATA?")
        if m is not None and m > -1.78:
            alertas.append("M-SCORE")
        if cal == "EXCELENTE" and pio is not None and pio <= 3:
            alertas.append("MEJORA DÉBIL")
        if alt is not None and alt < 1.81:
            alertas.append("ALTMAN ZONA DE RIESGO")
        if cal == "EXCELENTE" and salud == "DÉBIL":
            alertas.append("EXCELENTE PERO SALUD DÉBIL")
        if insuf:
            alertas.append("DATOS INSUFICIENTES")

    # --- TARJETAS POR INDICADOR (dato + estado + frase sencilla) ---
    def _rango(v, alto, bajo):
        return "ok" if v >= alto else ("bad" if v < bajo else "warn")

    f_calidad = []
    if roic is not None:
        e = _rango(roic, 20, 10)
        fr = {"ok": "GANA MUCHO POR CADA PESO QUE INVIERTE", "warn": "RENTABILIDAD ACEPTABLE, SIN SER EXCEPCIONAL",
              "bad": "GANA POCO POR LO QUE INVIERTE"}[e]
    else:
        e, fr = "nd", ""
    f_calidad.append(_fila_indicador("roic", "ROIC ACTUAL", roic, f"{roic:.1f}%" if roic is not None else "", e, fr))
    if roic5 is not None:
        e = _rango(roic5, 20, 10)
        fr = {"ok": "RENTABLE DE FORMA CONSISTENTE EN 5 AÑOS", "warn": "RENTABILIDAD MEDIA EN LOS ÚLTIMOS 5 AÑOS",
              "bad": "HISTÓRICAMENTE GANA POCO POR LO QUE INVIERTE"}[e]
    else:
        e, fr = "nd", ""
    f_calidad.append(_fila_indicador("roic_5y", "ROIC PROMEDIO 5 AÑOS", roic5, f"{roic5:.1f}%" if roic5 is not None else "", e, fr))
    if roe is not None:
        if roe >= 15 and not lev:
            e, fr = "ok", "BUENA GANANCIA PARA LOS ACCIONISTAS"
        elif roe >= 15 and lev:
            e, fr = "warn", "ROE ALTO, PERO PUEDE ESTAR INFLADO POR DEUDA"
        elif roe >= 10:
            e, fr = "warn", "GANANCIA MODERADA PARA LOS ACCIONISTAS"
        else:
            e, fr = "bad", "GANANCIA BAJA PARA LOS ACCIONISTAS"
    else:
        e, fr = "nd", ""
    f_calidad.append(_fila_indicador("roe", "ROE", roe, f"{roe:.1f}%" if roe is not None else "", e, fr))
    if dc is not None:
        e, fr = ("ok", "DEUDA BAJO CONTROL") if dc <= 60 else ("bad", "DEPENDE MUCHO DE PRÉSTAMOS")
    else:
        e, fr = "nd", ""
    f_calidad.append(_fila_indicador("deuda_capital", "DEUDA / CAPITAL TOTAL", dc, f"{dc:.1f}%" if dc is not None else "", e, fr))
    if gm is not None:
        e, fr = ("ok", "VENDE CON MARGEN AMPLIO: DIFÍCIL DE COPIAR") if gm >= 40 else ("warn", "MARGEN AJUSTADO: COMPITE MÁS POR PRECIO")
    else:
        e, fr = "nd", ""
    f_calidad.append(_fila_indicador("gross_margin", "MARGEN BRUTO", gm, f"{gm:.1f}%" if gm is not None else "", e, fr))
    if fcfni is not None:
        e, fr = ("ok", "SUS GANANCIAS SON EFECTIVO REAL") if fcfni >= 0.8 else ("bad", "PARTE DE SUS GANANCIAS NO LLEGA COMO EFECTIVO")
    else:
        e, fr = "nd", ""
    f_calidad.append(_fila_indicador("fcf_net_income", "FCF / UTILIDAD NETA", fcfni, f"{fcfni:.2f}" if fcfni is not None else "", e, fr))
    if epsg is not None:
        e, fr = ("ok", "GANA MÁS POR ACCIÓN QUE HACE 5 AÑOS") if epsg > 0 else (("bad", "GANA MENOS POR ACCIÓN QUE HACE 5 AÑOS") if epsg < 0 else ("warn", "GANANCIA POR ACCIÓN ESTANCADA"))
    else:
        e, fr = "nd", ""
    f_calidad.append(_fila_indicador("eps_growth_5y", "CRECIMIENTO EPS 5 AÑOS", epsg, f"{epsg:+.1f}%" if epsg is not None else "", e, fr))
    if revg is not None:
        e, fr = ("ok", "VENDE MÁS QUE HACE 5 AÑOS") if revg > 0 else (("bad", "VENDE MENOS QUE HACE 5 AÑOS") if revg < 0 else ("warn", "VENTAS ESTANCADAS"))
    else:
        e, fr = "nd", ""
    f_calidad.append(_fila_indicador("rev_cagr_5y", "CRECIMIENTO INGRESOS 5 AÑOS", revg, f"{revg:+.1f}%" if revg is not None else "", e, fr))
    if bb is not None:
        if bb >= 0:
            e, fr = "ok", "RECOMPRA ACCIONES: TU PARTE CRECE"
        elif bb >= -2:
            e, fr = "warn", "EMITE POCAS ACCIONES NUEVAS"
        else:
            e, fr = "bad", "EMITE MUCHAS ACCIONES: TU PARTE SE DILUYE"
    else:
        e, fr = "nd", ""
    f_calidad.append(_fila_indicador("buyback_yield", "BUYBACK YIELD", bb, f"{bb:+.1f}%" if bb is not None else "", e, fr))

    f_salud = []
    if pio is not None:
        e = "ok" if pio >= 7 else ("bad" if pio <= 3 else "warn")
        fr = {"ok": "EL NEGOCIO ESTÁ MEJORANDO", "warn": "MEJORA A MEDIAS", "bad": "EL NEGOCIO SE ESTÁ DETERIORANDO"}[e]
    else:
        e, fr = "nd", ""
    f_salud.append(_fila_indicador("piotroski", "PIOTROSKI SCORE", pio, f"{pio:.0f} / 9" if pio is not None else "", e, fr))
    if alt is not None:
        e = "ok" if alt >= 3 else ("bad" if alt < 1.81 else "warn")
        fr = {"ok": "LEJOS DE RIESGO DE QUIEBRA", "warn": "ZONA GRIS: VIGILAR SU SALUD", "bad": "ZONA DE PELIGRO: RIESGO FINANCIERO ALTO"}[e]
    else:
        e, fr = "nd", ""
    f_salud.append(_fila_indicador("altman_z", "ALTMAN Z-SCORE", alt, f"{alt:.2f}" if alt is not None else "", e, fr))
    if m is not None:
        e, fr = ("ok", "SIN SEÑALES DE MAQUILLAJE CONTABLE") if m <= -1.78 else ("bad", "POSIBLE MAQUILLAJE CONTABLE: REVISAR")
    else:
        e, fr = "nd", ""
    f_salud.append(_fila_indicador("beneish_m", "BENEISH M-SCORE", m, f"{m:.2f}" if m is not None else "", e, fr))

    f_precio = []
    if upside is not None:
        if upside >= 0.20:
            e, fr = "ok", "COTIZA MUY POR DEBAJO DE SU VALOR ESTIMADO"
        elif upside <= -0.10:
            e, fr = "bad", "COTIZA POR ENCIMA DE SU VALOR ESTIMADO"
        else:
            e, fr = "warn", "PRECIO CERCANO A SU VALOR ESTIMADO"
        fr += f" (VALOR {fv:,.2f} VS PRECIO {price:,.2f})"
    else:
        e, fr = "nd", ""
    f_precio.append(_fila_indicador("upside", "UPSIDE VS FAIR VALUE", upside, f"{upside * 100:+.1f}%" if upside is not None else "", e, fr))
    if evebit is not None:
        if 0 < evebit <= 10:
            e, fr = "ok", "BARATA FRENTE A LO QUE GANA"
        elif evebit < 0:
            e, fr = "bad", "PIERDE DINERO EN SU OPERACIÓN"
        elif evebit >= 20:
            e, fr = "bad", "CARA FRENTE A LO QUE GANA"
        else:
            e, fr = "warn", "PRECIO RAZONABLE FRENTE A LO QUE GANA"
    else:
        e, fr = "nd", ""
    f_precio.append(_fila_indicador("ev_ebit", "EV / EBIT", evebit, f"{evebit:.1f}x" if evebit is not None else "", e, fr))
    if fcfy is not None:
        if fcfy >= 4:
            e, fr = "ok", "GENERA MUCHO EFECTIVO PARA LO QUE CUESTA"
        elif fcfy <= 2:
            e, fr = "bad", "CARA: GENERA POCO EFECTIVO PARA LO QUE CUESTA"
        else:
            e, fr = "warn", "EFECTIVO RAZONABLE PARA LO QUE CUESTA"
    else:
        e, fr = "nd", ""
    f_precio.append(_fila_indicador("fcf_yield", "FCF YIELD", fcfy, f"{fcfy:.1f}%" if fcfy is not None else "", e, fr))

    return {
        "categoria": categoria,
        "puntaje": n_cal + n_val + n_sal,
        "alertas": alertas,
        "tribunales": {
            "CALIDAD": {"veredicto": cal, "detalle": f"{n_cal}/3 PRUEBAS", "filas": f_calidad},
            "SALUD": {"veredicto": salud, "detalle": f"{n_sal}/3 SEÑALES", "filas": f_salud},
            "PRECIO": {"veredicto": precio, "detalle": f"{n_val} A FAVOR · {v_c} EN CONTRA", "filas": f_precio},
        },
    }


def _html_seguro(texto):
    """Evita que el texto rompa el HTML y que el signo $ se interprete como fórmula."""
    return (str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("$", "&#36;"))


def _icono_info(definicion):
    return f'<span class="tm-info" title="{_html_seguro(definicion)}">i</span>'


def mostrar_veredicto_motor(res, aprendizaje=False):
    """Dibuja el veredicto: tarjeta de categoría, 3 tribunales y una tarjeta por indicador."""
    st.markdown(
        "<style>"
        ".tm-card{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:20px;margin-bottom:14px;"
        "display:flex;flex-direction:column;justify-content:space-between;text-transform:uppercase;}"
        ".tm-ind{min-height:175px;}"
        ".tm-tit{font-size:12px;letter-spacing:.06em;color:#8b949e;font-weight:600;}"
        ".tm-val{font-size:28px;font-weight:700;color:#ffffff;margin-top:6px;line-height:1.1;}"
        ".tm-frase{font-size:12px;color:#c9d1d9;margin-top:6px;line-height:1.35;}"
        ".tm-def{font-size:11px;color:#8b949e;margin-top:10px;line-height:1.45;border-top:1px solid #30363d;padding-top:8px;}"
        ".tm-pie{display:flex;justify-content:space-between;align-items:center;margin-top:14px;gap:8px;flex-wrap:wrap;}"
        ".tm-badge{font-size:11px;font-weight:700;padding:4px 12px;border-radius:999px;display:inline-block;margin:2px 4px 2px 0;}"
        ".tm-info{width:20px;height:20px;border-radius:50%;border:1.5px solid #8b949e;color:#8b949e;font-size:12px;"
        "font-weight:700;display:inline-flex;align-items:center;justify-content:center;cursor:help;"
        "font-family:Georgia,serif;text-transform:none;flex-shrink:0;}"
        "</style>",
        unsafe_allow_html=True,
    )

    # --- Tarjeta principal: categoría ---
    color, frase_cat, def_cat = CATEGORIAS_INFO[res["categoria"]]
    chips = ""
    for a in res["alertas"]:
        chips += (f'<span class="tm-badge" style="color:#d29922;background:rgba(210,153,34,.15)" '
                  f'title="{_html_seguro(ALERTAS_INFO.get(a, ""))}">ALERTA: {_html_seguro(a)}</span>')
    if not chips:
        chips = '<span class="tm-badge" style="color:#3fb950;background:rgba(63,185,80,.15)">SIN ALERTAS</span>'
    extra = ""
    if aprendizaje:
        extra = f'<div class="tm-def">{_html_seguro(def_cat)}</div>'
        for a in res["alertas"]:
            extra += f'<div class="tm-def"><b>{_html_seguro(a)}:</b> {_html_seguro(ALERTAS_INFO.get(a, ""))}</div>'
    st.markdown(
        f'<div class="tm-card" style="border-color:{color}">'
        f'<div class="tm-tit">CATEGORÍA DEL MOTOR · PUNTAJE {res["puntaje"]}/9</div>'
        f'<div class="tm-val" style="color:{color}">{_html_seguro(res["categoria"])}</div>'
        f'<div class="tm-frase">{_html_seguro(frase_cat)}</div>{extra}'
        f'<div class="tm-pie"><div>{chips}</div>{_icono_info(def_cat)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # --- Los 3 tribunales ---
    for clave in ("CALIDAD", "SALUD", "PRECIO"):
        trib = res["tribunales"][clave]
        info = TRIBUNALES_INFO[clave]
        frase_t, estado_t = info["frases"][trib["veredicto"]]
        txt_b, col_b, fondo_b = ESTADOS_INFO[estado_t]
        def_t = f'<div class="tm-def">{_html_seguro(info["definicion"])}</div>' if aprendizaje else ""
        st.markdown(
            f'<div class="tm-card">'
            f'<div class="tm-tit">{info["titulo"]} · {_html_seguro(trib["detalle"])}</div>'
            f'<div class="tm-val" style="font-size:22px">{_html_seguro(trib["veredicto"])}</div>'
            f'<div class="tm-frase">{_html_seguro(frase_t)}</div>{def_t}'
            f'<div class="tm-pie"><span class="tm-badge" style="color:{col_b};background:{fondo_b}">{txt_b}</span>'
            f'{_icono_info(info["definicion"])}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        filas = trib["filas"]
        for inicio in range(0, len(filas), 3):
            cols = st.columns(3)
            for c, fila in zip(cols, filas[inicio:inicio + 3]):
                txt_e, col_e, fondo_e = ESTADOS_INFO[fila["estado"]]
                definicion = DEFINICIONES_MOTOR.get(fila["key"], "")
                def_i = f'<div class="tm-def">{_html_seguro(definicion)}</div>' if aprendizaje else ""
                with c:
                    st.markdown(
                        f'<div class="tm-card tm-ind">'
                        f'<div><div class="tm-tit">{_html_seguro(fila["nombre"])}</div>'
                        f'<div class="tm-val">{_html_seguro(fila["valor"])}</div>'
                        f'<div class="tm-frase">{_html_seguro(fila["frase"])}</div>{def_i}</div>'
                        f'<div class="tm-pie"><span class="tm-badge" style="color:{col_e};background:{fondo_e}">{txt_e}</span>'
                        f'{_icono_info(definicion)}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    st.caption("HERRAMIENTA EDUCATIVA: NINGUNA CATEGORÍA ES UNA ORDEN DE COMPRA O VENTA. LOS NÚMEROS SON LA MITAD DE LA TAREA; LA OTRA MITAD ES EL ANÁLISIS CUALITATIVO.")


def _resumen_veredicto_texto(res):
    """Texto compacto del veredicto del motor para incluirlo en los prompts de la IA."""
    if res is None:
        return "VEREDICTO DEL MOTOR DE REGLAS FIJAS: sin datos suficientes para calcularlo."
    lineas = [
        "VEREDICTO DEL MOTOR DE REGLAS FIJAS (calculado sin IA con el método de 3 tribunales: calidad -> salud -> precio):",
        f"- Categoría: {res['categoria']} | Puntaje: {res['puntaje']}/9",
        f"- Alertas: {', '.join(res['alertas']) if res['alertas'] else 'ninguna'}",
    ]
    for clave in ("CALIDAD", "SALUD", "PRECIO"):
        trib = res["tribunales"][clave]
        lineas.append(f"- Tribunal de {clave.lower()}: {trib['veredicto']} ({trib['detalle']})")
        for fila in trib["filas"]:
            estado = ESTADOS_INFO[fila["estado"]][0]
            lineas.append(f"    * {fila['nombre']}: {fila['valor']} [{estado}] {fila['frase']}")
    lineas.append("Significado de categorías: DEEP DIVE = buen negocio, sano y a buen precio (investigar a fondo, no es "
                  "orden de compra); WATCHLIST = buen negocio y sano pero hoy no barato; NEUTRAL = ni excelente ni mala; "
                  "DESCARTADA = no pasa los filtros hoy (no es pronóstico); OMITIDA = banco/aseguradora/utility.")
    return "\n".join(lineas)


def _limpiar_formulario_lp():
    """Se ejecuta ANTES de dibujar la página (on_click), por eso sí puede vaciar los campos sin error."""
    for key, _ in METRICAS_LP:
        st.session_state[f"lp_input_{key}"] = ""
        st.session_state[f"lp_chk_{key}"] = False
    for key, _, _ in METRICAS_MOTOR:
        st.session_state[f"lp_motor_{key}"] = ""
    st.session_state["lp_motor_financiera"] = False
    st.session_state["lp_ticker_actual"] = ""


def mostrar_largo_plazo():
    st.title("💼 Análisis Fundamental - Inversión a Largo Plazo")
    st.caption("Captura los indicadores fundamentales de una empresa, guárdalos, compara contra otras y pide un análisis con IA (incluyendo contexto cualitativo de noticias).")

    # --- Estado de sesión ---
    # --- Estado de sesión ---
    if "lp_empresas_guardadas" not in st.session_state:
        st.session_state["lp_empresas_guardadas"] = {}

    # ============================================================
    # DESCUBRIR OPORTUNIDADES DE INVERSIÓN (búsqueda cualitativa)
    # ============================================================
    with st.expander("🔎 Descubrir Oportunidades de Inversión", expanded=False):
        st.caption("Busca empresas interesantes en cualquier país o sector, con base principalmente en investigación cualitativa de mercado (tendencias, catalizadores, posicionamiento competitivo).")

        col_op1, col_op2 = st.columns(2)
        with col_op1:
            tema_oportunidades = st.text_input(
                "Sector, tema o región de interés (opcional)",
                key="lp_tema_oportunidades",
                placeholder="Ej: inteligencia artificial, energía limpia, Latinoamérica, small caps...",
            )
        with col_op2:
            num_oportunidades = st.slider("Cuántas oportunidades quieres", min_value=3, max_value=10, value=5, key="lp_num_oportunidades")

        SECTORES_DISPONIBLES = [
            "Financiero", "Tecnología", "Servicios", "B2B", "Manufactura",
            "Salud y Farmacéutica", "Retail", "Logística", "Turismo",
            "Energía", "Bienes Raíces", "Consumo Básico", "Consumo Discrecional",
            "Materias Primas", "Telecomunicaciones", "Educación",
            "Agroindustria", "Entretenimiento y Medios",
        ]
        sectores_seleccionados = st.multiselect(
            "O selecciona uno o varios sectores",
            options=SECTORES_DISPONIBLES,
            key="lp_sectores_seleccionados",
        )

        if st.button("🚀 Buscar Oportunidades"):
            if not model:
                st.error("IA no configurada.")
            else:
                partes_filtro = []
                if sectores_seleccionados:
                    partes_filtro.append("sectores: " + ", ".join(sectores_seleccionados))
                if tema_oportunidades.strip():
                    partes_filtro.append(tema_oportunidades.strip())

                if partes_filtro:
                    filtro_txt = " enfocándote específicamente en: " + "; ".join(partes_filtro) + "."
                else:
                    filtro_txt = " sin restricción de sector, país o tamaño de empresa."

                prompt_oportunidades = f"""
                Actúa como un analista de inversión fundamental especializado en identificar oportunidades
                de inversión a largo plazo. Usa Google Search para investigar tendencias de mercado actuales,
                noticias recientes y contexto cualitativo real (no inventes datos).

                TAREA: Identifica {num_oportunidades} empresas que hoy en día se vean como oportunidades
                interesantes de inversión a largo plazo, pueden ser de cualquier país del mundo,{filtro_txt}

                Básate PRINCIPALMENTE en un análisis cualitativo de mercado, considerando cosas como:
                - Tendencias estructurales o de consumo que las favorecen
                - Cambios en la industria, disrupción o innovación relevante
                - Posicionamiento competitivo y ventajas frente a rivales
                - Catalizadores recientes (noticias, lanzamientos, expansión, regulación favorable)
                - Riesgos relevantes a tener en cuenta

                Para cada empresa da:
                1. Nombre y ticker (si cotiza en bolsa)
                2. País / región y sector
                3. Un resumen de 3-5 líneas explicando POR QUÉ se ve interesante ahora mismo (el contexto
                   cualitativo, no números financieros a detalle)
                4. Un riesgo o duda relevante a vigilar

                Aclara al inicio que esto es un punto de partida para investigar más a fondo, no una
                recomendación de compra. Responde en español, en formato de lista clara por empresa.
                """
                with st.spinner("Buscando oportunidades de inversión..."):
                    try:
                        resultado_oportunidades = model.generate_content(prompt_oportunidades).text
                        st.markdown(resultado_oportunidades)
                    except Exception as e:
                        if "429" in str(e) or "quota" in str(e).lower():
                            st.warning("⚠️ Cuota de búsqueda excedida. Intenta de nuevo en unos minutos.")
                        else:
                            st.error(f"Error buscando oportunidades: {e}")

        st.caption("💡 Cuando encuentres una que te interese, escribe su ticker abajo en 'Ticker o Nombre de la Empresa' y llena sus indicadores para el análisis completo.")

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
                # Acepta números con o sin % pegado, separados por espacio o tabulador
                valores = _parsear_valores_porcentaje(valor_input)
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

    # --- INDICADORES DEL MOTOR DE TRIBUNALES (NUEVO) ---
    st.markdown("---")
    st.markdown("#### :material/balance: INDICADORES DEL MOTOR DE TRIBUNALES")
    st.caption("UN SOLO DATO POR INDICADOR (EL VALOR ACTUAL). LOS ENCUENTRAS EN INVESTINGPRO, MORNINGSTAR, GURUFOCUS O STOCKANALYSIS. SI FALTA ALGUNO, EL MOTOR LO MARCA COMO SIN DATO. PASA EL MOUSE POR EL ÍCONO DE AYUDA DE CADA CAMPO PARA VER QUÉ SIGNIFICA.")
    with st.container(border=True):
        cols_motor = st.columns(3)
        for idx, (key, label, ejemplo) in enumerate(METRICAS_MOTOR):
            with cols_motor[idx % 3]:
                valor_m = st.text_input(label, key=f"lp_motor_{key}", placeholder=ejemplo, help=DEFINICIONES_MOTOR.get(key))
            dato_m = None
            if valor_m.strip():
                try:
                    dato_m = _parsear_dato_unico(valor_m)
                except ValueError:
                    st.error(f"REVISA EL FORMATO DE '{label}': DEBE SER UN SOLO NÚMERO. (TEXTO RECIBIDO: '{valor_m}')")
            datos_actuales[key] = {
                "label": label,
                "valores": [dato_m] if dato_m is not None else [],
                "promedio": dato_m,
                "es_promedio_5y": False,
                "dato_unico": True,
            }
        es_financiera = st.checkbox(
            "ES BANCO, ASEGURADORA O UTILITY (EL MÉTODO NO APLICA)",
            key="lp_motor_financiera",
            help="EN BANCOS Y ASEGURADORAS LA DEUDA ES SU MATERIA PRIMA Y EN LAS UTILITIES LA GANANCIA ESTÁ REGULADA. EL MOTOR LAS MARCA COMO OMITIDAS PARA NO CALIFICARLAS MAL. VISA, MASTERCARD Y PAYPAL NO CUENTAN COMO BANCOS.",
        )

    # Si no se capturó el precio, se toma de yfinance con el ticker
    if datos_actuales["precio_actual"]["promedio"] is None and ticker_lp.strip():
        precio_auto = _precio_yfinance(ticker_lp.strip().upper())
        if precio_auto is not None:
            datos_actuales["precio_actual"]["valores"] = [precio_auto]
            datos_actuales["precio_actual"]["promedio"] = precio_auto
            st.caption(f"PRECIO ACTUAL TOMADO DE YFINANCE: {precio_auto:,.2f} USD")

    # Si no se capturó el ROIC de 5 años, se calcula con tu fila de ROIC (los 5 datos más recientes)
    info_roic_form = datos_actuales.get("roic", {})
    if datos_actuales["roic_5y"]["promedio"] is None and info_roic_form.get("valores"):
        roic5_auto, origen_roic5 = None, ""
        if info_roic_form.get("es_promedio_5y"):
            roic5_auto = info_roic_form["promedio"]
            origen_roic5 = "TU DATO DE ROIC MARCADO COMO 5Y"
        elif len(info_roic_form["valores"]) >= 2:
            ultimos_roic = info_roic_form["valores"][:5]
            roic5_auto = sum(ultimos_roic) / len(ultimos_roic)
            origen_roic5 = f"LOS {len(ultimos_roic)} AÑOS MÁS RECIENTES DE TU FILA DE ROIC"
        if roic5_auto is not None:
            datos_actuales["roic_5y"]["valores"] = [roic5_auto]
            datos_actuales["roic_5y"]["promedio"] = roic5_auto
            st.caption(f"ROIC PROMEDIO 5 AÑOS CALCULADO CON {origen_roic5}: {roic5_auto:.1f}%")

    st.markdown("---")
    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        guardar = st.button("💾 Guardar Empresa", use_container_width=True)
    with col_g2:
        nueva = st.button("LIMPIAR FORMULARIO", icon=":material/restart_alt:", use_container_width=True, on_click=_limpiar_formulario_lp)
    with col_g3:
        borrar_todo = st.button("🗑️ Borrar Comparaciones", use_container_width=True)

    if guardar:
        if not ticker_lp.strip():
            st.error("Escribe un ticker o nombre para identificar la empresa antes de guardar.")
        else:
            st.session_state["lp_empresas_guardadas"][ticker_lp.strip().upper()] = datos_actuales
            st.session_state.setdefault("lp_financieras", {})[ticker_lp.strip().upper()] = es_financiera
            st.success(f"✅ Datos de {ticker_lp.strip().upper()} guardados. Puedes limpiar el formulario y capturar otra empresa para comparar.")


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
        for emp, datos in empresas_guardadas.items():
            res_emp = evaluar_tribunales(datos, st.session_state.get("lp_financieras", {}).get(emp, False))
            tabla[emp] = {"CATEGORÍA DEL MOTOR": res_emp["categoria"] if res_emp else "SIN DATOS", **tabla[emp]}
        df_comparacion = pd.DataFrame(tabla).astype(str)
        st.dataframe(df_comparacion, use_container_width=True)

    # --- VEREDICTO DEL MOTOR DE TRIBUNALES (NUEVO, SIN IA) ---
    st.markdown("---")
    col_vt, col_va = st.columns([3, 1])
    with col_vt:
        st.markdown("### :material/gavel: VEREDICTO DEL MOTOR")
        st.caption("CALIFICACIÓN AUTOMÁTICA CON REGLAS FIJAS: MISMOS DATOS, MISMO RESULTADO. NO USA IA NI CONSUME TOKENS.")
    with col_va:
        modo_aprendizaje = st.toggle(
            "MODO APRENDIZAJE",
            key="lp_modo_aprendizaje",
            help="MUESTRA LA EXPLICACIÓN COMPLETA DE CADA INDICADOR DEBAJO DE SU TARJETA.",
        )
    resultado_motor = evaluar_tribunales(datos_actuales, es_financiera)
    if resultado_motor is None:
        st.caption("LLENA LOS INDICADORES PARA VER EL VEREDICTO.")
    else:
        mostrar_veredicto_motor(resultado_motor, modo_aprendizaje)
    veredicto_txt = _resumen_veredicto_texto(resultado_motor)

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

                {veredicto_txt}

                TAREA:
                1. Evalúa la rentabilidad (márgenes bruto, operativo, neto, EBIT y EBITDA; ROA, ROE, ROIC).
                2. Evalúa la salud financiera (liquidez: Quick/Current Ratio; apalancamiento: Debt to Equity).
                3. Evalúa la valuación (PE, PS, PEG, Price to Book, PE Cash Flow).
                4. Evalúa la generación y calidad del flujo de caja libre (Free Cash Flow).
                5. IMPORTANTE: evalúa si los márgenes y demás indicadores son CONSISTENTES en el tiempo o
                   presentan alta volatilidad/tendencia negativa. Usa los datos por año que vienen entre paréntesis
                   junto a cada indicador (no solo el promedio) para juzgar esta consistencia.
                6. Explica en lenguaje muy sencillo el VEREDICTO DEL MOTOR: qué significa su categoría, qué dicen
                   Piotroski, Altman Z, Beneish M, EV/EBIT, FCF Yield y el upside contra el Fair Value, y qué
                   significan sus alertas (si las hay). Si tu conclusión difiere del motor, explica claramente por qué;
                   no lo contradigas sin dar razones basadas en los datos.

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
                    # --- PROMPT 2: ANÁLISIS CUALITATIVO (5 pilares) ---
                    prompt_cual = f"""
                Realiza un análisis cualitativo profundo de {nombre_emp} usando Google Search para investigar
                noticias, reportes financieros, entrevistas, foros de inversión y su información pública más
                reciente. Evalúa los siguientes 5 pilares con evidencia real (no supuestos):

                DATOS FINANCIEROS DISPONIBLES DE {nombre_emp} (para el pilar 5):
                {resumen}

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

                {veredicto_txt}

                5. SEÑALES DE ALERTA (cruza los datos financieros de arriba con lo que encuentres investigando)
                - Si el VEREDICTO DEL MOTOR trae alertas (M-Score, Altman en zona de riesgo, posible trampa de valor,
                  mejora débil, ¿demasiado barata?), investiga si las noticias o reportes las confirman o las explican.
                - ROE muy alto + Debt to Equity alto (>2-3): ¿el ROE puede estar inflado por deuda?
                - PE Cash Flow Ratio alto (>20) + Free Cash Flow/Net Income bajo (<1) o cayendo: ¿ganancias
                  contables sin respaldo de efectivo real?
                - Gross Margin alto (>40%) pero Operating Margin bajo (<5%): ¿los costos operativos se están
                  comiendo la rentabilidad?
                - Current Ratio > 1 pero Quick Ratio < 1: ¿liquidez atrapada en inventarios?
                - PS Ratio alto (>10) con EPS negativo: ¿se está pagando por expectativas, no por resultados?
                - Price to Book < 1 sin razón clara + ROA bajo + Debt to Equity alto: ¿el mercado desconfía del
                  valor contable reportado?
                - ROIC consistentemente bajo (<8%): ¿posible destrucción de valor?
                - EPS creciendo mientras Free Cash Flow/Share o Free Cash Flow/Net Income cae: ¿posible
                  contabilidad agresiva?
                - Además, busca en las noticias/investigación si hay señales cualitativas de alerta: cambios de
                  auditor, restatements de resultados, ventas masivas de acciones por directivos (insider
                  selling), reportes de vendedores en corto (short seller reports), investigaciones regulatorias,
                  recortes de dividendo o de guía financiera (guidance cuts).
                Evalúa SOLO lo que puedas verificar con los datos e información disponible, no inventes cifras.

                FORMATO DE RESPUESTA: Para cada uno de los 5 pilares, da un resumen breve con evidencia
                encontrada y ciérralo con una etiqueta: 🟢 Fuerte / 🟡 Moderado / 🔴 Débil. Para el pilar 5,
                si detectas alguna señal, indícalo claramente; si no detectas ninguna, dilo también.

                Termina con una sección '🌐 CONCLUSIÓN CUALITATIVA' resumiendo los 5 pilares.
                Después, en su propia línea y SIN NADA MÁS en esa línea, escribe exactamente:
                CALIFICACIÓN_CUALITATIVA: X/10
                (reemplaza X por tu calificación del 1 al 10 sobre la calidad cualitativa del negocio, considerando
                también las señales de alerta detectadas)
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

                    {veredicto_txt}

                    TAREA: Da una CONCLUSIÓN GENERAL en español, sencilla y directa, combinando ambos análisis:
                    indica si {nombre_emp} es una buena opción de inversión a largo plazo, qué pesa más
                    (lo cuantitativo o lo cualitativo) y por qué. No repitas todo el detalle, sintetiza lo esencial.
                    Menciona en una frase la categoría del motor y si el análisis cualitativo la confirma o la pone en duda.
                    Recuerda que ninguna categoría es una orden de compra: DEEP DIVE significa investigar a fondo.

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
            bloques = [
                _resumen_metricas_texto(emp, datos) + "\n" + _resumen_veredicto_texto(
                    evaluar_tribunales(datos, st.session_state.get("lp_financieras", {}).get(emp, False)))
                for emp, datos in empresas_guardadas.items()
            ]
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
            Cada empresa trae su VEREDICTO DEL MOTOR (categoría, tribunales y alertas): úsalo en la comparación y
            explica en lenguaje sencillo qué significan sus indicadores (Piotroski, Altman Z, Beneish M, EV/EBIT,
            FCF Yield, upside). Si tu veredicto final difiere del motor, explica por qué.

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

            {veredicto_txt}

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
