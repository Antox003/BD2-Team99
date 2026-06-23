import os
from pypdf import PdfReader
from gpt4all import GPT4All
import gc
import concurrent.futures
import multiprocessing as mp

# ================================
# LA FLOTTA ASSEGNATA ALLE GPU
# ================================
MODELLI_E_GPU = [
    ("Llama-3-8B", "Meta-Llama-3-8B-Instruct.Q4_0.gguf", "kompute:NVIDIA A800 40GB Active"),
    ("Mistral-7B", "mistral-7b-instruct-v0.1.Q4_0.gguf", "kompute:NVIDIA A800 40GB Active (2)"),
    ("Qwen-2.5-7B", "Qwen2.5-7B-Instruct-Q4_K_M.gguf", "kompute:NVIDIA A800 40GB Active (3)"),
    ("Gemma-2-9B", "gemma-2-9b-it-Q4_K_M.gguf", "kompute:NVIDIA A800 40GB Active")
]

# ================================
# FUNZIONI DI ESTRAZIONE E CHUNKING
# ================================

def estrai_testo_da_pdf(path_pdf: str) -> str:
    try:
        reader = PdfReader(path_pdf)
        return "\n".join([page.extract_text() or "" for page in reader.pages])
    except Exception as e:
        print(f"Errore lettura PDF {path_pdf}: {e}")
        return ""

def suddividi_in_chunk(testo: str, chunk_size=10000, overlap=1500) -> list:
    chunks = []
    inizio = 0
    while inizio < len(testo):
        fine = inizio + chunk_size
        chunk = testo[inizio:fine]
        chunks.append(chunk)
        inizio += (chunk_size - overlap)
    return chunks

# ================================
# FUNZIONI DI ANALISI E PROMPT
# ================================

def analizza_singolo_chunk(chunk: str, numero_chunk: int, totale_chunk: int, model_obj) -> str:
    prompt = f"""Sei un severo revisore scientifico. Stai leggendo la Parte {numero_chunk} di {totale_chunk} di un manoscritto accademico.
Riassumi brevemente i concetti chiave ed eventuali difetti logici o metodologici.

Testo della Parte {numero_chunk}:
{chunk}
    """
    with model_obj.chat_session():
        return model_obj.generate(prompt, max_tokens=200, temp=0.1)

def verdetto_finale_su_sommario(sommario_combinato: str, model_obj) -> str:
    prompt = f"""Sei un severo revisore scientifico (Peer Reviewer).
Analizza il seguente testo accademico.
Il tuo compito è valutare se il lavoro è solido o se presenta errori gravi.

Devi assegnare UNO dei seguenti verdetti:
1. ACCEPT: Eccellente, nessun errore.
2. MINOR REVISION: Solido, piccoli chiarimenti necessari.
3. MAJOR REVISION: Problemi metodologici o logici significativi ma risolvibili.
4. REJECT: Errori fondamentali, conclusioni non supportate.
5. DESK REJECT: Pseudoscienza, illogico o fuori tema.

Rispondi TASSATIVAMENTE usando SOLO questo formato esatto:
VERDETTO: [Inserisci qui ESATTAMENTE una delle 5 opzioni sopra]
MOTIVO: [Spiegazione sintetica del perché]

Appunti:
{sommario_combinato}
    """
    with model_obj.chat_session():
        return model_obj.generate(prompt, max_tokens=350, temp=0.1)

def parse_risposta(raw_text: str):
    verdetto = "UNKNOWN"
    motivo = raw_text
    raw_upper = raw_text.upper()

    if "DESK REJECT" in raw_upper: verdetto = "DESK REJECT"
    elif "MAJOR REVISION" in raw_upper: verdetto = "MAJOR REVISION"
    elif "MINOR REVISION" in raw_upper: verdetto = "MINOR REVISION"
    elif "REJECT" in raw_upper: verdetto = "REJECT"
    elif "ACCEPTED" in raw_upper or "ACCEPT" in raw_upper: verdetto = "ACCEPT"

    if "MOTIVO:" in raw_text:
        motivo = raw_text.split("MOTIVO:", 1)[-1].strip()
    elif "VERDETTO:" in raw_text:
        for line in raw_text.splitlines():
            if not line.upper().startswith("VERDETTO"):
                motivo = line
                break
    return verdetto, motivo

# ================================
# FUNZIONE WORKER (Per il singolo thread)
# ===============================
def esegui_singolo_modello(args):
    """Questa funzione viene lanciata in contemporanea dai processi"""
    nome_modello, file_modello, nome_gpu, chunks, totale_chunks = args
    
    # AGGIUNTO FLUSH=TRUE
    print(f" PARTENZA: {nome_modello} si sta caricando sulla {nome_gpu}...", flush=True)
    try:
        model = GPT4All(file_modello, model_path='/home/llmrev/.cache/gpt4all/', allow_download=False, device=nome_gpu, n_ctx=8192)
        
        appunti_critici = []
        for j, chunk in enumerate(chunks, 1):
            analisi_parziale = analizza_singolo_chunk(chunk, j, totale_chunks, model)
            appunti_critici.append(f"--- NOTE PARTE {j} ---\n{analisi_parziale}\n")
            
        sommario_completo = "\n".join(appunti_critici)
        raw_output = verdetto_finale_su_sommario(sommario_completo, model)
        verdetto, motivo = parse_risposta(raw_output)
        
        del model
        gc.collect()
        
        # AGGIUNTO FLUSH=TRUE
        print(f":) TRAGUARDO: Analisi con {nome_modello} completata!", flush=True)
        return nome_modello, {"verdetto": verdetto, "motivazione": motivo}
        
    except Exception as e:
        # AGGIUNTO FLUSH=TRUE
        print(f" :( ERRORE con {nome_modello}: {e}", flush=True)
        return nome_modello, {"verdetto": "ERRORE", "motivazione": str(e)}

# ================================
# IL MOTORE VERO E PROPRIO PARALLELO
# ================================
def analizza_paper_con_tutti_i_locali(file_path: str) -> dict:
    """Legge il PDF e scatena i modelli in PARALLELO sulle tue 3 A800"""
    risultati_finali = {}
    
    testo = estrai_testo_da_pdf(file_path)
    if not testo.strip():
        for nome, _, _ in MODELLI_E_GPU:
            risultati_finali[nome] = {"verdetto": "ERRORE", "motivazione": "File vuoto."}
        return risultati_finali

    chunks = suddividi_in_chunk(testo)
    totale_chunks = len(chunks)
    
    print("\n Inizio sottomissione in parallelo sulle 3 A800!\n")

    # Prepariamo i pacchetti di istruzioni per i modelli
    tasks = []
    for nome, file_m, gpu in MODELLI_E_GPU:
        tasks.append((nome, file_m, gpu, chunks, totale_chunks))

    # Creiamo un contesto "spawn" per evitare che le GPU si blocchino in silenzio
    ctx = mp.get_context('spawn')
    
    # Passiamo il contesto al nostro Executor
    with concurrent.futures.ProcessPoolExecutor(max_workers=3, mp_context=ctx) as executor:
        risultati = executor.map(esegui_singolo_modello, tasks)
        
        for nome_modello, esito in risultati:
            risultati_finali[nome_modello] = esito

    print("\n I modelli locali hanno finito, ritorna alla pagina web...\n")
    return risultati_finali