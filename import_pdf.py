import os
from database import aggiungi_paper

CARTELLA_PDF = "pdf_dataset"

print(f"Scansiono la cartella '{CARTELLA_PDF}'...")

aggiunti = 0

for nome_file in os.listdir(CARTELLA_PDF):
    
    if nome_file.endswith(".pdf"):
        percorso_completo = os.path.join(CARTELLA_PDF, nome_file)
        
        titolo = nome_file.replace(".pdf", "")
        
        successo = aggiungi_paper(titolo, percorso_completo)
        
        if successo:
            print(f" Aggiunto: {titolo}")
            aggiunti += 1
        else:
            print(f" Saltato (già presente): {titolo}")

print(f"\nAggiunti {aggiunti} nuovi paper nel database.")