import os
import threading
from flask import Flask, render_template, session, redirect, url_for, request, flash, send_from_directory, jsonify
from dotenv import load_dotenv
from werkzeug.utils import secure_filename 
import uuid
import pandas as pd
from io import BytesIO
from flask import send_file
from database import get_storico_analisi

from database import verifica_login, get_tutti_papers, get_paper_by_id, aggiungi_paper, elimina_paper_dal_db, salva_risultato_analisi
from ai_engine import analizza_paper_con_gpt, analizza_paper_con_gemini
from ai_engine_locale import analizza_paper_con_tutti_i_locali 


RISULTATI_SINGOLI_DB = {}

load_dotenv()

app = Flask(__name__)


app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default_key_per_sviluppo')
app.config['UPLOAD_FOLDER'] = 'pdf_dataset'

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/storico')
def storico():

    dati_storico = get_storico_analisi()
    
    return render_template('storico.html', dati_storico=dati_storico)


@app.route('/dataset')
def dataset():
    papers_dal_db = get_tutti_papers()
    
    return render_template('dataset.html', lista_papers=papers_dal_db)


@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if 'file_pdf' not in request.files:
        return redirect(url_for('dataset'))

    file = request.files['file_pdf']

    if file.filename == '':
        return redirect(url_for('dataset'))


    if file and file.filename.endswith('.pdf'):

        filename = secure_filename(file.filename)
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        file.save(file_path)
        
        titolo = filename.replace(".pdf", "")
        aggiungi_paper(titolo, file_path)
        
        return redirect(url_for('dataset'))

    return redirect(url_for('dataset'))


@app.route('/rimuovi_pdf/<paper_id>', methods=['POST'])
def rimuovi_pdf(paper_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    paper = get_paper_by_id(paper_id)
    
    if paper:
        file_path = paper.get('file_path')
        
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Errore durante l'eliminazione del file fisico: {e}")
                
        elimina_paper_dal_db(paper_id)
        
    return redirect(url_for('dataset'))


@app.route('/caricamento/<paper_id>')
def caricamento(paper_id):
    return render_template('caricamento.html', paper_id=paper_id)


@app.route('/sottometti_analisi/<paper_id>', methods=['POST'])
def sottometti_analisi(paper_id):
    paper = get_paper_by_id(paper_id)
    if not paper:
        return jsonify({"success": False, "error": "Paper non trovato"}), 404

    file_path = paper['file_path']

    risultato_gpt = analizza_paper_con_gpt(file_path)
    salva_risultato_analisi(paper_id, "GPT-4o-mini", risultato_gpt['verdetto'], risultato_gpt['motivazione'])

    risultato_gemini = analizza_paper_con_gemini(file_path)
    salva_risultato_analisi(paper_id, "Gemini-2.5-Flash", risultato_gemini['verdetto'], risultato_gemini['motivazione'])

    risultati_locali = analizza_paper_con_tutti_i_locali(file_path)
    
    for nome_modello, esito in risultati_locali.items():
        salva_risultato_analisi(paper_id, nome_modello, esito['verdetto'], esito['motivazione'])

    risultati_combinati = {
        "GPT-4o-mini": risultato_gpt,
        "Gemini-2.5-Flash": risultato_gemini,
        **risultati_locali
    }

    RISULTATI_SINGOLI_DB[paper_id] = {
        "titolo": paper['titolo'],
        "risultati": risultati_combinati
    }

    return jsonify({"success": True})

# ---------------------------------------------------------
# MOTORE PER ANALISI MASSIVA (Chiamato da Javascript)
# ---------------------------------------------------------
@app.route('/api/sottometti_tutti', methods=['POST'])
def api_sottometti_tutti():
    tutti_i_paper = get_tutti_papers() 
    
    if not tutti_i_paper:
        print("Nessun paper trovato nel DB!", flush=True)
        return jsonify({"success": False, "error": "Nessun paper nel database!"})

    lista_risultati_globali = []

    for paper in tutti_i_paper:
        paper_id = str(paper['_id'])
        file_path = paper['file_path']
        titolo = paper.get('titolo', f'Paper {paper_id}')

        print(f"\n🚀 SOTTOMISSIONE MASSIVA: {titolo}", flush=True)

        ris_gpt = analizza_paper_con_gpt(file_path)
        ris_gemini = analizza_paper_con_gemini(file_path)

        ris_locali = analizza_paper_con_tutti_i_locali(file_path)


        risultati_combinati = {
            "GPT-4o-mini": ris_gpt,
            "Gemini-2.5-Flash": ris_gemini,
            **ris_locali
        }

        lista_risultati_globali.append({
            "titolo": titolo,
            "risultati": risultati_combinati
        })

    task_id = str(uuid.uuid4())
    RISULTATI_MASSIVI_DB[task_id] = lista_risultati_globali

    print("✅ ANALISI MASSIVA COMPLETATA CON SUCCESSO!", flush=True)
    return jsonify({"success": True, "task_id": task_id})


# ---------------------------------------------------------
# PAGINA VERDETTO MASSIVO
# ---------------------------------------------------------
@app.route('/verdetto_massivo/<task_id>')
def verdetto_massivo(task_id):
    risultati_globali = RISULTATI_MASSIVI_DB.get(task_id)
    
    if not risultati_globali:
        return "Risultati scaduti o non trovati. Riprova.", 404

    return render_template(
        'verdetto.html', 
        tipo_analisi='multiplo', 
        lista_risultati=risultati_globali,
        task_id=task_id
    )


@app.route('/verdetto/<paper_id>')
def verdetto(paper_id):
    dati_paper = RISULTATI_SINGOLI_DB.get(paper_id, {})
    
    titolo = dati_paper.get('titolo', 'Paper sconosciuto')
    risultati = dati_paper.get('risultati', {})

    return render_template('verdetto.html', 
                           titolo_paper=titolo,
                           risultati=risultati,
                           paper_id=paper_id)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        utente = verifica_login(username, password)

        if utente:
            session['user_id'] = str(utente['_id']) 
            return redirect(url_for('home'))
        else:
            flash("Username o password non corretti.", "error")
            return redirect(url_for('login'))
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    """
    Effettua il logout rimuovendo l'utente dalla sessione.
    """
    session.pop('user_id', None)
    return redirect(url_for('home'))


@app.route('/visualizza/<paper_id>')
def visualizza_pdf(paper_id):
    paper = get_paper_by_id(paper_id)
    
    if paper:
        path_completo = paper['file_path']
        directory = os.path.dirname(path_completo)
        filename = os.path.basename(path_completo)
        
        return send_from_directory(directory, filename)
    
    return "Errore: Paper non trovato nel database", 404


@app.route('/sottometti_locale/<paper_id>', methods=['POST'])
def sottometti_locale(paper_id):
    paper = get_paper_by_id(paper_id)
    if not paper:
        return "Paper non trovato", 404

    file_path = paper['file_path']

    thread = threading.Thread(target=elabora_paper_in_background, args=(paper_id, file_path))
    thread.start()

    flash("Analisi locale avviata! Potrebbero volerci alcuni minuti. Ricarica la pagina più tardi per vedere i risultati.", "info")
    return redirect(url_for('dataset'))


# ================================
# ESPORTAZIONE EXCEL (SINGOLO)
# ================================
@app.route('/esporta_excel/<paper_id>')
def esporta_excel(paper_id):
    dati_paper = RISULTATI_SINGOLI_DB.get(paper_id, {})
    
    titolo = dati_paper.get('titolo', f'Paper_{paper_id}')
    risultati = dati_paper.get('risultati', {})
    
    rows = []
    for modello, dati in risultati.items():
        rows.append({
            "Modello AI": modello,
            "Verdetto": dati.get('verdetto', 'N/A'),
            "Motivazione": dati.get('motivazione', 'N/A')
        })
        
    df = pd.DataFrame(rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Verdetti')
    output.seek(0)
    
    nome_pulito = "".join([c for c in titolo if c.isalnum() or c in " _-"]).rstrip()
    return send_file(output, download_name=f"Analisi_{nome_pulito}.xlsx", as_attachment=True)

# ================================
# ESPORTAZIONE EXCEL (MASSIVO)
# ================================
@app.route('/esporta_excel_massivo/<task_id>')
def esporta_excel_massivo(task_id):
    risultati_globali = RISULTATI_MASSIVI_DB.get(task_id, [])
    
    rows = []
    for paper in risultati_globali:
        titolo = paper['titolo']
        for modello, dati in paper['risultati'].items():
            rows.append({
                "Titolo Paper": titolo,
                "Modello AI": modello,
                "Verdetto": dati.get('verdetto', 'N/A'),
                "Motivazione": dati.get('motivazione', 'N/A')
            })
            
    df = pd.DataFrame(rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Analisi Globale')
    output.seek(0)
    
    return send_file(output, download_name="Report_Intero_Dataset.xlsx", as_attachment=True)



@app.route('/carica_e_analizza', methods=['POST'])
def carica_e_analizza():
    print("\n" + "="*50, flush=True)
    print("Bottone analizza cliccato", flush=True)

    if 'file_pdf' not in request.files:
        print(" ERRORE: Flask non vede il file_pdf!", flush=True)
        return redirect(url_for('home'))

    file = request.files['file_pdf']
    if file.filename == '' or not file.filename.endswith('.pdf'):
        print(f" ERRORE: Il file non è valido o ha nome vuoto: {file.filename}", flush=True)
        flash("Per favore, inserisci un file PDF valido.", "error")
        return redirect(url_for('home'))

    print(f"File ricevuto con successo: {file.filename}!", flush=True)

    usa_prompt = request.form.get('usa_prompt')
    testo_prompt = request.form.get('testo_prompt')
    print(f"INFO PROMPT: usa_prompt={usa_prompt}, testo={testo_prompt}", flush=True)

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    file.save(file_path)

    titolo = filename.replace(".pdf", "")

    from bson.objectid import ObjectId
    from database import col_papers, aggiungi_paper
    
    paper_esistente = col_papers.find_one({"file_path": file_path})
    if paper_esistente:
        paper_id = str(paper_esistente['_id'])
        print(f"Trovato paper esistente nel DB: {paper_id}", flush=True)
    else:
        risultato = col_papers.insert_one({
            "titolo": titolo, "file_path": file_path, "stato": "da_analizzare"
        })
        paper_id = str(risultato.inserted_id)
        print(f"Nuovo paper inserito nel DB: {paper_id}", flush=True)

    if usa_prompt == 'on' and testo_prompt and testo_prompt.strip() != "":
        session[f'prompt_custom_{paper_id}'] = testo_prompt.strip()
        print("Prompt personalizzato salvato in sessione!", flush=True)

    print("🚀 File salvato. Mando l'ok a Javascript...", flush=True)
    
    return jsonify({"success": True, "paper_id": paper_id})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)