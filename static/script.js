function crearVenta(){

console.log("Intentando crear venta")

fetch("/nueva_venta")
.then(res => {

console.log("Respuesta recibida")

return res.json()

})
.then(data => {

console.log("Datos:", data)

venta_id = data.venta_id

document.getElementById("venta_id").innerText = venta_id

})
.catch(error => {

console.log("ERROR:", error)

})

}