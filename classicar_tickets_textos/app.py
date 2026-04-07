import pandas as pd
import re
import csv
import unicodedata
import os
import numpy as np

# ==============================
# 🔥 CORREÇÃO AUTOMÁTICA TICKETS.CSV
# ==============================

try:
    relatorio1 = pd.read_csv("tickets.csv", sep=";", encoding="utf-8-sig")
    relatorio1.columns = relatorio1.columns.str.strip().str.lower()

    if "id_ticket" not in relatorio1.columns:
        raise Exception("Estrutura inválida")

except:
    print("⚠️ Estrutura do tickets.csv inválida. Aplicando correção automática...")

    relatorio1 = pd.read_csv(
        "tickets.csv",
        sep=",",
        encoding="utf-8-sig",
        engine="python",
        quotechar='"',
        quoting=csv.QUOTE_ALL,
        on_bad_lines="skip",
        header=None
    )

    relatorio1 = relatorio1.iloc[:, :10]

    relatorio1.columns = [
        "id_ticket",
        "data_abertura",
        "status",
        "modulo",
        "caminho",
        "tipo",
        "responsavel",
        "prioridade",
        "ultima_atualizacao",
        "tempo_gasto"
    ]

    primeira_linha = relatorio1.iloc[0].astype(str).str.lower()
    if any("id_ticket" in v for v in primeira_linha):
        relatorio1 = relatorio1.iloc[1:]

# ==============================
# 1. CARREGAR ARQUIVOS
# ==============================

relatorio2 = pd.read_csv(
    "textos.csv",
    sep=",",
    encoding="utf-8-sig",
    engine="python",
    quoting=csv.QUOTE_MINIMAL,
    on_bad_lines="skip"
)

# ==============================
# 🔥 CORREÇÃO AUTOMÁTICA DE ESTRUTURA
# ==============================

relatorio2.columns = relatorio2.columns.str.strip()

if "id_ticket" not in relatorio2.columns:
    print("⚠️ Estrutura do CSV inválida. Aplicando correção automática...")

    relatorio2 = pd.read_csv(
        "textos.csv",
        sep=",",
        encoding="utf-8-sig",
        engine="python",
        header=None,
        quotechar='"',
        quoting=csv.QUOTE_ALL,
        on_bad_lines="skip"
    )

    relatorio2 = relatorio2.iloc[:, :4]
    relatorio2.columns = ["id_ticket", "nome", "texto", "criado_em"]

# ==============================
# 2. LIMPEZA E PADRONIZAÇÃO DEFENSIVA
# ==============================

relatorio1.columns = relatorio1.columns.str.strip().str.lower()
relatorio2.columns = relatorio2.columns.str.strip().str.lower()

relatorio1["id_ticket"] = relatorio1["id_ticket"].astype(str).str.strip()
relatorio2["id_ticket"] = relatorio2["id_ticket"].astype(str).str.strip()

if "modulo" in relatorio1.columns:
    relatorio1["modulo"] = relatorio1["modulo"].astype(str).str.strip()
else:
    print("⚠️ Aviso: Coluna 'modulo' não encontrada em tickets.csv.")
    relatorio1["modulo"] = "Desconhecido"

# ==============================
# 🔥 NORMALIZA TEXTO
# ==============================

if "texto" in relatorio2.columns:
    relatorio2["texto"] = relatorio2["texto"].replace(r'\n', ' ', regex=True)

# ==============================
# 3. FILTRO TEXTO PRINCIPAL
# ==============================

coluna_data = "criado_em"

if coluna_data in relatorio2.columns:
    relatorio2[coluna_data] = pd.to_datetime(
        relatorio2[coluna_data],
        format="%m/%d/%y %H:%M",
        errors="coerce"
    )

    relatorio2["texto"] = relatorio2["texto"].astype(str).str.strip()

    padroes_excluir = [
        "alteração de status",
        "alteracao de status",
        "ticket atribuído",
        "ticket atribuido"
    ]

    def texto_valido(texto):
        texto_lower = texto.lower()
        if texto == "" or texto_lower == "nan":
            return False
        return not any(p in texto_lower for p in padroes_excluir)

    relatorio2 = relatorio2[relatorio2["texto"].apply(texto_valido)]
    relatorio2 = relatorio2.sort_values(by=["id_ticket", coluna_data])
    relatorio2 = relatorio2.drop_duplicates(subset=["id_ticket"], keep="first")

# ==============================
# 4. PREPARAÇÃO DA BASE BRUTA
# ==============================

if "texto" in relatorio2.columns:
    relatorio2 = relatorio2[["id_ticket", "texto"]]

df_base = relatorio1.merge(relatorio2, on="id_ticket", how="left")
df_base["texto"] = df_base["texto"].fillna("")

# Renomear previamente as colunas base para casar com o output final
df_base.rename(columns={
    "id_ticket": "ID",
    "data_abertura": "Data Abertura",
    "status": "Status",
    "modulo": "Módulo",
    "caminho": "Caminho",
    "tipo": "Tipo",
    "prioridade": "Prioridade",
    "tempo_gasto": "Tempo Gasto"
}, inplace=True)

# ==============================
# 5. SINÔNIMOS E 6. REGRAS
# ==============================

SINONIMOS_COLETA = [
    "não apareceu", "nao apareceu", "não aparecem", "nao aparecem",
    "não subiu", "nao subiu", "não subiram", "nao subiram",
    "não consta", "nao consta", "não constam", "nao constam",
    "não foi importada", "nao foi importada", "não foram importadas", "nao foram importadas",
    "não foi coletada", "nao foi coletada", "não foram coletadas", "nao foram coletadas",
    "não está aparecendo", "nao esta aparecendo", "não estão aparecendo", "nao estao aparecendo",
    "não está listada", "nao esta listada", "não estão listadas", "nao estao listadas",
    "não buscou", "nao buscou", "não buscaram", "nao buscaram",
    "não carregou", "nao carregou", "não carregaram", "nao carregaram",
    "não sincronizando", "nao sincronizando", "erro importação", "erro importacao"
]

REGRAS = [
    {"estrutura": "UniFiscal > Coleta > CTE", "keywords": ["cte", "ctes", "conhecimento transporte", "ct-e"], "peso": 6},
    {"estrutura": "UniFiscal > Coleta > Entrada", "keywords": ["entrada", "nota entrada", "nfe entrada"], "peso": 5},
    {"estrutura": "UniFiscal > Coleta > Saída", "keywords": ["saida", "nota saida", "nfe saida"], "peso": 5},
    {"estrutura": "UniFiscal > Coleta > Entrada", "keywords": ["nota", "notas", "nfe", "nf", "xml", "sped", "txt", "importação", "importacao", "upload", "chave de acesso"], "peso": 3},
    {"estrutura": "UniFiscal > Parametrizações > Atualização", "keywords": ["cst", "cfop", "ncm", "icms", "ipi", "parametrização", "configuracao", "tributação", "aliquota"], "peso": 7},
    {"estrutura": "UniFiscal > Parametrizações > Dúvidas", "keywords": ["duvida", "como configurar", "como parametrizar"], "peso": 4},
    {"estrutura": "UniFiscal > Status de Manifesto", "keywords": ["manifesto", "desconhecimento", "cancelada", "recusada", "notas recusadas"], "peso": 6},
    {"estrutura": "UniFiscal > Validações Trib. Entrada", "keywords": ["não está validando", "erro validação", "divergência"], "peso": 5},
    {"estrutura": "UniFiscal > Validações Trib. Saída", "keywords": ["não está validando", "erro validação", "divergência"], "peso": 5},
    {"estrutura": "UniFiscal > Cadastro de Empresa", "keywords": ["cnpj", "nova empresa", "incluir empresa"], "peso": 6},
    {"estrutura": "UniFiscal > Melhorias", "keywords": ["melhoria", "sugestao", "poderia"], "peso": 2},
    {"estrutura": "UniDP > Férias", "keywords": ["ferias", "férias", "gozo"], "peso": 5},
    {"estrutura": "UniDP > Permissões", "keywords": ["acesso", "usuario", "senha", "login", "bloqueado"], "peso": 6},
    {"estrutura": "UniDP > Upload > Atualização de Colaboradores", "keywords": ["upload", "colaborador"], "peso": 5},
    {"estrutura": "UniDP > Falhas em Integrações", "keywords": ["integracao", "api"], "peso": 5},
    {"estrutura": "UniDP > Falhas em Salvamento de Formulários", "keywords": ["nao salva", "erro salvar"], "peso": 5},
    {"estrutura": "UniDP > Falhas em Lançamento de Ponto", "keywords": ["ponto"], "peso": 5},
    {"estrutura": "UniDP > Falhas no Cálculo de Banco de Horas", "keywords": ["banco de horas"], "peso": 5},
    {"estrutura": "UniDP > Parametrizações > Rubricas de Holerite", "keywords": ["holerite", "rubrica"], "peso": 6}
]

# ==============================
# 7. FUNÇÕES AUXILIARES
# ==============================

def limpar_texto(texto):
    texto = str(texto).lower()
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')
    texto = re.sub(r"[^\w\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto

def classificar(texto, modulo):
    if pd.isna(texto) or texto == "":
        return ("Outros", "Outros")

    texto = limpar_texto(texto)
    modulo = str(modulo).strip()

    if "teste" in texto or "testes" in texto:
        return ("Teste de Funcionalidade", "Ticket Teste")

    melhor_match = None
    maior_score = 0

    for regra in REGRAS:
        partes = regra["estrutura"].split(" > ")
        if partes[0] != modulo:
            continue

        score = 0
        for palavra in regra["keywords"]:
            if palavra in texto:
                score += regra["peso"]

        if len(partes) > 1 and partes[1] == "Coleta":
            for s in SINONIMOS_COLETA:
                if s in texto:
                    score += 3
            if "nota" in texto and any(s in texto for s in SINONIMOS_COLETA):
                score += 6

        if score > maior_score:
            maior_score = score
            melhor_match = partes[1:]

    if melhor_match:
        if melhor_match[0] == "Coleta":
            if not any(p in texto for p in ["nfe", "cte", "saida", "saída"]):
                return ("Inserir XML", "Genérico")

        if len(melhor_match) == 1:
            return (melhor_match[0], melhor_match[0])
        else:
            return (melhor_match[0], melhor_match[1])

    return ("Outros", "Outros")

def converter_tempo_para_horas(tempo_str):
    if pd.isna(tempo_str) or not isinstance(tempo_str, str) or tempo_str.strip() == "":
        return 0.0
    tempo_str = tempo_str.lower()
    match_dias = re.search(r'(\d+)\s*dia', tempo_str)
    match_horas = re.search(r'(\d+)\s*hora', tempo_str)
    match_minutos = re.search(r'(\d+)\s*minuto', tempo_str)
    total_horas = 0.0
    if match_dias:
        total_horas += int(match_dias.group(1)) * 24.0
    if match_horas:
        total_horas += float(match_horas.group(1))
    if match_minutos:
        total_horas += float(match_minutos.group(1)) / 60.0
    return round(total_horas, 2)

# ==============================
# 8. MOTOR DE SLA (BLINDADO COM NLP E IDENTIFICADOR DE REGRAS)
# ==============================

def avaliar_sla(modulo, categoria, subcategoria, tempo_horas):
    piso_h = np.nan
    teto_h = np.nan

    def norm(texto):
        if pd.isna(texto): return ""
        t = str(texto).strip().lower()
        t = unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode('utf-8')
        return t

    mod_n = norm(modulo)
    cat_n = norm(categoria)
    sub_n = norm(subcategoria)

    # Mapeamento
    if mod_n == "unifiscal":
        if cat_n == "inserir xml" or sub_n == "generico":
            piso_h, teto_h = 2.0, 24.0
        elif cat_n == "cadastro de empresa":
            piso_h, teto_h = 3.0, 24.0
        elif cat_n == "parametrizacoes" and sub_n == "duvidas":
            piso_h, teto_h = 6.0, 24.0
        elif cat_n == "parametrizacoes" and sub_n == "atualizacao":
            piso_h, teto_h = 24.2, 120.0
        elif cat_n == "status de manifesto":
            piso_h, teto_h = 153.6, 168.0
        elif cat_n in ["validacoes trib. entrada", "validacoes trib entrada", "validacoes trib. saida", "validacoes trib saida"]:
            piso_h, teto_h = 3.0, 24.0
        elif cat_n == "coleta": 
            piso_h, teto_h = 148.8, 168.0

    elif mod_n == "unidp":
        if cat_n == "ferias" or sub_n == "adicionar opcoes de ferias":
            piso_h, teto_h = 2.0, 24.0
        elif cat_n == "parametrizacoes" and sub_n == "rubricas de holerite":
            piso_h, teto_h = 2.0, 24.0
        elif cat_n == "permissoes":
            piso_h, teto_h = 1.0, 24.0
        elif cat_n == "upload" and sub_n == "atualizacao de colaboradores":
            piso_h, teto_h = 2.0, 24.0
        elif cat_n in ["falhas em integracoes", "falhas em salvamento de formularios", "falhas em lancamento de ponto"]:
            piso_h, teto_h = 36.0, 72.0
        elif cat_n == "falhas no calculo de banco de horas":
            piso_h, teto_h = 48.0, 72.0

    # 🔥 IDENTIFICADOR DE REGRA (O CORAÇÃO DA ASSISTÊNCIA HÍBRIDA)
    # Se o sistema achou limites, ou se é a regra especial "Melhorias", ele SABE o que fazer.
    tem_regra = False
    if (not pd.isna(piso_h) and not pd.isna(teto_h)) or (mod_n == "unifiscal" and cat_n == "melhorias"):
        tem_regra = True

    # Definição do Status Analítico
    if tempo_horas == 0.0:
        status = "Sem Registro de Tempo"
    elif mod_n == "unifiscal" and cat_n == "melhorias":
        status = "Prazo Não Aplicável"
    elif not tem_regra:
        status = "SLA Não Definido"
    elif tempo_horas > teto_h:
        status = "Acima do Teto (Nota: Tempo Corrido Bruto)"
    elif tempo_horas <= piso_h:
        status = "Abaixo do Piso (Alta Velocidade)"
    else:
        status = "Dentro do Prazo Nominal"

    # Cálculo numérico %
    if not pd.isna(teto_h) and teto_h > 0:
        consumo_pct = np.nan if tempo_horas == 0.0 else round(tempo_horas / teto_h, 4) 
    else:
        consumo_pct = np.nan

    return pd.Series([status, piso_h, teto_h, consumo_pct, tem_regra])

# ==============================
# 🔥 LÓGICA INCREMENTAL (ATUALIZAÇÃO HÍBRIDA)
# ==============================

path_final = "relatorio_classificado.xlsx"

if os.path.exists(path_final):
    try:
        df_existente = pd.read_excel(path_final)
        df_existente["ID"] = df_existente["ID"].astype(str).str.strip()
        
        # 1. Isolamos TODAS as suas edições manuais (inclusive SLAs e Módulo se editado)
        colunas_manuais = ["ID"]
        for col in ["Módulo", "Categoria", "Subcategoria", "Causa Raíz", "Título", "SLA Piso", "SLA Teto", "% Consumo SLA", "Status SLA"]:
            if col in df_existente.columns: colunas_manuais.append(col)
        df_manuais = df_existente[colunas_manuais]

        # 2. Tickets antigos que sumiram do CSV
        df_historico_ausente = df_existente[~df_existente["ID"].isin(df_base["ID"])].copy()

        # 3. Mescla protegendo as colunas
        df_processar = df_base.merge(df_manuais, on="ID", how="left", suffixes=('_orig', '_man'))
        
        # Se você corrigiu o Módulo manualmente, o algoritmo agora te respeita
        if "Módulo_man" in df_processar.columns:
            df_processar["Módulo"] = df_processar["Módulo_man"].fillna(df_processar["Módulo_orig"])
            df_processar.drop(columns=["Módulo_orig", "Módulo_man"], inplace=True)
        elif "Módulo_orig" in df_processar.columns:
            df_processar.rename(columns={"Módulo_orig": "Módulo"}, inplace=True)

        # 4. Classificamos APENAS os vazios (os 100% novos)
        mask_novos = df_processar["Categoria"].isna()
        if mask_novos.any():
            df_processar.loc[mask_novos, ["Categoria", "Subcategoria"]] = df_processar[mask_novos].apply(
                lambda row: pd.Series(classificar(row["texto"], row["Módulo"])), axis=1
            ).values
            
            for col in ["Causa Raíz", "Título"]:
                if col in df_processar.columns: df_processar.loc[mask_novos, col] = ""

        df_processar = pd.concat([df_historico_ausente, df_processar], ignore_index=True)

    except Exception as e:
        print(f"⚠️ Erro ao processar o histórico: {e}. Gerando tudo do zero.")
        df_processar = df_base.copy()
        df_processar[["Categoria", "Subcategoria"]] = df_processar.apply(
            lambda row: pd.Series(classificar(row["texto"], row["Módulo"])), axis=1
        )
        for col in ["Causa Raíz", "Título"]: df_processar[col] = ""
else:
    df_processar = df_base.copy()
    df_processar[["Categoria", "Subcategoria"]] = df_processar.apply(
        lambda row: pd.Series(classificar(row["texto"], row["Módulo"])), axis=1
    )
    for col in ["Causa Raíz", "Título"]: df_processar[col] = ""

# ==============================
# 🔥 APLICAÇÃO INTELIGENTE DO SLA (RESPEITA EDIÇÃO MANUAL)
# ==============================

# Cria colunas de SLA vazias caso seja a primeira vez rodando
for col in ["SLA Piso", "SLA Teto", "% Consumo SLA", "Status SLA"]:
    if col not in df_processar.columns:
        df_processar[col] = np.nan

if not df_processar.empty:
    df_processar["Tempo Gasto (Horas)"] = df_processar["Tempo Gasto"].apply(converter_tempo_para_horas)

    # O motor calcula o cenário para todos
    engine_results = df_processar.apply(
        lambda row: avaliar_sla(row["Módulo"], row["Categoria"], row["Subcategoria"], row["Tempo Gasto (Horas)"]),
        axis=1
    )
    df_processar[["Eng_Status", "Eng_Piso", "Eng_Teto", "Eng_Consumo", "Tem_Regra"]] = engine_results

    # REGRA 1: Onde o motor conhece a regra, ele preenche pra você (ajuda a automatizar o que você digitou)
    mask_regra = df_processar["Tem_Regra"] == True
    df_processar.loc[mask_regra, "Status SLA"] = df_processar.loc[mask_regra, "Eng_Status"]
    df_processar.loc[mask_regra, "SLA Piso"] = df_processar.loc[mask_regra, "Eng_Piso"]
    df_processar.loc[mask_regra, "SLA Teto"] = df_processar.loc[mask_regra, "Eng_Teto"]
    df_processar.loc[mask_regra, "% Consumo SLA"] = df_processar.loc[mask_regra, "Eng_Consumo"]

    # REGRA 2: Onde o motor NÃO conhece a regra e NÃO existe SLA histórico manual
    # Ele acusa "SLA Não Definido". (Onde existir manual, ele não toca e preserva seu trabalho!)
    mask_sem_regra_sem_hist = (~mask_regra) & df_processar["SLA Piso"].isna()
    df_processar.loc[mask_sem_regra_sem_hist, "Status SLA"] = "SLA Não Definido"

# ==============================
# 10. EXPORTAÇÃO ESTRITA E ORDENADA
# ==============================

colunas_finais_desejadas = [
    "ID", "Data Abertura", "Status", "Módulo", "Categoria", "Subcategoria",
    "SLA Piso", "SLA Teto", "% Consumo SLA", "Status SLA", "Tempo Gasto", 
    "Causa Raíz", "Caminho", "Tipo", "Título", "Prioridade", "Tempo Gasto (Horas)"
]

df_final = df_processar[[col for col in colunas_finais_desejadas if col in df_processar.columns]]
df_final = df_final.drop_duplicates(subset=["ID"], keep="last")
df_final.to_excel(path_final, index=False)

print("✅ Pipeline executado! Motor Híbrido ativado: preenche sozinho o que sabe, preserva sua edição no que não sabe.")