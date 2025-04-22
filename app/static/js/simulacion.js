document.addEventListener("DOMContentLoaded", function () {
    // Asigna el evento al botón "Generar Nuevos Valores"
    const btnSimular = document.getElementById("btn-simular");
    if (btnSimular) {
        btnSimular.addEventListener("click", generarNuevosValores);
    }
    
    // Asigna el evento a todos los botones "Estabilizar" de la tabla
    document.querySelectorAll(".btn-estabilizar").forEach(function(button) {
        button.addEventListener("click", estabilizarValor);
    });
});

function generarNuevosValores() {
    const moduloId = document.getElementById("btn-simular").getAttribute("data-modulo-id");

    fetch(`/modulos/simulacion_ajax/${moduloId}`)
      .then(response => response.json())
      .then(data => {
          if (data.error) {
              alert(data.error);
              return;
          }
          
          const valores = data.valores_simulados;
          const condiciones = data.condiciones;
          const scores = data.scores;
          const estadoPlanta = document.getElementById("estado-planta");

          // Actualizar cada fila de la tabla con los nuevos datos del servidor
          for (let variable in valores) {
              let valor = valores[variable];

              let condicionCell = document.getElementById(`estado-${variable}`);
              let scoreCell = document.getElementById(`alerta-${variable}`);
              let valorCell = condicionCell ? condicionCell.closest("tr").querySelector(".valor") : null;
              if (!condicionCell || !scoreCell || !valorCell) {
                  console.error(`No se encontró la celda para la variable: ${variable}`);
                  continue;
              }
              // Actualiza la celda de Condición con el mensaje del servidor
              condicionCell.innerHTML = condiciones[variable];
              
              // Actualiza la celda de Estado con el puntaje formateado
              let score = scores[variable];
              let scoreText = "";
              if (score === 0) {
                  scoreText = "✅ Ok (0)";
              } else if (score === 1) {
                  scoreText = "⚠️ Alerta (+1)";
              } else if (score === 2) {
                  scoreText = "⚠️ Alerta (+2)";
              } else if (score === 3) {
                  scoreText = "⚠️ Precaución (+3)";
              }
              scoreCell.innerHTML = scoreText;
              
              // Actualiza la celda de Valor Actual
              valorCell.innerHTML = `<strong>${valor.toFixed(1)}</strong>`;
          }
          
          // Actualiza el globo de estado global usando los datos del servidor
          estadoPlanta.className = `box ${data.estado_color}`;
          const emojiMapping = { green: "😊", yellow: "😐", orange: "😟", red: "😭" };
          const textMapping = { green: "¡Todo bien!", yellow: "En cuidado", orange: "Preocupado", red: "Necesito ayuda" };
          estadoPlanta.innerHTML = `<span class="emoji">${emojiMapping[data.estado_color]}</span><span class="texto">${textMapping[data.estado_color]}</span>`;
      })
      .catch(error => console.error("Error al obtener nuevos valores:", error));
}

function estabilizarValor(event) {
    // Obtener el nombre de la variable desde el atributo data-variable del botón
    let variable = event.target.getAttribute("data-variable");
    // Buscar la celda "estado" para esa variable (para obtener el rango ideal)
    let estadoCell = document.getElementById(`estado-${variable}`);
    if (!estadoCell) {
        console.error(`No se encontró la celda de estado para ${variable}`);
        return;
    }
    let min = parseFloat(estadoCell.dataset.min);
    let max = parseFloat(estadoCell.dataset.max);
    if (isNaN(min) || isNaN(max)) {
        console.error(`Valores de min/max no válidos para ${variable}`);
        return;
    }
    // Generar un valor aleatorio dentro del rango ideal
    let nuevoValor = parseFloat((Math.random() * (max - min) + min).toFixed(1));
    
    // Actualizar la celda "Valor Actual" en la fila correspondiente
    let valorCell = estadoCell.closest("tr").querySelector(".valor");
    if (valorCell) {
        valorCell.innerHTML = `<strong>${nuevoValor.toFixed(1)}</strong>`;
    }
    // Actualizar la celda "Condición" y "Estado" para esa variable (estabilizado: condiciones ideales y score 0)
    estadoCell.innerHTML = "🟢 Dentro del rango ideal";
    let scoreCell = document.getElementById(`alerta-${variable}`);
    if (scoreCell) {
        scoreCell.innerHTML = "✅ Ok (0)";
    }
    
    // Luego, recalculemos el estado global a partir de los valores actuales de la tabla
    recalcGlobalState();
}

function recalcGlobalState() {
    const variables = ["Temperatura", "pH", "Humedad"];
    const THRESHOLD_ALERT_JS = 1.0;
    let totalScore = 0;
    variables.forEach(variable => {
         let estadoCell = document.getElementById(`estado-${variable}`);
         if (!estadoCell) return;
         let min = parseFloat(estadoCell.dataset.min);
         let max = parseFloat(estadoCell.dataset.max);
         let row = estadoCell.closest("tr");
         let valorCell = row.querySelector(".valor");
         let valor = parseFloat(valorCell.textContent) || 0;
         let score = 0;
         if (valor < min) {
             let diff = min - valor;
             if (diff <= THRESHOLD_ALERT_JS) score = 1;
             else if (diff <= 4) score = 2;
             else score = 3;
         } else if (valor > max) {
             let diff = valor - max;
             if (diff <= THRESHOLD_ALERT_JS) score = 1;
             else if (diff <= 4) score = 2;
             else score = 3;
         } else {
             score = 0;
         }
         totalScore += score;
    });
    
    let estadoGlobal = "";
    if (totalScore === 0) estadoGlobal = "green";
    else if (totalScore <= 2) estadoGlobal = "yellow";
    else if (totalScore <= 5) estadoGlobal = "orange";
    else estadoGlobal = "red";
    
    // Actualizar el globo de estado global
    const estadoPlanta = document.getElementById("estado-planta");
    const emojiMapping = { green: "😊", yellow: "😐", orange: "😟", red: "😭" };
    const textMapping = { green: "¡Todo bien!", yellow: "En cuidado", orange: "Preocupado", red: "Necesito ayuda" };
    estadoPlanta.className = `box ${estadoGlobal}`;
    estadoPlanta.innerHTML = `<span class="emoji">${emojiMapping[estadoGlobal]}</span><span class="texto">${textMapping[estadoGlobal]}</span>`;
}
