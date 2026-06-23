import os
import requests
import pandas as pd
from pypdf import PdfReader
from openai import OpenAI

# API keys
GEMINI_KEY = "----" # contrallare chiavi prof
OPENAI_KEY = "----" # contrallare chiavi prof


GEMINI_MODEL = "models/gemini-flash-latest"
GPT_MODEL = "gpt-5.2"
# Endpoint Gemini
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"

# Client OpenAI
gpt_client = OpenAI(api_key=OPENAI_KEY)


def estrai_testo_da_pdf(path_pdf: str) -> str:
    """Estrae testo leggibile da PDF"""
    try:
        reader = PdfReader(path_pdf)
        testi = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(testi)
    except Exception as e:
        print(f"Errore lettura PDF {path_pdf}: {e}")
        return ""


def prompt_revisore(testo: str) -> str:
    """Prompt aggiornato con la scala di valutazione estesa"""
    return f"""
Sei un severo revisore scientifico (Peer Reviewer).
Analizza il seguente testo e valuta la sua qualità logica, metodologica e scientifica.
Ignora errori di formattazione o tipografici minori.

Devi assegnare UNO dei seguenti verdetti:

1. ACCEPT: Il lavoro è eccellente, scientificamente solido e non richiede modifiche.
2. MINOR REVISION: Il lavoro è solido, ma richiede piccoli chiarimenti o correzioni non strutturali.
3. MAJOR REVISION: Il metodo o la logica hanno problemi significativi ma risolvibili con una riscrittura o nuovi esperimenti.
4. REJECT: Il lavoro ha errori fondamentali, conclusioni non supportate dai dati o contraddizioni gravi.
5. DESK REJECT: Il lavoro è pseudoscientifico, completamente illogico, o fuori tema.

Rispondi TASSATIVAMENTE usando SOLO questo formato esatto:

VERDETTO: [Inserisci qui ESATTAMENTE una delle 5 opzioni sopra]
MOTIVO: [Spiegazione sintetica in massimo 2 righe]

Testo da analizzare:
{testo[:30000]} 
""" 
# Nota: ho messo un limite ai caratteri (es. 30000)


def analizza_con_gemini(testo: str) -> str:
    payload = {
        "contents": [{"parts": [{"text": prompt_revisore(testo)}]}]
    }
    try:
        resp = requests.post(GEMINI_URL, json=payload)
        if resp.status_code != 200:
            return f"ERRORE API: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        if "candidates" in data and data["candidates"]:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            return "ERRORE: Nessuna risposta generata."
    except Exception as e:
        return f"ECCEZIONE: {e}"


def analizza_con_gpt(testo: str) -> str:
    try:
        risposta = gpt_client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful and strict scientific reviewer."},
                {"role": "user", "content": prompt_revisore(testo)},
            ],
            temperature=0.0,
        )
        return risposta.choices[0].message.content.strip()
    except Exception as e:
        return f"ERRORE GPT: {e}"


def parse_risposta(raw: str):
    """Estrae il verdetto specifico e la motivazione"""
    lines = raw.splitlines()
    verdict = "UNKNOWN"
    reason = ""
    
    raw_upper = raw.upper()

    # Logica di parsing prioritaria (cerca prima le stringhe più lunghe per evitare falsi positivi)
    if "VERDETTO:" in raw_upper:
        parte_verdetto = raw_upper.split("VERDETTO:")[1].split("\n")[0].strip()
        
        if "DESK REJECT" in parte_verdetto:
            verdict = "DESK REJECT"
        elif "MAJOR REVISION" in parte_verdetto:
            verdict = "MAJOR REVISION"
        elif "MINOR REVISION" in parte_verdetto:
            verdict = "MINOR REVISION"
        elif "REJECT" in parte_verdetto:
            verdict = "REJECT"
        elif "ACCEPT" in parte_verdetto:
            verdict = "ACCEPT"
    
    # Fallback se il formato non è rispettato perfettamente ma la parola chiave è presente
    if verdict == "UNKNOWN":
        if "DESK REJECT" in raw_upper: verdict = "DESK REJECT"
        elif "MAJOR REVISION" in raw_upper: verdict = "MAJOR REVISION"
        elif "MINOR REVISION" in raw_upper: verdict = "MINOR REVISION"
        elif "REJECT" in raw_upper: verdict = "REJECT"
        elif "ACCEPT" in raw_upper: verdict = "ACCEPT"

    # Estrazione motivo
    for line in lines:
        if line.strip().upper().startswith("MOTIVO"):
            reason = line.split(":", 1)[-1].strip()
            break
            
    if not reason:
        # Prende tutto tranne la riga del verdetto se non trova "MOTIVO:"
        reason = raw.replace("\n", " ").strip()

    return verdict, reason


def main():
    risultati = []
    papers_dir = "papers"

    # Crea la cartella se non esiste per evitare errori
    if not os.path.exists(papers_dir):
        os.makedirs(papers_dir)
        print(f"Cartella '{papers_dir}' creata. Inserisci i PDF e riavvia.")
        return

    files = os.listdir(papers_dir)
    if not files:
        print(f"Nessun file trovato in '{papers_dir}'.")
        return

    for filename in files:
        if not (filename.endswith(".txt") or filename.endswith(".pdf")):
            continue

        path = os.path.join(papers_dir, filename)
        testo = ""
        
        if filename.endswith(".txt"):
            with open(path, "r", encoding="utf-8") as f:
                testo = f.read()
        else:
            print(f"Estraggo testo da PDF: {filename}...")
            testo = estrai_testo_da_pdf(path)

        if not testo:
            print(f" Salto {filename}: testo vuoto o illeggibile.")
            continue

        # --- GEMINI ---
        print(f"  Analizzo {filename} con Gemini ({GEMINI_MODEL})...")
        out_gemini = analizza_con_gemini(testo)
        verdict_g, reason_g = parse_risposta(out_gemini)
        print(f"      -> Verdetto: {verdict_g}")

        # --- GPT ---
        print(f"    Analizzo {filename} con ChatGPT ({GPT_MODEL})...")
        out_gpt = analizza_con_gpt(testo)
        verdict_gpt, reason_gpt = parse_risposta(out_gpt)
        print(f"      -> Verdetto: {verdict_gpt}")

        risultati.extend([
            {"paper": filename, "LLM": "Gemini", "Verdetto": verdict_g, "Motivo": reason_g},
            {"paper": filename, "LLM": "ChatGPT", "Verdetto": verdict_gpt, "Motivo": reason_gpt},
        ])

    if risultati:
        df = pd.DataFrame(risultati)
        df.to_excel("risultati_confronto_dettagliato.xlsx", index=False)
        print("\nAnalisi completata! File creato: risultati_confronto_dettagliato.xlsx")
    else:
        print("\nNessun risultato generato.")


if __name__ == "__main__":
    main()