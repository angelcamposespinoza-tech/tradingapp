# --- MENÚ DE NAVEGACIÓN PRINCIPAL ---
st.sidebar.markdown("---")
st.sidebar.header("🧭 Navegación")
apartado_seleccionado = st.sidebar.selectbox(
    "Selecciona el Módulo",
    ("📈 Scanner & Trading Opciones", "🏦 Inversión a Largo Plazo")
)

# =====================================================================
# 📊 APARTADO 1: SCANNER & TRADING DE OPCIONES (Todo tu código actual)
# =====================================================================
if apartado_seleccionado == "📈 Scanner & Trading Opciones":
    
    st.title("🚀 SUPERIOR SCANNER")

    # 2. MONITOR DE SEÑALES ORGANIZADO POR SECTORES
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
            if sec in sectores and tk not in sectores[sec]:
                sectores[sec].append(tk)

    tabs = st.tabs(list(sectores.keys()))

    for i, (nombre_sector, lista_tickers) in enumerate(sectores.items()):
        with tabs[i]:
            datos_sector = escanear_mercado(lista_tickers, v_intervalo, v_periodo)
            cols = st.columns(5)
            for j, res in enumerate(datos_sector):
                with cols[j % 5]:
                    st.metric(res['T'], f"${res['P']:,.2f}", f"RSI: {res['R']:.1f}")
                    
                    if "CALL" in res['S']: 
                        st.success(res['S'])
                    elif "PUT" in res['S']: 
                        st.error(res['S'])
                    else: 
                        st.info(res['S'])
                    
                    if res.get('MP'): st.warning(f"✅ Conf: {res['MP']}")
                    if res.get('MA'): st.info(f"⏳ Form: {res['MA']}")
                    
                    with st.expander("🔍 Ver Datos Técnicos"):
                        conclusion_final = generar_mini_conclusion(res)
                        st.markdown("**📋 Veredicto del Scanner:**")
                        st.info(conclusion_final)
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
        
        mitad = len(data) // 2
        datos_pasados = data.iloc[:mitad]
        techo_ref = datos_pasados['High'].max()
        piso_ref = datos_pasados['Low'].min()

        mov_sl = dinero_en_riesgo / 100
        mov_tp = meta_ganancia / 100
        if rsi_val < 50:
            sl, tp = precio_actual - mov_sl, precio_actual + mov_tp
        else:
            sl, tp = precio_actual + mov_sl, precio_actual - mov_tp

        ruptura_texto = ""
        if precio_actual > techo_ref:
            ruptura_texto = "🚀 ¡TECHO ROTO! (Posible Rally)"
        elif precio_actual < piso_ref:
            ruptura_texto = "📉 ¡PISO ROTO! (Caída Libre)"

        col_graf, col_info = st.columns([4, 1])
        with col_graf:
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_width=[0.2, 0.7])
            fig.add_trace(go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Precio"), row=1, col=1)
            fig.add_trace(go.Scatter(x=data.index, y=calcular_ema(data['Close'], 200), name="EMA 200", line=dict(color='purple', width=3)), row=1, col=1)
            fig.add_trace(go.Scatter(x=data.index, y=calcular_ema(data['Close'], 20), name="EMA 20", line=dict(color='orange', width=1)), row=1, col=1)
            
            fig.add_hline(y=tp, line_dash="dot", line_color="green", annotation_text="TP", row=1, col=1)
            fig.add_hline(y=sl, line_dash="dot", line_color="red", annotation_text="SL", row=1, col=1)
            
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
            if ruptura_texto: st.warning(ruptura_texto)
            
            st.write("---")
            st.subheader("🎯 Señal")
            st.write(f"Estado: **{etiqueta_ind}**")
            st.metric("RSI", f"{rsi_val:.1f}")
            
            st.write("---")
            st.markdown(f"**Referencia ({dias_vencimiento})**")
            st.metric("🏔️ Techo", f"${techo_ref:.2f}")
            st.metric("📉 Piso", f"${piso_ref:.2f}")
            
            vol_txt_ind, vol_tipo_ind = analizar_volumen(data)
            if vol_tipo_ind == "success": st.success(vol_txt_ind)
            elif vol_tipo_ind == "error": st.error(vol_txt_ind)
            else: st.warning(vol_txt_ind)
                
            texto_vol, color_vol = evaluar_volatilidad(data)
            if color_vol == "error": st.error(texto_vol)
            else: st.success(texto_vol)
                
            if precio_actual > ema200_actual: st.success("📈 ALCISTA")
            else: st.error("📉 BAJISTA")
                
            st.write("---")
            st.error(f"SL: ${sl:.2f}")
            st.success(f"TP: ${tp:.2f}")

        st.markdown("---")
        st.subheader(f"📰 Central de Noticias: {ticker_ind}")
        c1, c2, c3 = st.columns(3)
        c1.link_button(f"🌐 Yahoo Finance", f"https://finance.yahoo.com/quote/{ticker_ind}/news", use_container_width=True)
        c2.link_button(f"🔍 Google Finance", f"https://www.google.com/finance/quote/{ticker_ind}", use_container_width=True)
        c3.link_button(f"🧠 Seeking Alpha", f"https://seekingalpha.com/symbol/{ticker_ind}", use_container_width=True)

        st.markdown("---")
        with st.container():
            st.subheader("🤖 Pregúntame tus dudas")
            vol_info = "ALTA (Cuidado con el riesgo)" if color_vol == "error" else "Normal/Baja"
            duda = st.chat_input(f"Pregúntale a Gemini sobre {ticker_ind}...")
            
            if duda:
                contexto = f"INVESTIGACIÓN EN TIEMPO REAL... TAREA: Analiza los datos y responde a: {duda}"
                with st.chat_message("assistant"):
                    if model:
                        try:
                            response = model.generate_content(contexto)
                            st.write(response.text)
                        except Exception as e:
                            st.error(f"Error: {e}")

        # --- LABORATORIO ESTADÍSTICO (BACKTESTING) INTERNO ---
        st.markdown("---")
        st.header("📊 Laboratorio Estadístico (Backtesting de Datos)")
        archivo_datos = st.file_uploader("Sube tu archivo CSV histórico (Ej: Datos históricos NVDA.csv)", type=["csv"])

        if archivo_datos is not None:
            # Aquí va todo tu algoritmo matemático exacto del for i en range() de la Matriz de Micro-Contextos...
            # (Mantén el bloque intacto tal y como lo tenías para procesar el CSV)
            pass

# =====================================================================
# 🏦 APARTADO 2: INVERSIÓN A LARGO PLAZO (El nuevo bloque limpio)
# =====================================================================
elif apartado_seleccionado == "🏦 Inversión a Largo Plazo":
    st.title("🏦 PORTAFOLIO DE INVERSIÓN MACRO & LARGO PLAZO")
    st.markdown("Bienvenido al gestor patrimonial. Este apartado está aislado del ruido diario de las opciones.")
    
    # Aquí es donde construiremos tus nuevas herramientas fundamentales
    ticker_macro = st.text_input("Ingresa la Empresa para Análisis Macro (Ej: AAPL, MSFT, VO0)", value="VOO").upper()
    st.info("Próximamente: Análisis de múltiplos financieros, valuaciones DCF, dividendos acumulados y balance de portafolio.")
