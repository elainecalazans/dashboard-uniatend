# UniATEND — Pipeline de Classificação + Dashboard Gerencial

Pipeline de auditoria de tickets de suporte com dashboard Streamlit e envio automático de relatório diário por e-mail.

---

## Estrutura

```
dashboard_uniatend/
├── classicar_tickets_textos/   # pipeline (classificação, SLA, auditoria, e-mail)
│   ├── app.py                  # entry point do pipeline
│   ├── tickets.csv             # fonte de dados — NÃO versionado, colocar manualmente
│   └── textos.csv              # histórico de interações — NÃO versionado, colocar manualmente
├── relatorio_dashboard/        # dashboard Streamlit
│   └── app.py                  # entry point do dashboard
├── sla_rules.json              # regras de SLA por Módulo > Categoria > Subcategoria
├── config.json                 # metas mensais de SLA e baseline histórico
├── .env                        # credenciais — NÃO versionado, criar manualmente (ver abaixo)
└── requirements.txt
```

---

## Regras de Mensuração e Indicadores

### Os 4 Mandamentos do Playbook

Toda auditoria de ticket verifica estes critérios, derivados do Playbook UniDNA v1.0:

| # | Mandamento | Regra |
|---|-----------|-------|
| 1 | **FRT ≤ 2h** | Primeira resposta real do técnico em até 2 horas após a abertura do ticket |
| 2 | **Zero Zumbis** | Nenhum ticket com período de espera do cliente superior a 5 dias corridos sem resposta do técnico |
| 3 | **Regra dos 24 Dias** | Tickets com Categoria = "Melhorias" ou Tipo = "Melhoria" devem ter atualização a cada 24 dias enquanto abertos |
| 4 | **Encerramento com Conteúdo** | A última mensagem do técnico não pode ser genérica (ex.: "resolvido", "ok", "pronto") sem explicação técnica real |

> Tickets cancelados são excluídos da auditoria. Tickets com Tipo = "Melhoria" são excluídos do Risco Zumbi e dos Desvios de SLA.

---

### Critérios de Conformidade (OKR Mensal)

A conformidade de um ticket é avaliada **apenas sobre tickets concluídos no mês**. Um ticket é considerado **conforme** quando atende simultaneamente os 4 critérios abaixo:

| Critério | Condição para aprovação | Observação |
|----------|------------------------|------------|
| FRT ≤ 2h | `FRT OK = "Sim"` | Neutro (não reprova) quando `"Sem dados"` ou `"Abertura Administrativa"` |
| Risco Zumbi | `Risco Zumbi = "Não"` | Gap é medido apenas nos períodos em que o **cliente aguardou** o técnico |
| Resolução Genérica | `Resolução Genérica = "Não"` | Verifica última mensagem e, se genérica, a penúltima — técnico que envia explicação técnica e depois envia "Ticket finalizado." não é reprovado |
| Link ClickUp | `Link ClickUp ≠ "Ausente"` | Somente para tickets onde o técnico menciona "time de dev" / "tratativa de dev" |

**Meta:** ≥ 90% de conformidade.

> **Causa Raíz está fora dos critérios de conformidade** — é acompanhada como indicador de progressão separado, sem meta numérica por enquanto.

---

### Indicadores do Report Mensal

O e-mail de Auditoria Mensal de Conformidade (`python app.py --auditoria-mensal`) exibe 6 indicadores principais:

#### 1. Conformidade
- **Base:** tickets concluídos no mês corrente
- **Fórmula:** `tickets conformes / total de tickets concluídos no mês`
- **Meta:** ≥ 90% (verde), < 70% (vermelho), entre 70–90% (amarelo)

#### 2. Não Conformes
- Contagem absoluta de tickets concluídos no mês que falharam em ao menos 1 critério
- Reprovações múltiplas em um mesmo ticket contam como 1 ticket não conforme

#### 3. Tempo Mediano de Resolução
- **Base:** `Tempo Gasto (Horas)` dos tickets concluídos no mês
- **Métrica principal:** mediana — mais representativa para suporte, onde poucos tickets de longa duração distorceriam a média
- **Métrica secundária:** média — exibida abaixo como referência
- Exibido em minutos, horas ou dias conforme magnitude

#### 4. Melhorias
- **Fórmula:** `tickets com Tipo = "Melhoria" / total de tickets do mês`
- **Base:** todos os tickets do mês (abertos e concluídos)
- Indica proporção da demanda de evolução de produto no período

#### 5. Erro → Dev
- **Fórmula:** `tickets com Tipo = "Erro" e Link ClickUp ≠ "-" / total de tickets do mês`
- `Link ClickUp ≠ "-"` significa que o técnico mencionou o time de desenvolvimento no atendimento (com ou sem link preenchido)
- Mede a taxa de chamados de erro que exigiram escalada ao time de desenvolvimento

#### 6. Causa Raíz
- Exibe o número de causas raíz distintas identificadas no mês e o total de tickets com causa preenchida
- Alimentado por preenchimento manual no Excel ou por detecção automática (ver seção abaixo)
- Quando vazio: aguardando adoção dos textos padronizados de encerramento pelo time

---

### Recorrência (Report Mensal)

Seção complementar calculada sobre os **últimos 30 dias** a partir da data de execução:

| Métrica | Definição |
|---------|-----------|
| **Recorrência por Categoria** | % de tickets cuja Categoria aparece em 2 ou mais tickets no período. Indica padrões de demanda que se repetem. |
| **Recorrência por Causa Raíz** | % de tickets com causa raíz preenchida cuja causa aparece em 2 ou mais tickets no período. Indica problemas sistêmicos não resolvidos na origem. |

Cada métrica é acompanhada de um gráfico de barras com a distribuição por categoria/causa e listagem detalhada dos tickets envolvidos.

---

### Chamados por Causa Raíz

Breakdown por causa raíz identificada nos tickets do mês. Aparece no e-mail mensal somente quando há dados preenchidos.

A causa raíz pode ser registrada de duas formas:
1. **Preenchimento manual** — editando a coluna `Causa Raíz` diretamente no `relatorio_classificado.xlsx` antes da próxima execução do pipeline (o valor é preservado nas execuções seguintes)
2. **Detecção automática** — `classifier.py` identifica causas pelo texto das mensagens do técnico usando palavras-chave definidas em `REGRAS_CAUSA_RAIZ`

> Tickets históricos raramente são detectados automaticamente (linguagem informal). A detecção funciona progressivamente conforme o time adota os textos padronizados de encerramento.

**Causas mapeadas atualmente:**
- Coleta Saídas sem AutXML — Parametrização ERP Cliente → keyword: `autxml`
- Entradas — Consumo Indevido — Parâmetro = Integral → `consumo indevido` + `configuramos` + `periodo noturno` (exclui `certificado digital`)
- Entradas — Consumo Indevido — Parâmetro = Noturno → `consumo indevido` + `certificado digital`

---

### Separação Cliente / Técnico

O campo `usuario` do `textos.csv` identifica quem enviou cada mensagem. O pipeline separa automaticamente:

- **Técnico:** usuário cujo nome está na lista `TECNICOS` em `text_cleaner.py`
- **Cliente:** qualquer outro usuário

Casos especiais:
- **Abertura Administrativa:** técnico abriu o ticket em nome do cliente — `FRT` fica como `"Abertura Administrativa"` (neutro na conformidade)
- **Proxy:** todas as mensagens registradas por um único usuário não-técnico (ex.: gestor registrando por um cliente) — tratado da mesma forma

**Técnicos cadastrados** (atualizar `text_cleaner.py` ao mudar o time):
- GUILHERME LOPES PIRES DA SILVA
- GUILHERME HENRIQUE PORTO DOS SANTOS
- JEISY GONCALVES DE SOUSA
- RAFAEL RODRIGUES VIANNA
- ANDRESSA TELES RODRIGUES

---

### SLA

Regras definidas em `sla_rules.json` por `Módulo > Categoria > Subcategoria`, com piso e teto em horas.

| Status SLA | Significado |
|------------|-------------|
| Dentro do Prazo | Tempo gasto ≤ teto |
| Acima do Teto | Tempo gasto > teto — conta como desvio |
| Prazo Não Aplicável | Tipo = "Melhoria" — excluído do controle de SLA |
| SLA Não Definido | Combinação de Módulo/Categoria/Subcategoria sem regra cadastrada |
| Sem Registro de Tempo | Tempo Gasto em branco |

O e-mail diário e o mensal incluem a seção **Desvios de SLA**, com tickets concluídos no mês acima do teto e tickets abertos que já estouraram, agrupados por Módulo › Categoria.

---

## Pré-requisitos

- Python **3.11** ou superior (desenvolvido e testado em 3.13.2)
- Acesso à internet para envio de e-mail via Gmail SMTP (porta 587)

---

## Instalação

```bash
# 1. Clone o repositório
git clone <url-do-repositorio>
cd dashboard_uniatend

# 2. Crie e ative um ambiente virtual
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# 3. Instale as dependências
pip install -r requirements.txt
```

---

## Configuração

### 1. Arquivo `.env`

Copie o arquivo de exemplo e preencha com as credenciais reais:

```bash
cp .env.example .env
```

Variáveis necessárias:

| Variável    | Descrição                                                                 | Exemplo                              |
|-------------|---------------------------------------------------------------------------|--------------------------------------|
| `SMTP_USER` | Conta Gmail usada para enviar o relatório                                 | `setor@empresa.com`                  |
| `SMTP_PASS` | **Senha de app** do Google — não a senha da conta¹                       | `xxxx xxxx xxxx xxxx`                |
| `REPORT_TO`      | Destinatário(s) do relatório — separar múltiplos por `,` ou `;`      | `lider@empresa.com,gestor@empresa.com`   |
| `DASHBOARD_URL`  | URL do dashboard Streamlit — aparece como link no rodapé do e-mail   | `http://192.168.62.243:8501/`            |

> ¹ Como gerar a senha de app: Conta Google → Segurança → Verificação em duas etapas → **Senhas de app**.

### 2. Arquivos de dados

Coloque os arquivos exportados do sistema na pasta `classicar_tickets_textos/`:

```
classicar_tickets_textos/tickets.csv
classicar_tickets_textos/textos.csv
```

Esses arquivos não estão no repositório (dados sensíveis). Exportá-los do sistema de origem antes de rodar.

---

## Como executar

### Pipeline (classificação + auditoria + e-mail)

```bash
cd classicar_tickets_textos
python app.py
```

O pipeline irá:
1. Ler e classificar os tickets
2. Calcular SLA por ticket
3. Gerar `relatorio_classificado.xlsx` e `relatorio_auditoria.xlsx` em `relatorio_dashboard/`
4. Enviar o relatório de auditoria por e-mail automaticamente

### Dashboard Streamlit

```bash
cd relatorio_dashboard
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

O parâmetro `--server.address 0.0.0.0` permite acesso de outras máquinas na mesma rede.
Acesse pelo navegador em: `http://<ip-do-servidor>:8501`

---

## Rodar como serviço no servidor (Linux)

Para manter o dashboard sempre disponível, crie um serviço systemd:

```bash
sudo nano /etc/systemd/system/uniatend-dashboard.service
```

Conteúdo do arquivo:

```ini
[Unit]
Description=UniATEND Dashboard Streamlit
After=network.target

[Service]
User=<usuario-do-servidor>
WorkingDirectory=/caminho/para/dashboard_uniatend/relatorio_dashboard
ExecStart=/caminho/para/.venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Ative e inicie:

```bash
sudo systemctl daemon-reload
sudo systemctl enable uniatend-dashboard
sudo systemctl start uniatend-dashboard
sudo systemctl status uniatend-dashboard   # verificar se subiu
```

Para agendar o pipeline diariamente (ex.: todo dia às 7h):

```bash
crontab -e
```

Adicione:

```cron
0 7 * * * /caminho/para/.venv/bin/python /caminho/para/dashboard_uniatend/classicar_tickets_textos/app.py >> /var/log/uniatend-pipeline.log 2>&1
```

---

## Portas e firewall

| Serviço   | Porta padrão |
|-----------|-------------|
| Dashboard | 8501        |

Libere a porta 8501 no firewall do servidor para acesso pela VPN.

---

## Dependências principais

| Pacote      | Uso                                      |
|-------------|------------------------------------------|
| pandas      | manipulação de dados                     |
| openpyxl    | leitura/escrita de arquivos Excel        |
| streamlit   | dashboard web interativo                 |
| plotly      | gráficos                                 |
| premailer   | inlining de CSS para compatibilidade de e-mail |
| numpy       | cálculos numéricos                       |
