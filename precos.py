import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    layout="wide", page_title="Mapa de Calor - Preço de Combustíveis GO"
)

# Estilos CSS otimizados para responsividade e redução de tamanhos de fontes
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
        /* Reduz o tamanho da fonte do st.title */
        h1 {
            font-size: 1.6rem !important;
        }
        /* Reduz o tamanho da fonte do st.subheader (Título do Mapa) */
        h3 {
            font-size: 1.15rem !important;
            margin-bottom: -0.5rem !important;
        }

    </style>
""",
    unsafe_allow_html=True,
)


st.title("🗺️ Mapa de Calor de Preços de Combustíveis - Goiás")

# Estrutura principal em duas colunas desde o topo
col1, col2 = st.columns([1, 2.5])

with col1:
  # 1. Widget de Upload de Arquivo na coluna esquerda
  uploaded_file = st.file_uploader(
      "Faça o upload do arquivo CSV com os preços", type=["csv"]
  )

# Variáveis padrão
df = None
df_filtrado = pd.DataFrame()
qtd_outliers = 0
pct_outliers = 0.0
combustivel_selecionado = ""
opcoes_combustiveis = {}
data_ini = ""
data_fim = ""

if uploaded_file is not None:
  with col1:
    # Leitura do CSV considerando separador TAB e decimal com vírgula
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

    # Limpeza de cabeçalhos
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

#      # Seleção de Combustível
#      combustivel_selecionado = st.selectbox(
#          "Selecione o Combustível:",
#          options=list(opcoes_combustiveis.keys()),
#          format_func=lambda x: opcoes_combustiveis[x],
#      )

      # Tenta identificar o índice padrão para "Gasolina Comum" ou variações similares
      chaves_opcoes = list(opcoes_combustiveis.keys())
      indice_padrao = 0
      
      for i, chave in enumerate(chaves_opcoes):
        chave_lower = chave.lower()
        if "gasolina" in chave_lower and ("comum" in chave_lower or "gasolina_comum" in chave_lower or chave_lower == "gasolina"):
          indice_padrao = i
          break

      # Seleção de Combustível com Gasolina Comum como padrão inicial
      combustivel_selecionado = st.selectbox(
          "Selecione o Combustível:",
          options=chaves_opcoes,
          format_func=lambda x: opcoes_combustiveis[x],
          index=indice_padrao,
      )

      # Opções de Filtro de Outliers
      metodo_outliers = st.radio(
          "Filtro de Outliers:",
          options=[
              "Nenhum (0%)",
              "Remover via IQR (Estatístico)",
              "1% (Corte de 0.5% / 99.5%)",
              "2% (Corte de 1% / 99%)",
              "5% (Corte de 2.5% / 97.5%)",
              "10% (Corte de 5% / 95%)",
          ],
          index=1,
          help=(
              "• **Nenhum**: Mantém todos os dados.\n"
              "• **IQR**: Intervalo Interquartil (Q1 - 1.5*IQR a Q3 + 1.5*IQR).\n"
              "• **Cortes Percentuais**: Remove as porcentagens especificadas nas extremidades superior e inferior."
          ),
      )

      # Checkbox para alternar exibição dos nomes dos municípios (padrão: desmarcado)
      mostrar_nomes = st.checkbox("Exibir nomes dos municípios no mapa", value=False)

      data_ini = df["DATA_INI"].dropna().iloc[0] if "DATA_INI" in df else ""
      data_fim = df["DATA_FIM"].dropna().iloc[0] if "DATA_FIM" in df else ""

      st.caption(f"📅 **Período:** {data_ini} a {data_fim}")

      # Processamento de dados e tratamento de outliers
      df_comb = df[df[combustivel_selecionado].notna()].copy()
      df_comb[combustivel_selecionado] = pd.to_numeric(
          df_comb[combustivel_selecionado], errors="coerce"
      )

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

      # Indicadores compactos
      if not df_filtrado.empty:
        m1, m2 = st.columns(2)
        with m1:
          st.metric(
              "Preço Médio",
              f"R$ {df_filtrado[combustivel_selecionado].mean():.2f}".replace(
                  ".", ","
              ),
          )
          st.metric(
              "Menor Preço",
              f"R$ {df_filtrado[combustivel_selecionado].min():.2f}".replace(
                  ".", ","
              ),
          )
        with m2:
          st.metric(
              "Maior Preço",
              f"R$ {df_filtrado[combustivel_selecionado].max():.2f}".replace(
                  ".", ","
              ),
          )
          st.metric("Municípios", f"{total_filtrado}/246")

        if qtd_outliers > 0:
          st.warning(f"Outliers: {qtd_outliers} ({pct_outliers:.1f}%)")
        else:
          st.success("Outliers: Nenhum (0%)")
else:
  with col1:
    st.info("Aguardando upload do arquivo `.csv` para renderizar o painel.")
with col2:
  if uploaded_file is not None and not df_filtrado.empty:
    @st.cache_data
    def carregar_malha_goias():
      url_geojson = "https://raw.githubusercontent.com/tbrugz/geodata-br/master/geojson/geojs-52-mun.json"
      return gpd.read_file(url_geojson)

    gdf_go = carregar_malha_goias()
    gdf_go["id"] = gdf_go["id"].astype(str)

    df_base = df.drop(columns=[combustivel_selecionado], errors="ignore")
    df_base["COD_IBGE"] = df_base["COD_IBGE"].astype(str)
    df_filtrado["COD_IBGE"] = df_filtrado["COD_IBGE"].astype(str)

    df_merge = df_base.merge(
        df_filtrado[["COD_IBGE", combustivel_selecionado]],
        on="COD_IBGE",
        how="left",
    )

    gdf_mapa = gdf_go.merge(df_merge, left_on="id", right_on="COD_IBGE", how="left")
    
    # Formata o nome para ter apenas a primeira letra maiúscula
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

    # Título do mapa estilizado com HTML para colorir somente o nome do combustível
    nome_comb_upper = opcoes_combustiveis[combustivel_selecionado].upper()
    
    st.markdown(
        f"""
        <h3 style="font-size: 1.15rem; margin-bottom: -0.5rem; font-family: Arial, sans-serif;">
            MAPA DE CALOR: <span style="color: #00a2e8;">{nome_comb_upper}</span>
        </h3>
        """,
        unsafe_allow_html=True
    )
    
    st.caption(
        f"Estado de Goiás | Período: {data_ini} a {data_fim} |"
        f" {status_outlier_txt}"
    )


    url_geojson = "https://raw.githubusercontent.com/tbrugz/geodata-br/master/geojson/geojs-52-mun.json"

    fig = go.Figure()

    # CAMADA 1: Fundo cinza claro (todos os municípios)
    fig.add_trace(
        go.Choropleth(
            geojson=url_geojson,
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

    # CAMADA 2: Preços coloridos (apenas municípios com dados)
    df_com_dados = gdf_mapa[gdf_mapa[combustivel_selecionado].notna()].copy()

    fig.add_trace(
        go.Choropleth(
            geojson=url_geojson,
            locations=df_com_dados["id"],
            featureidkey="properties.id",
            z=df_com_dados[combustivel_selecionado],
            colorscale="RdYlGn_r",
            zmin=df_filtrado[combustivel_selecionado].min(),
            zmax=df_filtrado[combustivel_selecionado].max(),
            marker_line_width=0.6,
            marker_line_color="#4A4A4A",
            text=df_com_dados["nome_exibicao"],
            hovertemplate=(
                "<b>%{text}</b><br>Preço: R$ %{z:.2f}<extra></extra>"
            ),
            colorbar=dict(title="Preço (R$)", thickness=15, len=0.65),
        )
    )

    # CAMADA 3: Rótulos de texto condicionadas ao checkbox
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

    st.plotly_chart(fig, use_container_width=True)

#  else:
#    st.info("Aguardando upload do arquivo `.csv` para renderizar o painel.")