# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import warnings
import traceback
from google.cloud import bigquery

warnings.filterwarnings("ignore")

try:
    # ============================================================================
    # CONFIGURAÇÃO DA PÁGINA STREAMLIT
    # ============================================================================
    st.set_page_config(
        page_title="Dashboard PNAD/CAGED",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.markdown("""
        <style>
        .main { padding: 2rem; }
        .stMetric { background-color: #f0f2f6; padding: 1rem; border-radius: 0.5rem; }
        </style>
        """, unsafe_allow_html=True)

    # ============================================================================
    # INICIALIZAÇÃO DO CLIENTE BIGQUERY
    # ============================================================================
    # O Cloud Run se autentica automaticamente se as permissões passadas no IAM estiverem ok
    client = bigquery.Client()
    
    # ID da sua View salva no BigQuery
    VIEW_ID = "pnad-salarios.pnad_dados.dados_completos_view"

    st.title("📊 Dashboard Interativo PNAD/CAGED")
    st.markdown("""
        **Análise de Salários, Movimentação e Diversidade no Mercado de Trabalho Brasileiro**
    """)

    # ============================================================================
    # FUNÇÕES DE CONSULTA AO BIGQUERY (COM CACHE)
    # ============================================================================
    @st.cache_data(ttl=3600)
    def executar_query(query, params=None):
        """Função auxiliar para executar queries no BigQuery e retornar DataFrame"""
        if params:
            job_config = bigquery.QueryJobConfig(query_parameters=params)
            query_job = client.query(query, job_config=job_config)
        else:
            query_job = client.query(query)
        return query_job.to_dataframe()

    @st.cache_data(ttl=86400)  # Cache de 24h para os filtros estruturais
    def obter_valores_filtro(coluna, condicao_sql=""):
        """Busca valores únicos de uma coluna para preencher a barra lateral"""
        # Remove crases que possam vir na string para não duplicar
        coluna_limpa = coluna.replace("`", "")
        query = f"SELECT DISTINCT `{coluna_limpa}` FROM `{VIEW_ID}` {condicao_sql} WHERE `{coluna_limpa}` IS NOT NULL ORDER BY `{coluna_limpa}`"
        df = executar_query(query)
        return df[coluna_limpa].tolist()

    # Mapeamentos mantidos para a exibição visual
    mapa_contrato = {-1: "Demitidos", 1: "Admitidos"}
    mapa_sexo = {1: "Masculino", 3: "Feminino", 9: "Não Identificado"}
    mapa_raca = {1: "Branca", 2: "Preta", 3: "Parda", 4: "Amarela", 5: "Indígena", 6: "Não Informado", 9: "Não Identificado"}
    mapa_meses = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
        7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }

    # ============================================================================
    # SIDEBAR - CONSTRUÇÃO DINÂMICA VIA BIGQUERY
    # ============================================================================
    st.sidebar.header("🔍 Filtros")

    with st.sidebar.expander("📅 Período", expanded=True):
        # Extrai os Anomes disponíveis na base
        lista_anomes_int = obter_valores_filtro("competênciamov")
        lista_anomes_str = [str(x) for x in lista_anomes_int]
        
        # Agrupa anos e meses unicamente
        anos_disponiveis = sorted(list(set([int(x[:4]) for x in lista_anomes_str])))
        ano_selecionado = st.selectbox("Ano", anos_disponiveis)

        meses_disponiveis = sorted(list(set([int(x[4:6]) for x in lista_anomes_str if x.startswith(str(ano_selecionado))])))
        mes_idx = st.selectbox("Mês", range(len(meses_disponiveis)), format_func=lambda x: mapa_meses[meses_disponiveis[x]])
        mes_selecionado = meses_disponiveis[mes_idx]
        
        # Reconstrói a competência para o filtro SQL final
        anomes_filtro = int(f"{ano_selecionado}{str(mes_selecionado).zfill(2)}")

    with st.sidebar.expander("🗺️ Localização", expanded=True):
        regioes = obter_valores_filtro("região")
        regiao_map_invertido = { "Todas": "Todas", "Norte": 1, "Nordeste": 2, "Sudeste": 3, "Sul": 4, "Centro-Oeste": 5 }
        regiao_exibicao = st.selectbox("Região", ["Todas", "Norte", "Nordeste", "Sudeste", "Sul", "Centro-Oeste"])
        regiao = regiao_map_invertido[regiao_exibicao]

        condicao_uf = ""
        if regiao != "Todas":
            condicao_uf = f"WHERE `região` = {regiao}"
        
        ufs_cod = obter_valores_filtro("uf", condicao_uf)
        mapa_uf_local = {
            11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
            21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA",
            31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR", 42: "SC", 43: "RS",
            50: "MS", 51: "MT", 52: "GO", 53: "DF"
        }
        ufs_nomes = [mapa_uf_local[x] for x in ufs_cod if x in mapa_uf_local]
        uf_exibida = st.selectbox("UF", ["Todos"] + sorted(ufs_nomes))
        
        # Inverte a UF selecionada para código numérico
        uf = "Todos"
        if uf_exibida != "Todos":
            uf = [k for k, v in mapa_uf_local.items() if v == uf_exibida][0]

        condicao_mun = "WHERE 1=1"
        if uf != "Todos":
            condicao_mun += f" AND uf = {uf}"
        elif regiao != "Todas":
            condicao_mun += f" AND `região` = {regiao}"
            
        municipios = obter_valores_filtro("município", condicao_mun)
        municipio = st.selectbox("Município", ["Todos"] + municipios)

    with st.sidebar.expander("💼 Ocupação"):
        cbos = obter_valores_filtro("cbo2002ocupação")
        cbo = st.selectbox("CBO", ["Todos"] + cbos)

    with st.sidebar.expander("🌈 Diversidade"):
        genero_exibido = st.selectbox("Gênero", ["Todos", "Masculino", "Feminino", "Não Identificado"])
        mapa_sexo_inv = {"Todos": "Todos", "Masculino": 1, "Feminino": 3, "Não Identificado": 9}
        genero = mapa_sexo_inv[genero_exibido]

        etnia_exibida = st.selectbox("Etnia", ["Todos", "Branca", "Preta", "Parda", "Amarela", "Indígena", "Não Informado", "Não Identificado"])
        mapa_raca_inv = {"Todos": "Todos", "Branca": 1, "Preta": 2, "Parda": 3, "Amarela": 4, "Indígena": 5, "Não Informado": 6, "Não Identificado": 9}
        etnia = mapa_raca_inv[etnia_exibida]

    # ============================================================================
    # CONSTRUÇÃO DA QUERY DINÂMICA PRINCIPAL VIA SQL
    # ============================================================================
    query_base = f"SELECT * FROM `{VIEW_ID}` WHERE `competênciamov` = @anomes"
    params = [bigquery.ScalarQueryParameter("anomes", "INT64", anomes_filtro)]

    if regiao != "Todas":
        query_base += " AND `região` = @regiao"
        params.append(bigquery.ScalarQueryParameter("regiao", "INT64", regiao))
    if uf != "Todos":
        query_base += " AND uf = @uf"
        params.append(bigquery.ScalarQueryParameter("uf", "INT64", uf))
    if municipio != "Todos":
        query_base += " AND `município` = @municipio"
        params.append(bigquery.ScalarQueryParameter("municipio", "STRING", municipio))
    if cbo != "Todos":
        query_base += " AND `cbo2002ocupação` = @cbo"
        params.append(bigquery.ScalarQueryParameter("cbo", "INT64", cbo))
    if genero != "Todos":
        query_base += " AND sexo = @genero"
        params.append(bigquery.ScalarQueryParameter("genero", "INT64", genero))
    if etnia != "Todos":
        query_base += " AND `raçacor` = @etnia"
        params.append(bigquery.ScalarQueryParameter("etnia", "INT64", etnia))

    # Executa e traz APENAS o bloco de dados filtrados para a memória
    df_filtrado = executar_query(query_base, params)

    # ============================================================================
    # TRATAMENTO DOS DADOS FILTRADOS (PÓS-QUERY)
    # ============================================================================
    if len(df_filtrado) > 0:
        mapa_regiao = {1: "Norte", 2: "Nordeste", 3: "Sudeste", 4: "Sul", 5: "Centro-Oeste"}
        df_filtrado["nome_regiao"] = df_filtrado["região"].map(mapa_regiao)
        df_filtrado["sigla_uf"] = df_filtrado["uf"].map(mapa_uf_local)
        df_filtrado["nome_municipio"] = df_filtrado["município"].astype(str)
        df_filtrado["contrato"] = df_filtrado["saldomovimentação"].map(mapa_contrato)
        df_filtrado["genero"] = df_filtrado["sexo"].map(mapa_sexo)
        df_filtrado["etnia"] = df_filtrado["raçacor"].map(mapa_raca)
        
        # Cálculo do salário deflacionado pelo INPC direto no Python usando o inpc da view
        # Nota: Se o inpc vier nulo ou zerado, tratamos para evitar divisão por zero
        df_filtrado["inpc_fator"] = 1 + df_filtrado["inpc"].fillna(0) / 100
        df_filtrado["Sal_def_INPC"] = df_filtrado["salário"] / df_filtrado["inpc_fator"]
        df_filtrado["Anomes"] = df_filtrado["competênciamov"].astype(str)

    # ============================================================================
    # KPIs
    # ============================================================================
    st.subheader("📈 Indicadores Principais")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_adm = len(df_filtrado[df_filtrado["contrato"] == "Admitidos"]) if len(df_filtrado) > 0 else 0
        st.metric("Total Admitidos", f"{total_adm:,}")

    with col2:
        total_dem = len(df_filtrado[df_filtrado["contrato"] == "Demitidos"]) if len(df_filtrado) > 0 else 0
        st.metric("Total Demitidos", f"{total_dem:,}")

    with col3:
        saldo = total_adm - total_dem
        st.metric("Saldo", f"{saldo:,}")

    with col4:
        media_sal = df_filtrado["salário"].mean() if len(df_filtrado) > 0 else 0.0
        st.metric("Salário Médio", f"R$ {media_sal:,.2f}")

    # ============================================================================
    # GRÁFICOS
    # ============================================================================
    st.subheader("📊 Visualizações Interativas")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["Salários", "Por Região", "Por Gênero", "Por Etnia", "Comparativo"]
    )

    with tab1:
        if len(df_filtrado) > 0:
            df_media = df_filtrado.groupby("contrato").agg({"salário": "mean", "Sal_def_INPC": "mean"}).reset_index()
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df_media["contrato"], y=df_media["salário"], name="Nominal"))
            fig.add_trace(go.Bar(x=df_media["contrato"], y=df_media["Sal_def_INPC"], name="Deflacionado"))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados para este período.")

    with tab2:
        if len(df_filtrado) > 0:
            df_regiao = df_filtrado.groupby(["nome_regiao", "contrato"]).size().reset_index(name="quantidade")
            fig = px.bar(df_regiao, x="nome_regiao", y="quantidade", color="contrato", barmode="group")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados para este período.")

    with tab3:
        if len(df_filtrado) > 0:
            df_genero = df_filtrado.groupby("genero").size().reset_index(name="quantidade")
            fig = px.pie(df_genero, values="quantidade", names="genero", hole=0.3)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados para este período.")

    with tab4:
        if len(df_filtrado) > 0:
            df_etnia = df_filtrado.groupby(["etnia", "contrato"]).size().reset_index(name="quantidade")
            fig = px.bar(df_etnia, x="etnia", y="quantidade", color="contrato", barmode="stack")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados para este período.")

    with tab5:
        if len(df_filtrado) > 0:
            df_comp = df_filtrado.groupby("contrato").agg({"salário": "mean", "Anomes": "count"}).reset_index()
            df_comp.rename(columns={"Anomes": "quantidade"}, inplace=True)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_comp["contrato"], y=df_comp["salário"], mode="lines+markers", name="Salário"))
            fig.add_trace(go.Bar(x=df_comp["contrato"], y=df_comp["quantidade"], name="Quantidade", opacity=0.5))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados para este período.")

    # ============================================================================
    # TABELA
    # ============================================================================
    st.subheader("📋 Dados Detalhados")

    if st.checkbox("Mostrar tabela de dados"):
        if len(df_filtrado) > 0:
            colunas = ["Anomes", "nome_regiao", "sigla_uf", "nome_municipio",
                       "cbo2002ocupação", "contrato", "genero", "etnia",
                       "salário", "Sal_def_INPC"]
            colunas = [c for c in colunas if c in df_filtrado.columns]
            st.dataframe(df_filtrado[colunas], use_container_width=True)
        else:
            st.info("Sem dados para exibir na tabela.")

    # ============================================================================
    # EXPORTAÇÃO
    # ============================================================================
    st.subheader("💾 Exportar Dados")

    col_csv, col_excel = st.columns(2)

    with col_csv:
        if st.button("📥 Baixar como CSV") and len(df_filtrado) > 0:
            csv = df_filtrado.to_csv(index=False, encoding="utf-8")
            st.download_button("Download CSV", csv, file_name="dados.csv")

    with col_excel:
        if st.button("📥 Baixar como Excel") and len(df_filtrado) > 0:
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df_filtrado.to_excel(writer, index=False)
            st.download_button("Download Excel", buffer.getvalue(), file_name="dados.xlsx")

    # ============================================================================
    # RODAPÉ
    # ============================================================================
    st.markdown("---")
    st.markdown("""
        <div style="text-align: center; color: gray; font-size: 12px;">
            <p>Dashboard PNAD/CAGED | Desenvolvido por Professor Dulluca | 2026</p>
        </div>
    """, unsafe_allow_html=True)

except Exception as e:
    st.error("❌ Erro ao executar o app:")
    st.code(traceback.format_exc())
