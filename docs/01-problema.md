# 01 — El problema

## Situación actual

Un restaurante de tamaño mediano guarda su producto perecedero en cinco equipos de frío: pescados y mariscos, carnes y aves, lácteos, verduras y un congelador. Hoy el control funciona así:

- Un cocinero anota la temperatura en una hoja pegada en la puerta, dos o tres veces por turno.
- Nadie revisa en la noche ni cuando el restaurante está cerrado.
- Si una puerta queda mal cerrada o un compresor falla, se descubre cuando alguien abre la cámara, a veces horas después.
- Cuando pasa, el producto se tira "por si acaso", sin saber cuánto tiempo estuvo fuera de rango ni cuánto dinero se perdió.
- El inventario (lo que hay, cuánto costó y cuándo caduca) vive en otro sistema o en una hoja de cálculo, sin relación con las temperaturas.

## Por qué importa

1. **Dinero.** El pescado y la carne son lo más caro del inventario y lo que más rápido se echa a perder. Una sola noche con la cámara de pescado fuera de rango puede costar miles de pesos.
2. **Salud.** Un producto que estuvo fuera de rango y no se detectó puede terminar en un plato. La NOM-251-SSA1-2009 pide mantener los refrigerados a 4 °C o menos y los congelados a −18 °C o menos, y llevar registro.
3. **Inspecciones.** Una hoja a mano no demuestra nada: se puede llenar después y no muestra lo que pasó entre una anotación y otra.
4. **Decisiones a ciegas.** El gerente no sabe qué cámara falla más, a qué hora se abren más las puertas ni cuánto se pierde al mes por mala refrigeración.

## A quién le duele

| Persona | Qué le pasa hoy |
|---|---|
| Jefe de cocina | Responde por el producto, pero no puede estar revisando las cámaras todo el día ni de noche |
| Gerente o dueño | Ve la merma en el estado de resultados, pero no sabe de dónde viene |
| Cocineros | Llenan la hoja como trámite y no tienen forma de saber si una cámara está fallando |
| Clientes | Son los que reciben el riesgo si un producto en mal estado no se detecta |

## Qué tiene que resolver FríoTrack

1. Medir temperatura, humedad y puerta de cada cámara de forma continua, sin que nadie anote nada.
2. Avisar al jefe de cocina por SMS en cuanto una cámara sale de rango, aunque no esté en el restaurante.
3. Saber qué lotes de producto están en cada cámara y cuánto valen, para decir "hay $4,850 en riesgo" y no solo "la cámara 1 está a 3 °C".
4. Registrar automáticamente la merma cuando un producto pasa demasiado tiempo fuera de rango.
5. Dejar un historial que sirva como evidencia ante una inspección.
6. Mostrar todo en un dashboard que se pueda ver desde el celular.

## Fuera de alcance del Prototipo Alfa

- Sensores físicos: se simulan.
- Integración con un ERP real del mercado: se emula la parte de inventario dentro del backend.
- Varias sucursales: el prototipo es de un solo restaurante.
