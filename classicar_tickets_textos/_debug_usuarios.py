import pandas as pd
from data_utils import carregar_textos

df = carregar_textos()
df.columns = df.columns.str.strip()
df["id_ticket"] = df["id_ticket"].astype(str).str.strip()

# tickets de JEISY com tecnico=0 e tickets de GUILHERME LOPES com cliente=0
tickets_jeisy = ["456", "479", "429", "427", "433", "431"]
tickets_guilherme = ["554", "553", "497", "566", "330", "329", "328"]

print("=== JEISY - usuarios brutos ===")
for tid in tickets_jeisy:
    grupo = df[df["id_ticket"] == tid]
    print(f"\nTicket {tid}:")
    for _, row in grupo.iterrows():
        usuario = str(row.get("usuario", row.get("nome", "??"))).strip()
        texto = str(row.get("texto", ""))[:60]
        print(f"  usuario={repr(usuario)} | {texto}")

print("\n=== GUILHERME LOPES - usuarios brutos ===")
for tid in tickets_guilherme:
    grupo = df[df["id_ticket"] == tid]
    print(f"\nTicket {tid}:")
    for _, row in grupo.iterrows():
        usuario = str(row.get("usuario", row.get("nome", "??"))).strip()
        texto = str(row.get("texto", ""))[:60]
        print(f"  usuario={repr(usuario)} | {texto}")
