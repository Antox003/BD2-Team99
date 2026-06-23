import os
import requests
from pypdf import PdfReader
from openai import OpenAI
import google.generativeai as genai


GEMINI_KEY = os.getenv('GEMINI_KEY', '--------')
OPENAI_KEY = os.getenv('OPENAI_KEY', '------')

# Configura Gemini (adesso sa cos'è genai)
genai.configure(api_key=GEMINI_KEY)

def estrai_testo_da_pdf(path_pdf: str) -> str:
    try:
        reader = PdfReader(path_pdf)
        testi = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(testi)
    except Exception as e:
        print(f"Errore lettura PDF: {e}")
        return ""

def analizza_paper_con_gpt(path_pdf: str, prompt_personalizzato: str = None) -> dict:
    """Legge un singolo PDF, lo manda a GPT e restituisce il verdetto"""
    testo = estrai_testo_da_pdf(path_pdf)
    if not testo:
        return {"verdetto": "ERRORE", "motivazione": "Impossibile leggere il PDF."}

    # Se l'utente ha scritto un prompt personalizzato, usa quello, altrimenti usa quello standard
    istruzioni = prompt_personalizzato if prompt_personalizzato else "Sei un severo revisore scientifico (Peer Reviewer). Analizza il seguente testo e valuta la sua qualità logica, metodologica e scientifica. Ignora errori di formattazione o tipografici minori. Devi assegnare UNO dei seguenti verdetti: 1. ACCEPT: Il lavoro è eccellente, scientificamente solido e non richiede modifiche. 2. MINOR REVISION: Il lavoro è solido, ma richiede piccoli chiarimenti o correzioni non strutturali. 3. MAJOR REVISION: Il metodo o la logica hanno problemi significativi ma risolvibili con una riscrittura o nuovi esperimenti. 4. REJECT: Il lavoro ha errori fondamentali, conclusioni non supportate dai dati o contraddizioni gravi. 5. DESK REJECT: Il lavoro è pseudoscientifico, completamente illogico, o fuori tema. Rispondi TASSATIVAMENTE usando SOLO questo formato esatto: VERDETTO: [Inserisci qui ESATTAMENTE una delle 5 opzioni sopra] MOTIVO: [Spiegazione sintetica in massimo 2 righe]"
    
    try:
        # Uso Gpt 4o mini perchè veloce
        client = OpenAI(api_key=OPENAI_KEY)
        risposta = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[
                {"role": "system", "content": istruzioni},
                {"role": "user", "content": f"Testo da analizzare:\n{testo[:15000]}"}
            ],
            temperature=0.0,
        )
        raw = risposta.choices[0].message.content.strip()
        
        
        verdetto = "UNKNOWN"
        for v in ["DESK REJECT", "MAJOR REVISION", "MINOR REVISION", "REJECT", "ACCEPT"]:
            if v in raw.upper():
                verdetto = v
                break
                
        return {"verdetto": verdetto, "motivazione": raw}
    except Exception as e:
        return {"verdetto": "ERRORE", "motivazione": str(e)}

def analizza_paper_con_gemini(path_pdf: str, prompt_personalizzato: str = None) -> dict:
    """Legge un PDF e lo manda a Google Gemini"""
    testo = estrai_testo_da_pdf(path_pdf)
    if not testo:
        return {"verdetto": "ERRORE", "motivazione": "Impossibile leggere il PDF."}


    istruzioni = prompt_personalizzato if prompt_personalizzato else "Sei un severo revisore scientifico (Peer Reviewer). Analizza il seguente testo e valuta la sua qualità logica, metodologica e scientifica. Ignora errori di formattazione o tipografici minori. Devi assegnare UNO dei seguenti verdetti: 1. ACCEPT: Il lavoro è eccellente, scientificamente solido e non richiede modifiche. 2. MINOR REVISION: Il lavoro è solido, ma richiede piccoli chiarimenti o correzioni non strutturali. 3. MAJOR REVISION: Il metodo o la logica hanno problemi significativi ma risolvibili con una riscrittura o nuovi esperimenti. 4. REJECT: Il lavoro ha errori fondamentali, conclusioni non supportate dai dati o contraddizioni gravi. 5. DESK REJECT: Il lavoro è pseudoscientifico, completamente illogico, o fuori tema. Rispondi TASSATIVAMENTE usando SOLO questo formato esatto: VERDETTO: [Inserisci qui ESATTAMENTE una delle 5 opzioni sopra] MOTIVO: [Spiegazione sintetica in massimo 2 righe]"
    
    try:
        # Uso Gemini 2.5 Flash perchè veloce
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            system_instruction=istruzioni
        )
        
        risposta = model.generate_content(f"Testo da analizzare:\n{testo[:30000]}")
        raw = risposta.text.strip()
        
        verdetto = "UNKNOWN"
        for v in ["DESK REJECT", "MAJOR REVISION", "MINOR REVISION", "REJECT", "ACCEPT"]:
            if v in raw.upper():
                verdetto = v
                break
                
        return {"verdetto": verdetto, "motivazione": raw}
    except Exception as e:
        return {"verdetto": "ERRORE", "motivazione": str(e)}