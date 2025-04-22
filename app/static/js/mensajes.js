document.addEventListener("DOMContentLoaded", function () {
    // 🔹 Mostrar mensajes flash con SweetAlert2 (solo si hay mensaje)
    if (mensaje) {
        Swal.fire({
            title: categoria === "success" ? "¡Éxito!" : "Atención",
            text: mensaje,
            icon: categoria || "info",
            confirmButtonText: "Aceptar"
        });
    }

    // 🔹 Confirmación para eliminar registros
    document.querySelectorAll(".btn-eliminar").forEach(button => {
        button.addEventListener("click", function (event) {
            event.preventDefault();

            const id = this.getAttribute("data-id");
            const url = this.getAttribute("data-url");
            const nombre = this.closest("tr").querySelector("td").textContent.trim(); 

            Swal.fire({
                title: `¿Eliminar "${nombre}"?`,
                text: "No podrás revertir esta acción",
                icon: "warning",
                showCancelButton: true,
                confirmButtonColor: "#d33",
                cancelButtonColor: "#3085d6",
                confirmButtonText: "Sí, eliminar",
                cancelButtonText: "Cancelar"
            }).then((result) => {
                if (result.isConfirmed) {
                    fetch(url, { method: "POST" })
                        .then(response => {
                            if (response.ok) {
                                Swal.fire("Eliminado", `"${nombre}" ha sido eliminado.`, "success")
                                    .then(() => location.reload());
                            } else {
                                Swal.fire("Error", "Hubo un problema al eliminar el registro.", "error");
                            }
                        });
                }
            });
        });
    });
});
