import os
from pymongo import MongoClient
from bson.objectid import ObjectId # Serve per gestire gli ID di Mongo
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv



load_dotenv()

# Prendi la stringa magica dal file .env (più sicuro!)
MONGO_URI = os.getenv('MONGO_URI')
client = MongoClient(MONGO_URI)
db = client["Tesi_AI_Reviewer"]

# Collezioni
users_col = db["utenti_admin"]
col_papers = db["dataset_papers"]
col_verdetti = db["verdetti_llm"]

# --- FUNZIONI PER GLI UTENTI ---
def verifica_login(username, password):
    utente = users_col.find_one({"username": username})
    if utente and check_password_hash(utente['password_hash'], password):
        return utente
    return None

# --- FUNZIONI PER I PDF/PAPERS ---
def aggiungi_paper(titolo, file_path):
    paper = {
        "titolo": titolo,
        "file_path": file_path,
        "stato": "caricato"
    }
    return col_papers.insert_one(paper).inserted_id

# --- FUNZIONI PER I VERDETTI ---
def salva_risultato_analisi(paper_id, modello, verdetto, motivazione):
    risultato = {
        "paper_id": ObjectId(paper_id),
        "modello": modello,
        "verdetto": verdetto,
        "motivazione": motivazione
    }
    col_verdetti.insert_one(risultato)


def crea_primo_admin(username, password):
    if users_col.find_one({"username": username}):
        return "Admin già esistente"
    
    hashed_pw = generate_password_hash(password)
    users_col.insert_one({
        "username": username,
        "password_hash": hashed_pw
    })
    return "Admin creato correttamente"


# Aggiungi questa funzione in fondo a database.py

def aggiungi_paper(titolo, file_path):
    """Inserisce i metadati del PDF nel database se non esiste già"""
    # Controlla se c'è già per evitare doppioni se lanci lo script due volte
    if col_papers.find_one({"file_path": file_path}):
        return False 
    
    paper = {
        "titolo": titolo,
        "file_path": file_path,
        "stato": "da_analizzare" # 'da_analizzare', 'in_corso', 'completato'
    }
    col_papers.insert_one(paper)
    return True


def get_tutti_papers():
    """Recupera tutti i paper dal database e li trasforma in una lista"""
    # find() prende tutto, list() lo trasforma in un formato leggibile da HTML
    return list(col_papers.find())


def get_paper_by_id(paper_id):
    """Cerca un paper specifico nel database tramite il suo ID"""
    return col_papers.find_one({"_id": ObjectId(paper_id)})


def elimina_paper_dal_db(paper_id):
    """Elimina il documento del paper dal database"""
    return col_papers.delete_one({"_id": ObjectId(paper_id)})

def get_storico_analisi():
    """
    Recupera tutti i paper che hanno almeno un verdetto 
    e organizza i responsi raggruppandoli per paper.
    """
    # Troviamo tutti i verdetti nel database
    tutti_i_verdetti = list(col_verdetti.find())
    
    storico_organizzato = {}
    
    for v in tutti_i_verdetti:
        paper_id_str = str(v['paper_id'])
        
        # Se è la prima volta che incontriamo questo paper, gli creiamo il contenitore
        if paper_id_str not in storico_organizzato:
            # Cerchiamo il titolo reale del paper per mostrarlo nella tabella
            paper_info = get_paper_by_id(paper_id_str)
            titolo = paper_info['titolo'] if paper_info else "Paper sconosciuto"
            
            storico_organizzato[paper_id_str] = {
                "titolo": titolo,
                # Puoi aggiungere la data reale se la salvi nel DB, qui mettiamo un placeholder
                "data": "N/D", 
                "ora": "N/D",
                "responsi": []
            }
            
        # Aggiungiamo il singolo giudizio del modello alla lista dei responsi di questo paper
        storico_organizzato[paper_id_str]['responsi'].append({
            "categoria": v.get('modello', 'Modello Ignoto'), # Mostriamo quale LLM ha dato il giudizio
            "esito": v.get('verdetto', 'N/D'),
            "motivazione": v.get('motivazione', 'N/D')
        })
        
    return storico_organizzato