from __future__ import annotations

import re
import unicodedata
import pandas as pd

SINONIMOS_COLETA: list[str] = [
    "nao apareceu", "nao aparecem", "nao subiu", "nao subiram",
    "nao consta", "nao constam", "nao foi importada", "nao foram importadas",
    "nao foi coletada", "nao foram coletadas", "nao esta aparecendo",
    "nao estao aparecendo", "nao esta listada", "nao estao listadas",
    "nao buscou", "nao buscaram", "nao carregou", "nao carregaram",
    "nao sincronizando", "erro importacao",
]

REGRAS: list[dict] = [
    {"estrutura": "UniFiscal > Coleta > CTE",       "keywords": ["cte", "ctes", "conhecimento transporte", "ct-e"], "peso": 6},
    {"estrutura": "UniFiscal > Coleta > Entrada",   "keywords": ["entrada", "nota entrada", "nfe entrada"], "peso": 5},
    {"estrutura": "UniFiscal > Coleta > Saída",     "keywords": ["saida", "nota saida", "nfe saida"], "peso": 5},
    {"estrutura": "UniFiscal > Coleta > Entrada",   "keywords": ["nota", "notas", "nfe", "nf", "xml", "sped", "txt", "importação", "importacao", "upload", "chave de acesso"], "peso": 3},
    {"estrutura": "UniFiscal > Parametrizações > Atualização", "keywords": ["cst", "cfop", "ncm", "icms", "ipi", "parametrização", "configuracao", "tributação", "aliquota"], "peso": 7},
    {"estrutura": "UniFiscal > Parametrizações > Dúvidas",     "keywords": ["duvida", "como configurar", "como parametrizar"], "peso": 4},
    {"estrutura": "UniFiscal > Status de Manifesto",           "keywords": ["manifesto", "desconhecimento", "cancelada", "recusada", "notas recusadas", "foi feito o desconhecimento da operacao"], "peso": 6},
    {"estrutura": "UniFiscal > Validações Trib. Entrada",      "keywords": ["nao esta validando", "erro validacao", "divergencia", "entrada", "nfe entrada", "nota entrada"], "peso": 5},
    {"estrutura": "UniFiscal > Validações Trib. Saída",        "keywords": ["nao esta validando", "erro validacao", "divergencia", "saida", "nfe saida", "nota saida"], "peso": 5},
    {"estrutura": "UniFiscal > Cadastro de Empresa",           "keywords": ["cnpj", "nova empresa", "incluir empresa"], "peso": 6},
    {"estrutura": "UniFiscal > Melhorias",                     "keywords": ["melhoria", "sugestao", "poderia"], "peso": 2},
    {"estrutura": "UniDP > Férias",                            "keywords": ["ferias", "gozo"], "peso": 5},
    {"estrutura": "UniDP > Permissões",                        "keywords": ["acesso", "usuario", "senha", "login", "bloqueado"], "peso": 6},
    {"estrutura": "UniDP > Upload > Atualização de Colaboradores", "keywords": ["upload", "colaborador"], "peso": 5},
    {"estrutura": "UniDP > Falhas em Integrações",             "keywords": ["integracao", "api"], "peso": 5},
    {"estrutura": "UniDP > Falhas em Salvamento de Formulários", "keywords": ["nao salva", "erro salvar"], "peso": 5},
    {"estrutura": "UniDP > Falhas em Lançamento de Ponto",     "keywords": ["ponto"], "peso": 5},
    {"estrutura": "UniDP > Falhas no Cálculo de Banco de Horas", "keywords": ["banco de horas"], "peso": 5},
    {"estrutura": "UniDP > Parametrizações > Rubricas de Holerite", "keywords": ["holerite", "rubrica"], "peso": 6},
]


def limpar_texto(texto: str) -> str:
    texto = str(texto).lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("utf-8")
    texto = re.sub(r"[^\w\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def classificar(texto: str, modulo: str) -> tuple[str, str]:
    if pd.isna(texto) or texto == "":
        return ("Outros", "Outros")

    texto_limpo = limpar_texto(texto)
    modulo = str(modulo).strip()

    if "teste" in texto_limpo or "testes" in texto_limpo:
        return ("Teste de Funcionalidade", "Ticket Teste")

    melhor_match: list[str] | None = None
    maior_score = 0

    for regra in REGRAS:
        partes = regra["estrutura"].split(" > ")
        if partes[0] != modulo:
            continue

        score = sum(regra["peso"] for kw in regra["keywords"] if kw in texto_limpo)

        if len(partes) > 1 and partes[1] == "Coleta":
            score += sum(3 for s in SINONIMOS_COLETA if s in texto_limpo)
            if "nota" in texto_limpo and any(s in texto_limpo for s in SINONIMOS_COLETA):
                score += 6

        if score > maior_score:
            maior_score = score
            melhor_match = partes[1:]

    if melhor_match:
        if melhor_match[0] == "Coleta" and not any(p in texto_limpo for p in ["nfe", "cte", "saida"]):
            return ("Inserir XML", "Genérico")
        cat = melhor_match[0]
        sub = melhor_match[1] if len(melhor_match) > 1 else cat
        return (cat, sub)

    return ("Outros", "Outros")
