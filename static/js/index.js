// Trova gli elementi
const bottone = document.getElementById('bottone-revisione');
const inputPdf = document.getElementById('carica-pdf');
const labelBox = document.querySelector('.box-upload');
const messaggioErrore = document.getElementById('messaggio-errore');

// Recuperiamo solo la checkbox e la textarea
const checkPrompt = document.getElementById('check-prompt');
const testoPrompt = document.getElementById('testo-prompt');

// SEZIONE 1: GESTIONE DEL DRAG & DROP
// A. Evita che il browser apra il PDF per conto suo quando lo trasciniamo
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(nomeEvento => {
    labelBox.addEventListener(nomeEvento, function(e) {
        e.preventDefault();
        e.stopPropagation();
    }, false);
});

// B. Effetto grafico: colora il box quando il file ci "vola" sopra
['dragenter', 'dragover'].forEach(nomeEvento => {
    labelBox.addEventListener(nomeEvento, function() {
        labelBox.classList.add('drag-attivo');
    }, false);
});

// C. Effetto grafico: toglie il colore se l'utente esce dal box o rilascia il file
['dragleave', 'drop'].forEach(nomeEvento => {
    labelBox.addEventListener(nomeEvento, function() {
        labelBox.classList.remove('drag-attivo');
    }, false);
});

// D. Il momento del rilascio (DROP)
labelBox.addEventListener('drop', function(e) {
    // Catturiamo il file che è stato lasciato cadere
    let fileTrascinato = e.dataTransfer.files;
    
    // Lo inseriamo forzatamente nel nostro input nascosto
    inputPdf.files = fileTrascinato; 
    
    // Aggiorniamo la grafica
    mostraAnteprimaFile();
});

// SEZIONE 2: GESTIONE DEL CLICK NORMALE
// Se l'utente clicca normalmente invece di trascinare
inputPdf.addEventListener('change', mostraAnteprimaFile);

// SEZIONE 3: LA FUNZIONE CHE CREA L'ANTEPRIMA
function mostraAnteprimaFile() {
  // Controlliamo se c'è almeno un file
  if (inputPdf.files.length > 0) {
    let file = inputPdf.files[0]; // Prendiamo il primo file
  // Controllo di sicurezza: è davvero un PDF?
  if (file.type === "application/pdf") {
  // Cambiamo il testo inserendo la X in alto e centrando il resto
    labelBox.innerHTML = `
    <span id="rimuovi-pdf" class="chiudi-icona">✖</span>
    <div style="text-align: center;">
    📄 <br> 
    <strong>${file.name}</strong>
    </div>
    `;
  // Lo facciamo diventare verde per confermare il successo
    labelBox.style.borderColor = "#27ae60";
    labelBox.style.color = "#27ae60";
 // Nascondiamo l'errore rosso (se c'era)
    messaggioErrore.classList.add('nascosto');

 // TASTO X
 const tastoRimuovi = document.getElementById('rimuovi-pdf');
 tastoRimuovi.addEventListener('click', function(e) {
   e.preventDefault();   // Evita i comportamenti di default del browser
   e.stopPropagation();  // Blocca il click qui, per non far aprire la finestra dei file
   inputPdf.value = "";  // Svuota la memoria del file input
   ripristinaBox();      // Richiama la funzione che fa tornare tutto come prima
 });

 } else {
 // Se ha furbescamente caricato un'immagine o un file word
     alert("Per favore, carica unicamente file in formato PDF.");
     inputPdf.value = ""; // Svuotiamo l'input
     ripristinaBox();
    }
  }
}

// Funzione che riporta il box allo stato originale
function ripristinaBox() {
  labelBox.innerHTML = "Seleziona il file PDF";
  labelBox.style.borderColor = "#2c3e50"; // Torna blu scuro
  labelBox.style.color = "#2c3e50";       // Torna blu scuro
}


// SEZIONE 4: L'INVIO AL SERVER (Aggiornata per funzionare col <form>)
const form = document.querySelector('form');

if (form) {
    form.addEventListener('submit', function(e) {
        // 1. Controlliamo se la scatola del file è vuota
        if (inputPdf.files.length === 0) {
            // C'È UN ERRORE: Blocchiamo la partenza del form verso Python
            e.preventDefault(); 
            // Togliamo la classe "nascosto" per far apparire la scritta rossa
            messaggioErrore.classList.remove('nascosto');
            return; 
        }

        // TUTTO OK: Il file c'è e il form sta per partire verso Flask
        messaggioErrore.classList.add('nascosto');

        // UX: Disabilitiamo il bottone per evitare che l'utente clicchi due volte per sbaglio
        bottone.disabled = true;
        bottone.textContent = "Caricamento in corso...";
    });
}


// SEZIONE 5: GESTIONE DEL PROMPT PERSONALIZZATO
if (checkPrompt && testoPrompt) {
    
    function gestisciStatoPrompt() {
        if (checkPrompt.checked) {
            testoPrompt.disabled = false; // Sblocca: torna al colore normale!
        } else {
            testoPrompt.disabled = true;  // Blocca: attiva l'effetto sbiadito del CSS!
            testoPrompt.value = '';       // Pulisce il testo se l'utente ci ripensa
        }
    }

    // Controllo all'avvio
    gestisciStatoPrompt();

    // In ascolto del click
    checkPrompt.addEventListener('change', gestisciStatoPrompt);
}