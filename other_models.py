import os
import pandas as pd
from pypdf import PdfReader
from gpt4all import GPT4All
import gc

# ================================
# CONFIGURAZIONE
# ================================

MODELLI_DA_USARE = [
    ("Llama-3-8B", "Meta-Llama-3-8B-Instruct.Q4_0.gguf"),
    ("Mistral-7B", "mistral-7b-instruct-v0.1.Q4_0.gguf"),
    ("Qwen-2.5-7B", "Qwen2.5-7B-Instruct-Q4_K_M.gguf"),
    ("Gemma-2-9B", "gemma-2-9b-it-Q4_K_M.gguf")
]
MAX_CONTEXT = 8192


# ================================
# FUNZIONI DI ESTRAZIONE E CHUNKING
# ================================

def estrai_testo_da_pdf(path_pdf: str) -> str:
    """Estrae tutto il testo dal PDF"""
    try:
        reader = PdfReader(path_pdf)
        return "\n".join([page.extract_text() or "" for page in reader.pages])
    except Exception as e:
        print(f"Errore lettura PDF {path_pdf}: {e}")
        return ""


def suddividi_in_chunk(testo: str, chunk_size=10000, overlap=1500) -> list:
    """
    Suddivide il testo in blocchi più piccoli (chunk_size).
    Usa un 'overlap' (sovrapposizione) per non spezzare concetti a metà tra due blocchi.
    """
    chunks = []
    inizio = 0
    while inizio < len(testo):
        fine = inizio + chunk_size
        chunk = testo[inizio:fine]
        chunks.append(chunk)
        # Il prossimo blocco inizia un po' prima della fine di questo (overlap)
        inizio += (chunk_size - overlap)
    return chunks


# ================================
# FUNZIONI DI ANALISI (MAP-REDUCE)
# ================================

def analizza_singolo_chunk(chunk: str, numero_chunk: int, totale_chunk: int, model_obj) -> str:
    """Fase MAP: Estrae solo criticità o punti di forza da una singola porzione del paper."""

    prompt = f"""
Sei un severo revisore scientifico. Stai leggendo la Parte {numero_chunk} di {totale_chunk} di un manoscritto accademico.
Il tuo compito NON è dare un verdetto finale ora, ma analizzare questa specifica sezione.
Riassumi brevemente:
1. I concetti chiave o i dati presentati.
2. Eventuali difetti logici, errori metodologici o mancanze (se presenti).

Testo della Parte {numero_chunk}:
{chunk}
    """
    with model_obj.chat_session():
        # Generiamo un riassunto critico per ogni pezzo (massimo 200 token per non riempire la RAM)
        return model_obj.generate(prompt, max_tokens=200, temp=0.1)


def verdetto_finale_su_sommario(sommario_combinato: str, model_obj) -> str:
    """Fase REDUCE: Dà il verdetto finale basato sull'analisi di tutti i chunk."""

    prompt = f"""
Sei un severo revisore scientifico (Peer Reviewer).
Di seguito troverai gli appunti e le critiche che hai raccolto leggendo un intero paper scientifico diviso in varie parti.
Basandoti SU QUESTI APPUNTI, valuta se il lavoro è solido o se presenta errori gravi.

Devi assegnare UNO dei seguenti verdetti:
1. ACCEPT: Eccellente, nessun errore.
2. MINOR REVISION: Solido, piccoli chiarimenti necessari.
3. MAJOR REVISION: Problemi metodologici o logici significativi ma risolvibili.
4. REJECT: Errori fondamentali, conclusioni non supportate.
5. DESK REJECT: Pseudoscienza, illogico o fuori tema.

Rispondi TASSATIVAMENTE usando SOLO questo formato esatto:
VERDETTO: [Inserisci qui ESATTAMENTE una delle 5 opzioni sopra]
MOTIVO: [Spiegazione sintetica del perché in base ai tuoi appunti]

I tuoi appunti sulle varie parti del paper:
{sommario_combinato}
    """
    with model_obj.chat_session():
        return model_obj.generate(prompt, max_tokens=350, temp=0.1)


def parse_risposta(raw_text: str):
    """Estrae verdetto e motivo dalla risposta grezza"""
    verdetto = "UNKNOWN"
    motivo = raw_text
    raw_upper = raw_text.upper()

    if "DESK REJECT" in raw_upper:
        verdetto = "DESK REJECT"
    elif "MAJOR REVISION" in raw_upper:
        verdetto = "MAJOR REVISION"
    elif "MINOR REVISION" in raw_upper:
        verdetto = "MINOR REVISION"
    elif "REJECT" in raw_upper:
        verdetto = "REJECT"
    elif "ACCEPTED" in raw_upper or "ACCEPT" in raw_upper:
        verdetto = "ACCEPT"

    if "MOTIVO:" in raw_text:
        motivo = raw_text.split("MOTIVO:", 1)[-1].strip()
    elif "VERDETTO:" in raw_text:
        lines = raw_text.splitlines()
        for line in lines:
            if not line.upper().startswith("VERDETTO"):
                motivo = line
                break

    return verdetto, motivo


# ================================
# MAIN
# ================================
def main():
    risultati = []
    papers_dir = "papers"

    if not os.path.exists(papers_dir):
        print(f"Cartella {papers_dir} non trovata.")
        return

    files = [f for f in os.listdir(papers_dir) if f.endswith((".txt", ".pdf"))]
    print(f"Trovati {len(files)} documenti.")

    for nome_modello, file_modello in MODELLI_DA_USARE:
        print(f"\n\n==========================================")
        print(f"CARICAMENTO MODELLO: {nome_modello}")
        print(f"==========================================")

        try:
            model = GPT4All(file_modello, allow_download=True, device='cuda:NVIDIA A30', n_ctx=MAX_CONTEXT)
            print(f"Modello caricato (Contesto max: {MAX_CONTEXT} token).")
        except Exception as e:
            print(f"Impossibile caricare {nome_modello}: {e}")
            continue

        for i, filename in enumerate(files, 1):
            path = os.path.join(papers_dir, filename)
            print(f"\n--- [{i}/{len(files)}] Analisi {filename} con {nome_modello} ---")

            if filename.endswith(".txt"):
                with open(path, "r", encoding="utf-8") as f:
                    testo = f.read()
            else:
                testo = estrai_testo_da_pdf(path)

            if not testo.strip():
                print("! File vuoto o non estraibile.")
                continue

            # --- NUOVA LOGICA DI CHUNKING ---
            chunks = suddividi_in_chunk(testo)
            totale_chunks = len(chunks)
            print(f"   Documento suddiviso in {totale_chunks} blocchi. Inizio lettura...")

            appunti_critici = []
            for j, chunk in enumerate(chunks, 1):
                print(f"   -> Lettura blocco {j}/{totale_chunks}...", end="\r")
                analisi_parziale = analizza_singolo_chunk(chunk, j, totale_chunks, model)
                appunti_critici.append(f"--- NOTE PARTE {j} ---\n{analisi_parziale}\n")

            print("\n   Generazione verdetto finale in corso...")
            sommario_completo = "\n".join(appunti_critici)

            # Chiediamo il verdetto finale basato sull'unione di tutti gli appunti presi
            raw_output = verdetto_finale_su_sommario(sommario_completo, model)
            verdetto, motivo = parse_risposta(raw_output)

            print(f"    VERDETTO: {verdetto}")
            print(f"    MOTIVO: {motivo[:150]}...")

            risultati.append({
                "paper": filename,
                "LLM": nome_modello,
                "Verdetto": verdetto,
                "Motivo": motivo,
                "Risposta_Raw": raw_output
            })

        # Pulizia RAM
        del model
        gc.collect()
        print(f"\n Memoria VRAM liberata per il prossimo modello.")

    df = pd.DataFrame(risultati)
    df.to_excel("risultati_altri_modelli_chunked.xlsx", index=False)
    print("\nAnalisi completata! File creato: risultati_altri_modelli_chunked.xlsx")


if __name__ == "__main__":
    main()