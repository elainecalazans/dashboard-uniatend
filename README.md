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

Crie o arquivo `.env` na raiz do projeto com as credenciais de e-mail:

```env
SMTP_USER=seu-email@gmail.com
SMTP_PASS=sua-senha-de-app-gmail
REPORT_TO=lider@empresa.com,outro@empresa.com
```

> **SMTP_PASS** deve ser uma **senha de app** do Google (não a senha da conta).
> Acesse: Conta Google → Segurança → Verificação em duas etapas → Senhas de app.
>
> **REPORT_TO** aceita um ou múltiplos endereços separados por vírgula ou ponto-e-vírgula.

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
