# Donde vamos — 22 de agosto de 2026

Nota de continuidad. Lo que esta hecho, lo que falta y de quien depende.

> **SIGREP esta EN PRODUCCION** en https://sigrep.grupo-santacruz.com
>
> **Las dos unidades tienen base propia.** Carnes en `DB SIG-REP`, agropecuaria
> en `sigrep_agro`, sobre el mismo servidor PostgreSQL. `GET /salud` publica
> `bases_separadas: true`.

## Lo primero cuando se retome

**1. Desplegar.** Hay cinco commits empujados sin desplegar. El Environment de
Dokploy ya esta correcto —nueve lineas, sin `SIGREP_VERSION`—; solo falta pulsar
Deploy cuando el CI termine.

**Como saber si entro**: `GET /api/v1/salud` dice hoy `version: 1.0.0`. Cuando
entre lo nuevo dira `1.0.0+<sha>`. Si dice `0.0.0+local`, esa imagen no salio del
CI.

**2. Dias habiles de agosto** para los dos centros. Sin ellos no hay ideal, y sin
ideal el semaforo sale `SIN_PRESUPUESTO` aunque haya presupuesto.

**3. Cargar el presupuesto.** El `AGROPECUARIA.xlsx` del negocio se sube tal
cual: Presupuesto → dimension **Vendedor** → Cargar archivo. Ojo con el periodo:
ese archivo es de **julio** y la pantalla suele abrirse en el mes corriente.

## Estado

| | |
|---|---|
| Backend | FastAPI · **527 pruebas en verde** · ruff y mypy limpios · migraciones hasta `0007` |
| Frontend | React + TS · 17 pantallas · typecheck y build limpios |
| Unidad agropecuaria | Completa: 13 endpoints, 6 pantallas, exportacion a Excel, ingesta probada |
| Bases separadas | **Si**, con la unidad firmada en el token |
| Repositorio | `github.com/Johnnyr-beep/SIG-REP` (privado), 45 commits |

## Lo que hay cargado en produccion

Agropecuaria: **agosto del 1 al 22**, 7.037 lineas, 0 rechazos. Sin presupuesto
capturado todavia.

Carnes: con datos, ultima ingesta del 22 de agosto.

## La decision que bloquea el cumplimiento de agropecuaria

**Cinco vendedores venden y no estan presupuestados**, y suman el 47,8 % de la
venta. Con ellos el cumplimiento de la compania sale **49,85 %**; sin ellos,
**26,00 %**. Ninguna de las dos cifras es «la buena» hasta que el negocio decida.

| Vendedor | Venta en 7 dias de julio |
|---|---|
| AGROPECUARIA SANTACRUZ LTDA (NIT 830505537) | 1.248.608.078 |
| DIAZ RAMOS DIANNY MAGIDY | 180.095.816 |
| SANCHEZ MARTINEZ MANUEL DE JESUS | 41.456.890 |
| HOYOS FARAH UBALDO JERONIMO | 35.404.650 |
| BURGOS BORRERO BELKYS DAYANA | 40.000 |

Dos preguntas: ¿deberian tener presupuesto? Y si no lo tienen a proposito, ¿su
venta debe contar en el cumplimiento de la compania? En carnes se resolvio
listandolos aparte como «venta informativa».

## Errores encontrados en el Excel del negocio

**El total en kilos de la hoja `VENDEDORES` esta mal**: dice 461.270 y la suma da
654.270. Faltan 193.000, que son exactamente los de Call center — la formula se
salta ese canal. Los pesos suman bien.

**Hay tres presupuestos en kilos que no coinciden** entre las hojas `VENDEDORES`,
`TABLA` y la vista dinamica. El bueno es el de `TABLA` (columnas I/J para kilos y
AN/AO para pesos): 659.413,31 kg y 6.315.016.727,26, que es la cifra que sale en
los tableros del negocio.

**El mismo vendedor con dos grafias**: `CABARCA LACHE KAREN DANIEL` y
`CABRERA LACHE KAREN DANIELA`. El cargador cruza contra las cedulas del catalogo
y reporta lo que no case, en vez de adivinar.

## Pendiente del negocio

- Dias habiles de los dos centros de agropecuaria, y de las 7 zonas de carnes.
- Umbrales del semaforo y regla de comision.
- Que hacer con los cinco vendedores sin presupuesto (arriba).
- Con filtro de centro, en los ejes que **no** son el centro la meta no esta
  repartida por centro: el cumplimiento compara la venta de un centro contra la
  meta de los dos. Alternativa: vaciar ahi el cumplimiento. Anotado en el codigo.
- Fuente del historico de 2025.

## Pendiente del administrador de la API SIESA

En `docs/INTEGRACION-SIESA.md`:

| | Que se pide | Estado |
|---|---|---|
| §4.1 | Costo en el modulo `SIN ACUMULAR` | Bloqueante para el margen de PEREIRA |
| §4.4 | `COUNT(DISTINCT documento)` por centro y fecha | Sin el, no hay numero de documentos |
| §4.5 | **Identificador del cliente en `/ventas/agropecuaria`** | Sin el, no se puede saber quien dejo de comprar |

## Deuda conocida

- **Modo de ejemplos sin agro**: `VITE_SIGREP_EJEMPLOS=1` no tiene datos de la
  unidad. No afecta a produccion.
- **Cuatro credenciales pasaron por el chat y siguen sin rotar**: `SIGREP_SECRET_KEY`
  —la mas grave, firma los tokens—, el token de SIESA, la clave de la base y la
  de SIGCOM.
- **El panel de Dokploy sigue en HTTP plano** en el puerto 3000.
- Falta el secreto `DOKPLOY_WEBHOOK_URL` en GitHub. Sin el no hay despliegue
  automatico, pero desde hoy **eso ya no tumba la ejecucion del CI**: avisa.

## Lo que aun no se ha probado nunca

**Cerrar un mes completo con el sistema.** Las dos unidades estan construidas y
verificadas por partes; carnes esta validada punto por punto contra el Excel. Pero
nadie ha cerrado un mes de punta a punta con SIGREP y comparado el resultado.

La comprobacion que lo demuestra: abrir **Resumen de ventas** y recorrer los
siete criterios de agrupacion. **Los siete tienen que dar el mismo total.**
