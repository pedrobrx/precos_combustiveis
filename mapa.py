import json
import os
import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    layout="wide", page_title="Painel Inteligente - Combustíveis GO"
)

st.markdown(
    """
    <style>
        .block-container { 
            padding-top: 1.2rem; 
            padding-bottom: 0.5rem; 
            padding-left: 1.5rem;
            padding-right: 1.5rem;
        }
        .stPlotlyChart {
            width: 100% !important;
        }
        h1 {
            font-size: 1.5rem !important;
        }
        h3 {
            font-size: 1.15rem !important;
            margin-bottom: -0.5rem !important;
        }
    </style>
""",
    unsafe_allow_html=True,
)

st.title("🗺️ Painel Analítico de Combustíveis - Goiás")

def converter_para_float(serie):
    if serie.dtype in [np.float64, np.int64, float, int]:
        return serie.astype(float)
    
    s = serie.astype(str).str.strip().str.replace("R$", "", regex=False).str.strip()
    has_comma = s.str.contains(r',', na=False)
    
    s_clean = s.copy()
    s_clean[has_comma] = s_clean[has_comma].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    mask_multi_dot = ~has_comma & (s_clean.str.count(r'\.') > 1)
    s_clean[mask_multi_dot] = s_clean[mask_multi_dot].str.replace('.', '', regex=False)
    
    return pd.to_numeric(s_clean, errors='coerce')

@st.cache_data
def carregar_geojson_dict():
    arquivo_local = "geojs-52-mun.json"
    if os.path.exists(arquivo_local):
        with open(arquivo_local, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        import urllib.request
        url = "https://raw.githubusercontent.com/tbrugz/geodata-br/master/geojson/geojs-52-mun.json"
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode())

geojson_dict = carregar_geojson_dict()

col1, col2 = st.columns([1, 2.5])

with col1:
    tipo_dado = st.selectbox(
        "Tipo de Dado Analisado:",
        options=["precos", "volumes", "valor_total"],
        format_func=lambda x: {
            "precos": "💵 1. Preço de Combustíveis (R$)",
            "volumes": "📦 2. Volume Comercializado (L)",
            "valor_total": "💰 3. Valor Total / Faturamento (R$)"
        }[x],
        help="Selecione se o arquivo CSV carregado refere-se a preços, volumes ou valor total."
    )

    config_visual = {
        "precos": {
            "titulo_mapa": "MAPA DE CALOR - - - PREÇOS",
            "cor_accent": "#00a2e8",
            "colorscale": "RdYlGn_r",
            "escala_log": False
        },
        "volumes": {
            "titulo_mapa": "MAPA DE CALOR - - - VOLUME COMERCIALIZADO",
            "cor_accent": "#2ca02c",
            "colorscale": "RdYlGn_r",
            "escala_log": True  # Aplica suavização logarítmica para distribuir bem as cores
        },
        "valor_total": {
            "titulo_mapa": "MAPA DE CALOR - - - FATURAMENTO TOTAL",
            "cor_accent": "#ff7f0e",
            "colorscale": "RdYlGn_r",
            "escala_log": True  # Aplica suavização logarítmica para distribuir bem as cores
        }
    }

    cfg = config_visual[tipo_dado]

    uploaded_file = st.file_uploader(
        f"Faça o upload do CSV ({tipo_dado.replace('_', ' ').title()})", type=["csv"]
    )

df = None
df_filtrado = pd.DataFrame()
qtd_outliers = 0
pct_outliers = 0.0
combustivel_selecionado = ""
opcoes_combustiveis = {}
data_ini = ""
data_fim = ""
mostrar_nomes = False
metodo_outliers = "Nenhum (0%)"

if uploaded_file is not None:
    with col1:
        try:
            df = pd.read_csv(
                uploaded_file,
                sep="\t",
                decimal=",",
                dtype={"COD_IBGE": str},
                na_values=[""],
            )
        except Exception:
            uploaded_file.seek(0)
            df = pd.read_csv(
                uploaded_file,
                sep=None,
                engine="python",
                decimal=",",
                dtype={"COD_IBGE": str},
            )

        df.columns = df.columns.str.strip().str.replace('"', "")

        colunas_fixas = [
            "MUNICIPIO",
            "COD_IBGE",
            "DATA_INI",
            "DATA_FIM",
        ]
        colunas_combustiveis = [c for c in df.columns if c not in colunas_fixas]

        opcoes_combustiveis = {
            c: c.replace("_", " ").title() for c in colunas_combustiveis
        }

        if opcoes_combustiveis:
            chaves_opcoes = list(opcoes_combustiveis.keys())
            indice_padrao = 0
            
            for i, chave in enumerate(chaves_opcoes):
                chave_lower = chave.lower()
                if "gasolina" in chave_lower and ("comum" in chave_lower or chave_lower == "gasolina"):
                    indice_padrao = i
                    break

            combustivel_selecionado = st.selectbox(
                "Selecione o Combustível:",
                options=chaves_opcoes,
                format_func=lambda x: opcoes_combustiveis[x],
                index=indice_padrao,
            )

            index_outlier_default = 1 if tipo_dado == "precos" else 0
            if tipo_dado == "precos":
                metodo_outliers = st.selectbox(
                    "Filtro de Outliers:",
                    options=[
                        "Nenhum (0%)",
                        "Remover via IQR (Estatístico)",
                        "1% (Corte de 0.5% / 99.5%)",
                        "2% (Corte de 1% / 99%)",
                        "5% (Corte de 2.5% / 97.5%)",
                        "10% (Corte de 5% / 95%)",
                    ],
                    index=index_outlier_default,
                )
            else:
                metodo_outliers = index_outlier_default

            mostrar_nomes = st.checkbox("Exibir nomes dos municípios no mapa", value=False)

            data_ini = df["DATA_INI"].dropna().iloc[0] if "DATA_INI" in df else ""
            data_fim = df["DATA_FIM"].dropna().iloc[0] if "DATA_FIM" in df else ""

            st.caption(f"📅 **Período:** {data_ini} a {data_fim}")

            # Bloco informativo para interpretação da régua de escala logarítmica com fonte menor e cor personalizada
            if tipo_dado in ["volumes", "valor_total"]:
                with st.expander("Como ler a Régua de cores (Escala Logarítmica à direita) ℹ️"):
                    st.markdown(
                        """
                        <div style="font-size: 0.82rem; color: #00a2e8; line-height: 1.4;">
                        A leitura da régua de calor à direita apresentada na imagem funciona da seguinte forma:<br>
                        * Os números exibidos na régua (ex: 6, 8, 10, 12, 14, 16) não representam diretamente o valor em Reais ou Litros. Eles indicam patamares de grandeza matemática para equilibrar as cores no estado.<br><br>
                        
                        <b>Tradução prática:</b><br>
                        * <b>Verde (4 a 6):</b> Municípios com menor volume ou faturamento.<br>
                        * <b>Amarelo / Laranja (8 a 12):</b> Municípios de porte médio e intermediário.<br>
                        * <b>Vermelho (14):</b> Os maiores polos econômicos do estado.<br>
                        
                        <i>Dica:</i> Passe o cursor do mouse sobre qualquer município no mapa para ver o valor real exato!
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

            df_comb = df[df[combustivel_selecionado].notna()].copy()
            df_comb[combustivel_selecionado] = converter_para_float(df_comb[combustivel_selecionado])
            df_comb = df_comb[df_comb[combustivel_selecionado].notna()].copy()

            total_inicial = len(df_comb)

            if metodo_outliers == "Remover via IQR (Estatístico)" and total_inicial > 0:
                q1 = df_comb[combustivel_selecionado].quantile(0.25)
                q3 = df_comb[combustivel_selecionado].quantile(0.75)
                iqr = q3 - q1
                limite_inferior = q1 - 1.5 * iqr
                limite_superior = q3 + 1.5 * iqr
                df_filtrado = df_comb[
                    (df_comb[combustivel_selecionado] >= limite_inferior)
                    & (df_comb[combustivel_selecionado] <= limite_superior)
                ].copy()

            elif metodo_outliers == "1% (Corte de 0.5% / 99.5%)" and total_inicial > 0:
                lim_inf = df_comb[combustivel_selecionado].quantile(0.005)
                lim_sup = df_comb[combustivel_selecionado].quantile(0.995)
                df_filtrado = df_comb[
                    (df_comb[combustivel_selecionado] >= lim_inf)
                    & (df_comb[combustivel_selecionado] <= lim_sup)
                ].copy()

            elif metodo_outliers == "2% (Corte de 1% / 99%)" and total_inicial > 0:
                lim_inf = df_comb[combustivel_selecionado].quantile(0.01)
                lim_sup = df_comb[combustivel_selecionado].quantile(0.99)
                df_filtrado = df_comb[
                    (df_comb[combustivel_selecionado] >= lim_inf)
                    & (df_comb[combustivel_selecionado] <= lim_sup)
                ].copy()

            elif metodo_outliers == "5% (Corte de 2.5% / 97.5%)" and total_inicial > 0:
                lim_inf = df_comb[combustivel_selecionado].quantile(0.025)
                lim_sup = df_comb[combustivel_selecionado].quantile(0.975)
                df_filtrado = df_comb[
                    (df_comb[combustivel_selecionado] >= lim_inf)
                    & (df_comb[combustivel_selecionado] <= lim_sup)
                ].copy()

            elif metodo_outliers == "10% (Corte de 5% / 95%)" and total_inicial > 0:
                lim_inf = df_comb[combustivel_selecionado].quantile(0.05)
                lim_sup = df_comb[combustivel_selecionado].quantile(0.95)
                df_filtrado = df_comb[
                    (df_comb[combustivel_selecionado] >= lim_inf)
                    & (df_comb[combustivel_selecionado] <= lim_sup)
                ].copy()

            else:
                df_filtrado = df_comb.copy()

            total_filtrado = len(df_filtrado)
            qtd_outliers = total_inicial - total_filtrado
            pct_outliers = (
                (qtd_outliers / total_inicial * 100) if total_inicial > 0 else 0
            )

            if not df_filtrado.empty:
                m1, m2 = st.columns(2)
                val_serie = df_filtrado[combustivel_selecionado]

                if tipo_dado == "precos":
                    lbl_principal = "Preço Médio"
                    val_principal = f"R$ {val_serie.mean():.2f}".replace(".", ",")
                    lbl_secundario_1 = "Menor Preço"
                    val_sec_1 = f"R$ {val_serie.min():.2f}".replace(".", ",")
                    lbl_secundario_2 = "Maior Preço"
                    val_sec_2 = f"R$ {val_serie.max():.2f}".replace(".", ",")
                elif tipo_dado == "volumes":
                    lbl_principal = "Volume Total"
                    val_principal = f"{val_serie.sum():,.0f} L".replace(",", ".")
                    lbl_secundario_1 = "Média / Município"
                    val_sec_1 = f"{val_serie.mean():,.0f} L".replace(",", ".")
                    lbl_secundario_2 = "Maior Volume"
                    val_sec_2 = f"{val_serie.max():,.0f} L".replace(",", ".")
                else:
                    lbl_principal = "Faturamento Total"
                    val_principal = f"R$ {val_serie.sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    lbl_secundario_1 = "Média / Município"
                    val_sec_1 = f"R$ {val_serie.mean():,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    lbl_secundario_2 = "Maior Faturamento"
                    val_sec_2 = f"R$ {val_serie.max():,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

                with m1:
                    st.metric(lbl_principal, val_principal)
                    st.metric(lbl_secundario_1, val_sec_1)
                with m2:
                    st.metric(lbl_secundario_2, val_sec_2)
                    st.metric("Municípios", f"{total_filtrado}/246")

                if qtd_outliers > 0:
                    st.warning(f"Outliers: {qtd_outliers} ({pct_outliers:.1f}%)")
                else:
                    st.success("Outliers: Nenhum (0%)")
                    
else:
    with col1:
        st.info("Aguardando upload do arquivo `.csv` para renderizar o painel.")

with col2:
    if uploaded_file is not None and not df_filtrado.empty and combustivel_selecionado:
        @st.cache_data
        def processar_geometrias(geojson_data):
            return gpd.GeoDataFrame.from_features(geojson_data["features"])

        gdf_go = processar_geometrias(geojson_dict)
        gdf_go["id"] = gdf_go["id"].astype(str)

        df_base = df.drop(columns=[c for c in df.columns if c not in ["MUNICIPIO", "COD_IBGE", "DATA_INI", "DATA_FIM"]], errors="ignore")
        df_base["COD_IBGE"] = df_base["COD_IBGE"].astype(str)
        df_filtrado["COD_IBGE"] = df_filtrado["COD_IBGE"].astype(str)

        df_merge = df_base.merge(
            df_filtrado[["COD_IBGE", combustivel_selecionado]],
            on="COD_IBGE",
            how="left",
        )

        gdf_mapa = gdf_go.merge(df_merge, left_on="id", right_on="COD_IBGE", how="left")
        
        gdf_mapa["nome_exibicao"] = (
            gdf_mapa["MUNICIPIO"].fillna(gdf_mapa["name"])
            .astype(str)
            .str.title()
        )

        status_outlier_txt = (
            f"Outliers: {qtd_outliers} ({pct_outliers:.1f}%)"
            if qtd_outliers > 0
            else "Outliers: Nenhum (0%)"
        )

        nome_comb_upper = opcoes_combustiveis[combustivel_selecionado].upper()
        
        st.markdown(
            f"""
            <h3 style="font-size: 1.15rem; margin-bottom: -0.5rem; font-family: Arial, sans-serif;">
                {cfg['titulo_mapa']}: <span style="color: {cfg['cor_accent']};">{nome_comb_upper}</span>
            </h3>
            """,
            unsafe_allow_html=True
        )
        
        st.caption(
            f"Estado de Goiás | Período: {data_ini} a {data_fim} |"
            f" {status_outlier_txt}"
        )

        fig = go.Figure()

        fig.add_trace(
            go.Choropleth(
                geojson=geojson_dict,
                locations=gdf_mapa["id"],
                featureidkey="properties.id",
                z=[1] * len(gdf_mapa),
                colorscale=[[0, "#ECECEC"], [1, "#ECECEC"]],
                showscale=False,
                marker_line_width=0.6,
                marker_line_color="#4A4A4A",
                hoverinfo="skip",
            )
        )

        df_com_dados = gdf_mapa[gdf_mapa[combustivel_selecionado].notna()].copy()

        # Aplicação da escala logarítmica inteligente para volumes e faturamento
        if cfg["escala_log"]:
            val_plot = np.log1p(df_com_dados[combustivel_selecionado])
            zmin_val = np.log1p(df_filtrado[combustivel_selecionado].min())
            zmax_val = np.log1p(df_filtrado[combustivel_selecionado].max())
        else:
            val_plot = df_com_dados[combustivel_selecionado]
            zmin_val = df_filtrado[combustivel_selecionado].min()
            zmax_val = df_filtrado[combustivel_selecionado].max()

        if tipo_dado == "precos":
            hover_template = "<b>%{text}</b><br>Preço: R$ %{customdata[0]:.2f}<extra></extra>"
            cb_title = "Preço (R$)"
        elif tipo_dado == "volumes":
            hover_template = "<b>%{text}</b><br>Volume: %{customdata[0]:,.0f} L<extra></extra>"
            cb_title = "Volume (L) [Escala Log]"
        else:
            hover_template = "<b>%{text}</b><br>Valor Total: R$ %{customdata[0]:,.2f}<extra></extra>"
            cb_title = "Valor (R$) [Escala Log]"

        fig.add_trace(
            go.Choropleth(
                geojson=geojson_dict,
                locations=df_com_dados["id"],
                featureidkey="properties.id",
                z=val_plot,
                customdata=np.stack([df_com_dados[combustivel_selecionado]], axis=-1),
                colorscale=cfg["colorscale"],
                zmin=zmin_val,
                zmax=zmax_val,
                marker_line_width=0.6,
                marker_line_color="#4A4A4A",
                text=df_com_dados["nome_exibicao"],
                hovertemplate=hover_template,
                colorbar=dict(title=cb_title, thickness=15, len=0.65),
            )
        )

        if mostrar_nomes:
            df_com_dados["centroid"] = df_com_dados.geometry.centroid
            lats = [point.y for point in df_com_dados["centroid"]]
            lons = [point.x for point in df_com_dados["centroid"]]

            fig.add_trace(
                go.Scattergeo(
                    lat=lats,
                    lon=lons,
                    text=df_com_dados["nome_exibicao"],
                    mode="text",
                    textfont=dict(size=8, family="Arial, sans-serif", color="black"),
                    hoverinfo="skip",
                )
            )

        fig.update_geos(
            fitbounds="locations",
            visible=False,
            showcountries=False,
            showcoastlines=False,
        )

        fig.update_layout(
            font=dict(family="Arial, sans-serif"),
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            height=620, 
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )

        st.plotly_chart(fig, use_container_width=True, key=f"mapa_{tipo_dado}_{combustivel_selecionado}_{metodo_outliers}")

#    else:
#        with col2:
#            st.info("👈 Faça o upload do arquivo CSV na barra lateral para visualizar o mapa e os dados.")