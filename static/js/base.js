// Cerchiamo il bottone e il menù nella pagina
const hamburgerBtn = document.getElementById('hamburger-btn');
const navMenu = document.getElementById('nav-menu');

// Mettiamo il bottone "in ascolto" del clic
if (hamburgerBtn && navMenu) {
    hamburgerBtn.addEventListener('click', function() {
        // La funzione toggle aggiunge la classe 'active' se non c'è, e la toglie se c'è
        navMenu.classList.toggle('active');
    });
}