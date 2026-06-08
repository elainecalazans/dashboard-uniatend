import pandas as pd
from data_utils import carregar_textos, carregar_tickets
from text_cleaner import consolidar_historico
from auditor import _calcular_frt

df_tickets = carregar_tickets()
df_textos = carregar_textos()
df_hist = consolidar_historico(df_textos)
hist_idx = df_hist.set_index("id_ticket")["historico"].to_dict()

alvos = ["JEISY", "GUILHERME LOPES"]
for _, ticket in df_tickets.iterrows():
    resp = str(ticket.get("responsavel", "")).upper()
    if not any(a in resp for a in alvos):
        continue
    tid = str(ticket["id_ticket"]).strip()
    historico = hist_idx.get(tid, [])
    frt = _calcular_frt(historico)
    if frt is None:
        msgs_c = [h for h in historico if h["papel"] == "cliente"]
        msgs_t = [h for h in historico if h["papel"] == "tecnico"]
        print(f"Ticket {tid} | {resp} | cliente={len(msgs_c)} tecnico={len(msgs_t)}")
        for h in historico[:5]:
            print(f"  {h['papel'].upper()} | {h['timestamp']} | {repr(h['texto'][:80])}")
        print()
