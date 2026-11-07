# Piloto ejecutable: UE5 + inferencia local en dos PCs

**Fecha:** 2026-11-07. Continuación del [contraste de arquitecturas](PIPELINE_ACTUAL_Y_FUTURO.md).

## Objetivo del primer hito

Demostrar una cadena completa para **una función jugable y un asset**: especificación,
paquetes acotados, ejecución local, validación, integración UE5, build empaquetada y
revisión humana. Medir la proporción local/free/premium y el costo por entrega aceptada.

Propuesta inicial de slice: una puerta de acceso con un prerrequisito, feedback visible
y un prop procedural. Reutilizar el estado de interacción y el ejemplo de asset existentes
en NovanodeLab; confirmar el comportamiento actual antes de crear nuevas implementaciones.
La elección final del slice pertenece al humano y no modifica el trabajo activo en Hero Lab.

## 1. Primer componente implementado: inventario de dos hosts

El comando independiente `python3 -m pipeline.hosts` agrega una primera herramienta
de diagnóstico. Usa solo la biblioteca estándar y se ejecuta desde la raíz del proyecto.

### En Ubuntu: rol propuesto de producción

```sh
python3 -m pipeline.hosts inventory --node ubuntu-production --role production
```

### En Fedora: rol propuesto de inferencia

```sh
python3 -m pipeline.hosts inventory --node fedora-inference --role inference
```

`role` declara la responsabilidad propuesta; no afirma que ese servicio ya esté operativo.
El comando imprime JSON. Solo ejecuta una consulta de lectura de `nvidia-smi`, con timeout
de cinco segundos. Localiza otros ejecutables mediante PATH sin ejecutarlos. No se conecta
a servidores, no carga modelos y no abre el editor.

Registra:

- Fecha UTC, etiqueta del nodo y hostname.
- Distribución, kernel, CPU y memoria RAM visible para Linux.
- Espacio libre en el filesystem del checkout; `--disk-path /ruta/existente` permite
  medir el volumen que realmente alojaría engine, modelos y builds.
- GPU, UUID, driver y VRAM total/usada/libre informada por el driver.
- Rutas de herramientas encontradas, **sin inferir versión ni compatibilidad**.
- Datos faltantes como `null` y consultas GPU fallidas como `unknown`, sin reutilizar
  observaciones anteriores ni registrar stderr de procesos.

No enumera procesos ni lee variables de entorno con credenciales o configuraciones de
proveedores. El snapshot sí contiene hostname, UUID de GPU y rutas locales: es evidencia
operativa interna, no un informe para publicar automáticamente.

### Guardar y comparar evidencia

En cada PC, crear el directorio y guardar un archivo nuevo con fecha:

```sh
mkdir -p .studio/evidence/hosts
```

En Ubuntu:

```sh
python3 -m pipeline.hosts inventory --node ubuntu-production --role production > ".studio/evidence/hosts/ubuntu-$(date -u +%Y%m%dT%H%M%SZ).json"
```

En Fedora:

```sh
python3 -m pipeline.hosts inventory --node fedora-inference --role inference > ".studio/evidence/hosts/fedora-$(date -u +%Y%m%dT%H%M%SZ).json"
```

Transferir el snapshot por la conexión privada acordada, preservando el original.
No hay descubrimiento automático de PCs ni un hostname SSH supuesto.
Con ambos archivos en la misma PC, reemplazar las rutas del siguiente ejemplo:

```sh
python3 -m pipeline.hosts compare .studio/evidence/hosts/ubuntu-FECHA.json .studio/evidence/hosts/fedora-FECHA.json
```

| Resultado | Significado |
|---|---|
| `inventory_complete`, salida 0 | Dos inventarios recientes con roles distintos y la base de hardware observada. Continúan pendientes los gates operativos. |
| `blocked`, salida 1 | Faltan observaciones, hay duplicados, datos inválidos, hardware distinto de la base o snapshots obsoletos. Revisar `issues`. |
| `error`, salida 2 | Archivo inexistente, formato inválido o entrada no admitida. |

La comparación requiere snapshots de las últimas 24 horas, con hasta 60 segundos de
tolerancia de reloj futuro. Detecta GPU duplicada aunque se cambien las etiquetas de nodo.
El hostname duplicado exige revisión; no demuestra por sí solo que sea la misma máquina.
La base esperada es Linux, al menos 60 GiB de RAM visible y una RTX 3090 con al menos
23 GiB reportados, tolerando reservas de sistema respecto de los 64/24 GiB nominales.

**`inventory_complete` no significa `pipeline_verified`.** Estos archivos son observaciones
no firmadas, no atestaciones de hardware. No prueban red, CUDA funcional, disponibilidad de
servicios, capacidad de un modelo ni identidad de su cuantización. La VRAM debe medirse
nuevamente antes de cada carga. El espacio libre se registra; la capacidad necesaria se
calcula después de seleccionar los artefactos y su política de retención.

## 2. Plan de trabajo y dependencias

Estos son paquetes de planificación, **no contratos ejecutables del runner**. Cada uno
debe convertirse en un contrato compatible con `studio.py task context` antes de su
ejecución, una vez conocidos sus archivos, comandos y límites. No usar placeholders como
acciones automáticas ni ejecutar paquetes que dependen de evidencia ausente.

| ID | Depende de | Entregable acotado | Aceptación y evidencia |
|---|---|---|---|
| P01 | — | Inventario local y comparador. | Tests del diagnóstico y snapshot real del primer host. Implementación incluida en esta etapa. |
| P02 | P01 | Inventario del segundo host y asignación de roles. | Dos snapshots distintos y recientes; confirmar engine funcional actual, discos y servicios que deben preservarse. |
| P03 | P02 | Conexión privada entre estación y servidor. | Ruta y autenticación elegidas por el dueño; prueba de conectividad sin endpoint público. |
| P04 | P02 | Selección de dos candidatos locales. | Modelo pequeño y mayor, revisión/hash, quant, runtime y plantilla identificados; descarga solo si está autorizada. |
| P05 | P03, P04 | Calificación del transporte de herramientas. | Una petición activa; lectura, llamada de herramienta, resultado y edición controlada funcionando desde el harness real. |
| P06 | P05 | Benchmark de coding representativo. | Mismos casos y contexto para ambos candidatos; métricas y defectos observados, no scores de tarjetas de modelo. |
| P07 | P02 | Inventario de comportamiento del slice y especificación versionada. | Confirmar proyecto, estado de puerta/interacción y asset existentes; definir únicamente el cambio necesario. |
| P08 | P05 | Contabilidad integral de solicitudes. | Consumo local/free/premium, retries y auxiliares conciliados; valores desconocidos explícitos. |
| P09 | P06, P07, P08 | Paquete de lógica del prerrequisito. | Caso válido e inválido verificados, sin duplicar el sistema de interacción; consumo e intentos registrados. |
| P10 | P06, P07, P08 | Paquete de asset y exportación reproducible. | Fuente, escala, pivote, geometría, materiales y procedencia comprobados con el export real; consumo e intentos registrados. |
| P11 | P09, P10 | Integración UE5 bajo dueño único. | Import correcto, build nativa y comportamiento/collision del slice comprobados. |
| P12 | P11 | Build empaquetada y smoke del slice. | Resultado fresco vinculado a revisión de código/assets, logs y mediciones de rendimiento. |
| P13 | P12 | Revisión humana. | Controles, gameplay y aspecto aprobados por humano; defectos restantes registrados. |
| P14 | P08, P13 | Evaluación del piloto y decisión de ampliar. | Tokens y gasto conciliados, proporción 95/5 observada, tiempo/costo por entrega y siguiente hito acordado. |

La contabilidad debe estar activa antes de los paquetes de contenido. Registrar también
los consumos anteriores de planificación y benchmark; si no se pueden reconstruir, la
métrica se etiqueta como parcial. Ningún paquete se aprueba a partir del documento solo.

## 3. Qué debe resolver el benchmark

Empezar con tres casos pequeños derivados del repositorio, en copias de trabajo aisladas:

1. **Navegación y herramientas:** localizar un símbolo real, leer su contrato y devolver
   una respuesta verificable sin editar. Comprobar el round-trip de herramientas.
2. **Cambio de código:** una modificación conocida con comportamiento esperado y pruebas
   independientes; medir si el modelo usa APIs existentes y respeta las escrituras.
3. **Reparación:** un error acotado en una copia de trabajo, con salida real del compilador
   o validador. No introducir fallos deliberados en el checkout de producción.

Registrar por intento: revisión base, contrato, modelo/hash/quant, runtime/plantilla,
contexto y límite de salida, tiempos, VRAM, resultado de herramientas, diff y verificaciones.
Comparar finalización correcta y costo temporal, además de tokens por segundo.

Usar como máximo dos intentos por paquete; timeout o resultado desconocido exige
checkpoint y conciliación antes de volver a enviar. Un timeout de inferencia no se
interpreta como prueba de que el servidor dejó de trabajar.

## 4. Política inicial de modelos y presupuesto

- **Local:** ruta predeterminada después de P05/P06, con una solicitud activa.
- **Free:** complemento explícito, una vez calificados cuota, transporte y tratamiento
  de datos; no es requisito para que el pipeline local funcione.
- **Premium:** arquitectura, ambigüedades importantes y revisiones de hito. Requiere
  presupuesto autorizado y una reserva/ID de trabajo persistidos antes de esperar.
- **Gasto de este piloto aún no autorizado:** la preparación técnica usa presupuesto
  de nuevas llamadas premium de USD 0. Esto no contabiliza ni declara gratuita esta
  conversación externa con el agente.
- **Meta:** al menos 95% de tokens local/free y como máximo 5% premium, incluyendo
  intentos fallidos y mantenimiento. Informar también proporción de tareas aceptadas
  sin premium y techo mensual absoluto, todavía pendiente de acordar.

Los valores existentes de `studio.toml` no son autorización nueva ni una garantía de
que solicitudes externas al ledger ya estén limitadas.

## 5. Información necesaria para desbloquear la siguiente etapa

1. **Segunda PC:** acceso al checkout, hostname o alias privado acordado y resultado de P02.
2. **Conectividad:** si ambas PCs comparten LAN y qué conexión privada se utilizará.
3. **Roles actuales:** dónde está la instalación UE funcional y qué servicios deben seguir activos.
4. **Herramientas:** enlaces exactos de «Maya» y «Colibri» y el trabajo que se espera de ellas.
5. **Presupuesto:** techo mensual premium en USD y confirmación del slice inicial.

Las respuestas completan contratos posteriores. Hasta entonces se puede validar la
herramienta de inventario y recopilar evidencia local, pero no afirmar que las dos PCs
ya trabajan como un pipeline integrado.
