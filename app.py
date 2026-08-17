# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import warnings
import traceback
from google.cloud import bigquery

warnings.filterwarnings("ignore")

try:
    st.set_page_config(
        page_title="Dashboard PNAD/CAGED",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        """
        <style>
        .main { padding: 2rem; }
        .stMetric { background-color: #f0f2f6; padding: 1rem; border-radius: 0.5rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    client = bigquery.Client()
    VIEW_ID = "1043829155645.pnad_dados.dados_completos_view"
    PROJECT_ID, DATASET_ID, VIEW_NAME = VIEW_ID.split(".")

    st.title("📊 Dashboard Interativo PNAD/CAGED")
    st.markdown("**Análise de salários, movimentação e diversidade no mercado de trabalho brasileiro**")

    # Não aplicar st.cache_data diretamente nesta função: objetos de parâmetros
    # do BigQuery podem conter referências não serializáveis (funções internas),
    # causando o erro "TypeError: cannot pickle 'function' object".
    def executar_query(query, params=None):
        """Executa uma consulta parametrizada no BigQuery e retorna um DataFrame."""
        job_config = bigquery.QueryJobConfig(query_parameters=params or [])
        return client.query(query, job_config=job_config).to_dataframe()

    @st.cache_data(ttl=86400)
    def obter_colunas_view():
        """Obtém o schema da view para evitar confundir município com CBO."""
        query = f"""
            SELECT column_name
            FROM `{PROJECT_ID}.{DATASET_ID}.INFORMATION_SCHEMA.COLUMNS`
            WHERE table_name = @view_name
            ORDER BY ordinal_position
        """
        try:
            df = executar_query(query, [bigquery.ScalarQueryParameter("view_name", "STRING", VIEW_NAME)])
            return df["column_name"].tolist()
        except Exception:
            return []

    COLUNAS_VIEW = obter_colunas_view()

    def coluna_existente(candidatas):
        """Retorna a primeira coluna existente, ignorando diferenças de acentuação/case."""
        normalizadas = {str(c).lower(): c for c in COLUNAS_VIEW}
        for candidata in candidatas:
            if candidata.lower() in normalizadas:
                return normalizadas[candidata.lower()]
        return None

    # O nome deve vir de uma coluna de município, nunca da coluna CBO.
    COLUNA_MUNICIPIO_NOME = coluna_existente([
        "nome_municipio", "nome_município", "municipio_nome", "município_nome",
        "nomemunicipio", "nome do município", "nome_municipio_ibge",
    ])
    COLUNA_MUNICIPIO_CODIGO = coluna_existente(["município", "municipio", "cod_municipio", "codigo_municipio"])
    COLUNA_MUNICIPIO = COLUNA_MUNICIPIO_NOME or COLUNA_MUNICIPIO_CODIGO

    if not COLUNA_MUNICIPIO:
        raise RuntimeError("A view não possui uma coluna de município reconhecível.")

    @st.cache_data(ttl=86400)
    def obter_valores_filtro(coluna, condicao_sql=""):
        coluna_sql = f"`{coluna}`"
        where = condicao_sql.strip() or "WHERE 1=1"
        query = f"""
            SELECT DISTINCT {coluna_sql} AS valor
            FROM `{VIEW_ID}`
            {where} AND {coluna_sql} IS NOT NULL
            ORDER BY valor
        """
        df = executar_query(query)
        return df["valor"].tolist()

    @st.cache_data(ttl=86400)
    def obter_municipios(condicao_sql=""):
        """Lista nomes de município; se a base só tiver código, converte para texto sem usar CBO."""
        where = condicao_sql.strip() or "WHERE 1=1"
        expressao = f"`{COLUNA_MUNICIPIO_NOME}`" if COLUNA_MUNICIPIO_NOME else f"CAST(`{COLUNA_MUNICIPIO_CODIGO}` AS STRING)"
        query = f"""
            SELECT DISTINCT {expressao} AS valor
            FROM `{VIEW_ID}`
            {where} AND {expressao} IS NOT NULL
            ORDER BY valor
        """
        df = executar_query(query)
        return df["valor"].astype(str).tolist()

    mapa_contrato = {-1: "Demitidos", 1: "Admitidos"}
    mapa_sexo = {1: "Masculino", 3: "Feminino", 9: "Não Identificado"}
    mapa_raca = {1: "Branca", 2: "Preta", 3: "Parda", 4: "Amarela", 5: "Indígena", 6: "Não Informado", 9: "Não Identificado"}
    mapa_meses = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
    mapa_regiao = {1: "Norte", 2: "Nordeste", 3: "Sudeste", 4: "Sul", 5: "Centro-Oeste"}
    mapa_uf_local = {11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF"}

    st.sidebar.header("🔍 Filtros")
    with st.sidebar.expander("📅 Período", expanded=True):
        lista_anomes = [int(x) for x in obter_valores_filtro("competênciamov") if pd.notna(x)]
        if not lista_anomes:
            raise RuntimeError("Não há competências disponíveis na view.")
        anos_disponiveis = sorted({x // 100 for x in lista_anomes})
        ano_selecionado = st.selectbox("Ano", anos_disponiveis, index=len(anos_disponiveis) - 1)
        meses_disponiveis = sorted({x % 100 for x in lista_anomes if x // 100 == ano_selecionado})
        mes_idx = st.selectbox("Mês", range(len(meses_disponiveis)), format_func=lambda i: mapa_meses.get(meses_disponiveis[i], str(meses_disponiveis[i])))
        mes_selecionado = meses_disponiveis[mes_idx]
        anomes_filtro = ano_selecionado * 100 + mes_selecionado

    with st.sidebar.expander("🗺️ Localização", expanded=True):
        regiao_exibicao = st.selectbox("Região", ["Todas", "Norte", "Nordeste", "Sudeste", "Sul", "Centro-Oeste"])
        regiao_map_invertido = {"Todas": "Todos", "Norte": 1, "Nordeste": 2, "Sudeste": 3, "Sul": 4, "Centro-Oeste": 5}
        regiao = regiao_map_invertido[regiao_exibicao]
        condicao_uf = "" if regiao == "Todos" else f"WHERE `região` = {regiao}"
        ufs_cod = obter_valores_filtro("uf", condicao_uf)
        ufs_nomes = [mapa_uf_local[x] for x in ufs_cod if x in mapa_uf_local]
        uf_exibida = st.selectbox("UF", ["Todos"] + sorted(ufs_nomes))
        uf = "Todos" if uf_exibida == "Todos" else next(k for k, v in mapa_uf_local.items() if v == uf_exibida)
        condicao_mun = "WHERE 1=1"
        if uf != "Todos":
            condicao_mun += f" AND `uf` = {uf}"
        elif regiao != "Todos":
            condicao_mun += f" AND `região` = {regiao}"
        municipios = obter_municipios(condicao_mun)
        municipio = st.selectbox("Município", ["Todos"] + municipios)
        if not COLUNA_MUNICIPIO_NOME:
            st.caption("A view não possui nome de município; os valores exibidos são os códigos da coluna município.")

    with st.sidebar.expander("💼 Ocupação"):
        cbos = obter_valores_filtro("cbo2002ocupação")
        cbo = st.selectbox("CBO", ["Todos"] + cbos)

    with st.sidebar.expander("🌈 Diversidade"):
        genero_exibido = st.selectbox("Gênero", ["Todos", "Masculino", "Feminino", "Não Identificado"])
        genero = {"Todos": "Todos", "Masculino": 1, "Feminino": 3, "Não Identificado": 9}[genero_exibido]
        etnia_exibida = st.selectbox("Etnia", ["Todos", "Branca", "Preta", "Parda", "Amarela", "Indígena", "Não Informado", "Não Identificado"])
        etnia = {"Todos": "Todos", "Branca": 1, "Preta": 2, "Parda": 3, "Amarela": 4, "Indígena": 5, "Não Informado": 6, "Não Identificado": 9}[etnia_exibida]

    filtros_sql = ""
    params = [bigquery.ScalarQueryParameter("anomes", "INT64", anomes_filtro)]
    if regiao != "Todos":
        filtros_sql += " AND `região` = @regiao"
        params.append(bigquery.ScalarQueryParameter("regiao", "INT64", regiao))
    if uf != "Todos":
        filtros_sql += " AND `uf` = @uf"
        params.append(bigquery.ScalarQueryParameter("uf", "INT64", uf))
    if municipio != "Todos":
        if COLUNA_MUNICIPIO_NOME:
            filtros_sql += f" AND `{COLUNA_MUNICIPIO_NOME}` = @municipio"
        else:
            filtros_sql += f" AND CAST(`{COLUNA_MUNICIPIO_CODIGO}` AS STRING) = @municipio"
        params.append(bigquery.ScalarQueryParameter("municipio", "STRING", str(municipio)))
    if cbo != "Todos":
        filtros_sql += " AND `cbo2002ocupação` = @cbo"
        params.append(bigquery.ScalarQueryParameter("cbo", "INT64", int(cbo)))
    if genero != "Todos":
        filtros_sql += " AND `sexo` = @genero"
        params.append(bigquery.ScalarQueryParameter("genero", "INT64", genero))
    if etnia != "Todos":
        filtros_sql += " AND `raçacor` = @etnia"
        params.append(bigquery.ScalarQueryParameter("etnia", "INT64", etnia))

    query_base = f"SELECT * FROM `{VIEW_ID}` WHERE `competênciamov` = @anomes{filtros_sql}"
    df_filtrado = executar_query(query_base, params)

    def preparar_dataframe(df):
        if df.empty:
            return df
        df = df.copy()
        df["nome_regiao"] = df["região"].map(mapa_regiao)
        df["sigla_uf"] = df["uf"].map(mapa_uf_local)
        if COLUNA_MUNICIPIO_NOME and COLUNA_MUNICIPIO_NOME in df.columns:
            df["nome_municipio"] = df[COLUNA_MUNICIPIO_NOME].astype(str)
        else:
            df["nome_municipio"] = df[COLUNA_MUNICIPIO_CODIGO].astype(str)
        df["contrato"] = df["saldomovimentação"].map(mapa_contrato)
        df["genero"] = df["sexo"].map(mapa_sexo)
        df["etnia"] = df["raçacor"].map(mapa_raca)
        coluna_inpc = next((c for c in df.columns if "inpc" in c.lower()), None)
        fator = 1 + df[coluna_inpc].fillna(0) / 100 if coluna_inpc else 1.0
        df["Sal_def_INPC"] = df["salário"] / fator
        df["Anomes"] = df["competênciamov"].astype(str)
        return df

    df_filtrado = preparar_dataframe(df_filtrado)

    # Histórico: últimos 12 meses até o mês selecionado, mantendo os mesmos filtros.
    periodo = pd.Period(f"{anomes_filtro // 100}-{anomes_filtro % 100:02d}", freq="M")
    historico_anomes = [int((periodo - i).strftime("%Y%m")) for i in range(11, -1, -1)]
    params_hist = [bigquery.ArrayQueryParameter("historico", "INT64", historico_anomes)]
    filtros_hist = filtros_sql.replace("@anomes", "@historico")
    # filtros_sql não contém @anomes; a substituição acima é mantida por segurança.
    params_hist.extend([p for p in params if p.name != "anomes"])
    query_hist = f"""
        SELECT `competênciamov` AS anomes,
               COUNTIF(`saldomovimentação` = 1) AS admitidos,
               COUNTIF(`saldomovimentação` = -1) AS demitidos,
               AVG(`salário`) AS salario_medio
        FROM `{VIEW_ID}`
        WHERE `competênciamov` IN UNNEST(@historico){filtros_hist}
        GROUP BY anomes
        ORDER BY anomes
    """
    df_historico = executar_query(query_hist, params_hist)
    if not df_historico.empty:
        df_historico["periodo"] = pd.to_datetime(df_historico["anomes"].astype(str), format="%Y%m").dt.strftime("%b/%Y")
        df_historico["saldo"] = df_historico["admitidos"] - df_historico["demitidos"]

    st.subheader("📈 Indicadores Principais")
    total_adm = int((df_filtrado.get("contrato", pd.Series(dtype=str)) == "Admitidos").sum())
    total_dem = int((df_filtrado.get("contrato", pd.Series(dtype=str)) == "Demitidos").sum())
    media_sal = float(df_filtrado["salário"].mean()) if not df_filtrado.empty else 0.0
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Admitidos", f"{total_adm:,}")
    col2.metric("Total Demitidos", f"{total_dem:,}")
    col3.metric("Saldo", f"{total_adm - total_dem:,}")
    col4.metric("Salário Médio", f"R$ {media_sal:,.2f}")

    st.subheader("📊 Visualizações Interativas")
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Salários", "Por Região", "Por Gênero", "Por Etnia", "Comparativo", "Histórico — 12 meses"])
    with tab1:
        if not df_filtrado.empty:
            df_media = df_filtrado.groupby("contrato", as_index=False).agg(salario_nominal=("salário", "mean"), salario_inpc=("Sal_def_INPC", "mean"))
            fig = go.Figure([go.Bar(x=df_media["contrato"], y=df_media["salario_nominal"], name="Nominal"), go.Bar(x=df_media["contrato"], y=df_media["salario_inpc"], name="Deflacionado")])
            fig.update_layout(barmode="group", yaxis_title="Salário médio (R$)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados para este período.")
    with tab2:
        if not df_filtrado.empty:
            st.plotly_chart(px.bar(df_filtrado.groupby(["nome_regiao", "contrato"]).size().reset_index(name="quantidade"), x="nome_regiao", y="quantidade", color="contrato", barmode="group"), use_container_width=True)
        else: st.info("Sem dados para este período.")
    with tab3:
        if not df_filtrado.empty:
            st.plotly_chart(px.pie(df_filtrado.groupby("genero").size().reset_index(name="quantidade"), values="quantidade", names="genero", hole=0.3), use_container_width=True)
        else: st.info("Sem dados para este período.")
    with tab4:
        if not df_filtrado.empty:
            st.plotly_chart(px.bar(df_filtrado.groupby(["etnia", "contrato"]).size().reset_index(name="quantidade"), x="etnia", y="quantidade", color="contrato", barmode="stack"), use_container_width=True)
        else: st.info("Sem dados para este período.")
    with tab5:
        if not df_filtrado.empty:
            comparativo = df_filtrado.groupby("contrato", as_index=False).agg(salario=("salário", "mean"), quantidade=("contrato", "size"))
            fig = go.Figure([go.Bar(x=comparativo["contrato"], y=comparativo["quantidade"], name="Quantidade"), go.Scatter(x=comparativo["contrato"], y=comparativo["salário"], mode="lines+markers", name="Salário médio", yaxis="y2")])
            fig.update_layout(yaxis=dict(title="Quantidade"), yaxis2=dict(title="Salário médio (R$)", overlaying="y", side="right"))
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("Sem dados para este período.")
    with tab6:
        if not df_historico.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_historico["periodo"], y=df_historico["admitidos"], mode="lines+markers", name="Admitidos"))
            fig.add_trace(go.Scatter(x=df_historico["periodo"], y=df_historico["demitidos"], mode="lines+markers", name="Demitidos"))
            fig.add_trace(go.Scatter(x=df_historico["periodo"], y=df_historico["saldo"], mode="lines+markers", name="Saldo"))
            fig.update_layout(xaxis_title="Competência", yaxis_title="Quantidade", hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("Não há dados históricos para os filtros selecionados.")

    st.subheader("📋 Dados Detalhados")
    if st.checkbox("Mostrar tabela de dados"):
        if not df_filtrado.empty:
            colunas = ["Anomes", "nome_regiao", "sigla_uf", "nome_municipio", "cbo2002ocupação", "contrato", "genero", "etnia", "salário", "Sal_def_INPC"]
            st.dataframe(df_filtrado[[c for c in colunas if c in df_filtrado.columns]], use_container_width=True)
        else: st.info("Sem dados para exibir na tabela.")

    st.subheader("💾 Exportar Dados")
    col_csv, col_excel = st.columns(2)
    with col_csv:
        if st.button("📥 Preparar CSV") and not df_filtrado.empty:
            st.download_button("Download CSV", df_filtrado.to_csv(index=False, encoding="utf-8"), file_name="dados_pnad.csv", mime="text/csv")
    with col_excel:
        if st.button("📥 Preparar Excel") and not df_filtrado.empty:
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer: df_filtrado.to_excel(writer, index=False)
            st.download_button("Download Excel", buffer.getvalue(), file_name="dados_pnad.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.markdown("---")
    st.markdown("<div style='text-align:center;color:gray;font-size:12px'><p>Dashboard PNAD/CAGED | Desenvolvido por Professor Dulluca | 2026</p></div>", unsafe_allow_html=True)

except Exception:
    st.error("❌ Erro ao executar o app:")
    st.code(traceback.format_exc())

# Observação: para exibir nomes, a view deve possuir uma coluna como nome_municipio.
# Se ela tiver apenas o código numérico em município, faça o JOIN com uma dimensão IBGE
# no BigQuery e inclua o nome na dados_completos_view.
