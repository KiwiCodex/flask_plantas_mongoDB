document.addEventListener("DOMContentLoaded", function () {
    const buscador = document.getElementById("buscador");
    const tableBody = document.querySelector("table tbody");
    
    // Cuando se escribe en el input, filtra las filas de la tabla.
    buscador.addEventListener("keyup", function () {
        const filtro = buscador.value.toLowerCase();
        const filas = tableBody.getElementsByTagName("tr");
        
        for (let i = 0; i < filas.length; i++) {
            const fila = filas[i];
            const textoFila = fila.textContent.toLowerCase();
            
            // Si el texto de la fila contiene el filtro, la mostramos; de lo contrario, la ocultamos.
            if (textoFila.indexOf(filtro) > -1) {
                fila.style.display = "";
            } else {
                fila.style.display = "none";
            }
        }
    });
});
