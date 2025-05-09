function calculate() {
    const length = parseFloat(document.getElementById('length').value);
    const width = parseFloat(document.getElementById('width').value);
    const depth = parseFloat(document.getElementById('depth').value);

    if (isNaN(length) || length <= 0 || isNaN(width) || width <= 0 || isNaN(depth) || depth <= 0) {
        alert("Por favor, ingrese valores válidos.");
        return;
    }

    const volume = length * width * depth;
    const aggreBindPerM3 = 4;
    const waterPerM3 = 1.3;

    const totalAggreBind = aggreBindPerM3 * volume;
    const totalWater = waterPerM3 * volume;
    const total = totalAggreBind + totalWater;

    document.getElementById('aggrebindResult').innerText = `AggreBind necesario: ${totalAggreBind.toFixed(2)} litros`;
    document.getElementById('waterResult').innerText = `Agua necesaria: ${totalWater.toFixed(2)} litros`;
    document.getElementById('totalResult').innerText = `Total: ${total.toFixed(2)} litros`;

    document.getElementById('result').style.display = 'block';
    document.getElementById('summary').style.display = 'block';
    document.querySelector('.buttons').style.display = 'flex';

    // Guardar datos en variables globales
    window.cotizacionData = {
        length,
        width,
        depth,
        aggrebind: totalAggreBind.toFixed(2),
        water: totalWater.toFixed(2),
        total: total.toFixed(2)
    };
}

function sendQuote() {
    if (!window.cotizacionData) {
        alert("Por favor, primero realice el cálculo.");
        return;
    }

    fetch("/enviar_cotizacion", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(window.cotizacionData)
    })
    .then(response => {
        if (response.ok) {
            alert("Cotización enviada correctamente.");
            closeQuote();
        } else {
            alert("Error: Ya tiene una cotizacion pendiente");
        }
    })
    .catch(error => {
        console.error("Error al enviar:", error);
        alert("Error en la conexión.");
    });
}

function closeQuote() {
    document.getElementById('result').style.display = 'none';
    document.getElementById('summary').style.display = 'none';
    document.querySelector('.buttons').style.display = 'none';

    document.getElementById('length').value = '';
    document.getElementById('width').value = '';
    document.getElementById('depth').value = '';
}
