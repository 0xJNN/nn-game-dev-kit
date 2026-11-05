# Hero Lab para Lyra — prototipo original, no personajes terminados

Fuente reproducible: `projects/hero-sandbox/`. Recursos: `resources/hero-sandbox/catalog.json`.
Trabajamos sobre la copia local de **Lyra 5.8 / Unreal 5.8.4 para Linux**, no sobre NovanodeLab.

## Hero Training v3 — integración local en curso

Objetivo: **Lobby → Hero Training → elegir Melee o Mage → tres bots rivales → volver al lobby**.
La compatibilidad de clases Lyra/IK y los imports existentes ya pasó en un commandlet de solo lectura
con salida normal y cero errores. Eso no verifica todavía este recorrido de gameplay ni su calidad visual.

La implementación nueva vive en `HeroTraining*`, `hero_training.py`, `prepare_training.py` y
`validate_training.py`. Es **opt-in mediante `-HeroTrainingV3` y solo standalone**: no sustituye los
mapas v1/v2 ni el frontend/modos originales. Añade una pantalla CommonUI sobre el frontend existente,
selección explícita de héroe, una experiencia derivada localmente de los sistemas de Lyra y acciones
propias para equipo, input y equipos rivales. El daño usa `LyraDamageExecution` y el HealthSet nativo,
no el HealthSet de los muñecos v1/v2. El equipo nativo concede y retira las habilidades.

**Estado: fuente implementada; compilación, preparación, recorrido real y revisión humana tienen
gates separados.** Consultar los receipts nuevos antes de considerar v3 ejecutable. Ningún comando
se inicia automáticamente ni se debe repetir una preparación parcial/fallida.

Los comandos son preview salvo `--execute`:

```sh
python3 projects/hero-sandbox/hero_training.py build
python3 projects/hero-sandbox/hero_training.py prepare-v3
python3 projects/hero-sandbox/hero_training.py validate-v3
python3 projects/hero-sandbox/hero_training.py play-v3
```

`build --execute`, `prepare-v3 --execute` y `validate-v3 --execute` son operaciones nativas separadas,
con ownership, identidades exactas, logs locales y un intento por fase. `play-v3 --execute` **abre una
ventana** y exige previamente build/assets coincidentes; no se ejecuta como parte de la preparación.
Su arranque es el frontend, no el laboratorio v2. El stop de v3 es independiente:

```sh
python3 projects/hero-sandbox/hero_training.py stop --dry-run
python3 projects/hero-sandbox/hero_training.py stop --execute --timeout 20
```

Solo selecciona jobs `play-v3-<12 hex>`, verifica también el supervisor y `-HeroTrainingV3`, usa pidfd
y una única SIGINT, y no reescribe el journal nativo. No detiene v2, editor, builds ni servicios.
Un resultado desconocido exige reconciliación; no se reenvía una señal a ciegas. El cierre de un
Unreal real sigue sin estar calificado por estos fixtures.

Controles **implementados, pendientes de probar en el recorrido real**: WASD/ratón de Lyra;
LMB o J para atacar; Q o K para dash de espada; Tab/Esc para el menú de entrenamiento. El HUD propio
muestra salud, cooldowns y número de bots rivales. El menú de pausa permite reanudar o volver al lobby.

La receta crea solo `Content/TrainingV3/`: cinco clips retargeteados al esqueleto del pawn, cinco
montages, equipo/AbilitySet, configuración de tres bots y experiencia. Los montages de espada usan
los ataques A/B/C y dash adquiridos. **El mago usa provisionalmente `OverhandThrow` como gesto de
lanzamiento**, no un recurso mágico dedicado; el staff sigue siendo un placeholder. La claymore
importada mide aproximadamente 659 cm antes de escalarse y se normaliza a 120 cm; el hueso de agarre
y la compatibilidad de esqueletos se comprueban, pero alineación, clipping y apariencia necesitan
revisión visual. No se afirma que los shaders/materiales estén resueltos por encontrar los assets.

La promoción de Content exige un padre verificado, hash idéntico de **cada** asset anterior y
adiciones solo bajo `TrainingV3/`. Una validación v3 completa puede conservar la elegibilidad de los
mapas v1/v2; no cambia sus bytes ni aprueba su arte. Los checks de paquetes no prueban clicks,
input, IA real, daño, muerte/respawn ni retorno al lobby. Red, FPS y packaging quedan fuera de esta etapa.

## Selección y diagnóstico de solo lectura

```sh
python3 studio.py projects list
python3 studio.py projects status --profile hero-sandbox
python3 studio.py doctor --profile hero-sandbox
python3 studio.py run --profile hero-sandbox
```

El último comando **solo muestra** la invocación guardada de `manage.py play-v2`; no inicia Unreal.
El perfil declara proyecto, mapa v2, experiencia y versión 5.8.4, sin cambiar el predeterminado
NovanodeLab. `unreal editor --profile hero-sandbox` también es preview. `--execute` y las otras
operaciones nativas de Hero Lab desde `studio.py` se rechazan; no caen en el adaptador del lab.

El diagnóstico no crea archivos, no importa helpers ni lee logs/assets a contexto de IA. Consulta
metadatos acotados y hashes locales del plugin propio: distingue motor/descriptor compatibles,
recursos con revisión/pin/hold de entrada a IA, jobs sin reconciliar y evidencia histórica.
`historical_unbound` **no es verificación vigente**: los journals anteriores no fijan una identidad
completa de motor/contenido, aunque coincidan fuentes y binario. `stale` indica diferencias;
`identity_unavailable` o cobertura incompleta exige revisión, no repetir ni borrar jobs.
Los gates visuales, red, rendimiento, paquete y aprobación humana siguen separados.

Para diagnosticar el motor, definir `UE_ROOT` a una instalación propia ya autorizada; no se instala
ni se acepta una licencia. La ausencia de `.studio`/Lyra/helpers produce indicaciones sin descargarlos.
**Esto no migra el lanzador**: `manage.py` conserva su ruta de motor local y dependencias ignoradas.
La presencia del helper de entrada no verifica toda esa cadena. Los comandos nativos de abajo
mantienen sus comprobaciones de ownership, fuentes, assets y jobs; no ejecutarlos por un status positivo.

## Presentación v2 — revisión del personaje, cámara y textos

El reporte humano confirmó el problema de la primera versión: se veía el wand, pero no el cuerpo;
los textos estaban invertidos y el mapa parecía estructura gris. La inspección nativa separó las causas:

- **No era necesario esperar más shaders para que apareciera el cuerpo.** El pawn estaba poseído,
  GAS funcionaba y la cámara ya estaba en tercera persona, a **298,6 cm**. Sin embargo, faltaba el
  componente de apariencia del controlador: solo quedaba una malla auxiliar de **4 vértices**.
- Nuestra experiencia v1 había reutilizado PawnData, pero omitido la acción que ensambla las partes
  cosméticas de Lyra. La v2 referencia **solo esa acción de componentes**, no los bots, temporizadores,
  marcador, UI o entrega de armas del modo original.
- La prueba v2 `probe-v2-d6d9a48936f4` confirmó un cuerpo adjunto, visible según los flags del motor,
  con animación vinculada: **48.783 vértices entre cuerpo y proxy**, en vez de cuatro. La cámara se
  conserva; no se construyó otro sistema de cámara ni se sustituyó el movimiento de Lyra.
- Todos nuestros textos v1 tenían un giro fijo de 180°. En la v2 se usa la cara legible de TextRender
  y un giro horizontal hacia el observador, conservando el eje vertical y sin escalas negativas.
  La comprobación visual aislada de texto se registra aparte; no equivale a aprobar el arte del héroe.
- El gris era un **blockout intencional sin materiales propios**, no una demostración de que el motor
  no renderizase. La v2 asigna seis materiales originales sencillos, acentos por zona, iluminación y
  previews CC0 visibles antes de Play. Sigue siendo un laboratorio, no un lobby/escenario terminado.

Mapa nuevo: **`/NovanodeHeroes/Maps/L_HeroSandbox_v2`**. Los **60 archivos de Content preexistentes**
(incluidos mapas v1 e imports) se conservan byte a byte. En el editor, las figuras de exposición son
previews; el jugador poseído se crea al pulsar **Play**. No hay que entrar a un portal: este mapa
selecciona directamente su propia experiencia de Lyra al comenzar la partida.

```sh
python3 projects/hero-sandbox/manage.py play-v2
```

Ese comando entra **directamente al juego**, sin quedarse en el viewport del editor ni en el lobby.
Para editar el mapa, cerrar primero esa ventana y usar:

```sh
python3 projects/hero-sandbox/manage.py editor-v2
```

### Cerrar la partida gestionada

Desde otra terminal, mientras `play-v2` mantiene su lanzador abierto:

```sh
python3 projects/hero-sandbox/manage.py stop
```

Solicita un cierre al **proceso del juego**, no un Ctrl+C al lanzador. Verifica PID/start ticks,
usuario, ejecutable, argumentos/proyecto/mapa, arranque y supervisor. Usa un `pidfd` de Linux
para enviar una única `SIGINT` a ese proceso con handler instalado; no usa `pkill`, señales de
grupo, SIGKILL ni escalado automático. El lanzador original conserva la responsabilidad de
guardar el código de salida real. `stop` nunca reescribe el journal de la partida ni aprueba su calidad.

```sh
python3 projects/hero-sandbox/manage.py stop --dry-run
python3 projects/hero-sandbox/manage.py stop --timeout 30
python3 projects/hero-sandbox/manage.py stop --job-id play-v2-XXXXXXXXXXXX
```

`--job-id` es el ID exacto del journal (12 dígitos hexadecimales, no las X del ejemplo).
El timeout permitido es 1–60 s, 20 s por defecto. Sin partida pendiente, no hace nada. Si hay
varias, exige selección explícita; no detiene `editor-v2`, builds, pruebas ni otros proyectos.
No requiere los helpers ignorados ni toma los locks del editor que la partida mantiene ocupados.

Un timeout, PID ausente/reutilizado, supervisor perdido o journal sin salida confirmada conserva
el resultado **desconocido**. Cada solicitud efectiva deja un receipt `hero-sandbox-stop-*.json`;
si quedó sin resolver, no se envía otra señal automáticamente. Revisar/reconciliar, no borrar el
journal ni repetir a ciegas. Puede cerrarse normalmente la ventana si falta soporte pidfd/handler.
El transporte se prueba con fixtures propios; el cierre de Unreal real requiere comprobación humana.

Las comprobaciones reproducibles de la v2 son `probe-v2`, `probe-v2-rendered` y `smoke-v2`.
El probe con GPU no envía imágenes del sample a IA: solo devuelve métricas estructurales. La captura
aislada de texto no pasó: primero rechazó geometría auxiliar, después produjo una imagen negra
que fue inspeccionada, y una variante de aislamiento terminó con SIGSEGV. **`text-capture` está
deshabilitado y sus evidencias preservadas; no se reintenta ni cuenta como aprobación visual.**
La orientación de texto tiene regresiones matemáticas, pero requiere confirmación humana in-game.
La calidad visual del personaje, agarre,
retargeting de ataques, multijugador y FPS siguen siendo gates independientes.

La pasada actual `probe-v2-rendered-805ab8e5066b` confirmó un cuerpo animado, adjunto y recientemente
renderizado en GPU, con la cámara a 298,6 cm: **salida normal y cero errores/fatals**. La regresión
de combate `smoke-v2-a68186da6d4b` también pasó con **100 → 75 → 55 → 35 → 5**, sin daño duplicado
por swing y con desplazamiento, igualmente con salida normal y cero errores/fatals. Ninguna prueba
es un benchmark de FPS ni una revisión artística. El fallo del fixture aislado no se ocultó ni se
transfirió a la calificación de esas ejecuciones independientes del mapa real.

La receta `prepare_presentation.py` crea assets versionados **una sola vez**; no se debe repetir para
sobrescribirlos. Su validación de paquetes se hace en modo commandlet de solo lectura, conservando
los intentos previos bloqueados. La creación y la validación en editor completo registraron un error
de `AIAssistant`; no se ignoró ni atribuyó al cuerpo. La validación posterior
`validate-v2-ed6ca3133eab` pasó con **salida normal y cero errores/fatals**, sin alterar paquetes.

Los apartados siguientes documentan la base y las evidencias históricas de la v1.

## Qué construimos

- Plugin **NovanodeHeroes**, sin editar el núcleo, mapas originales, configuración o descriptor de Lyra.
- Experiencia/mapa propios: `/NovanodeHeroes/Maps/L_HeroSandbox_v1`.
- Un mismo personaje provisional de Lyra alterna dos kits; todavía no hay selección de campeones.
- **Mago:** proyectil replicado, 25 de daño a muñecos y cooldown de 0,8 s.
- **Espada:** tres ataques de 20 / 20 / 30 de daño, recuperación de 0,42 / 0,42 / 0,65 s,
  ventana de impacto de 0,10–0,27 s y reinicio del combo tras 1,15 s sin continuar.
- **Desplazamiento de espada:** impulso mediante CharacterMovement y cooldown de 2,5 s.
- Muñecos de 100 HP; se restablecen tres segundos después de ser derrotados.
- Feedback provisional: esfera de proyectil, expansión breve al impactar y tres sonidos sintetizados
  localmente. No se ha instalado un pack de Niagara ni MetaSounds y no hay arte final.

Las habilidades se conceden al **ASC/GAS existente del pawn de Lyra**; los muñecos usan un
AttributeSet propio y el daño se aplica mediante GameplayEffects. El servidor decide daño,
cooldowns e impactos. El cliente solo solicita kit/acción: no envía cantidades de daño, destinos
de teleport ni listas de víctimas. Cada muñeco recibe daño una vez por golpe. La espada comprueba
cobertura antes de dañar. Cambiar kit no elimina cooldowns. No hay daño contra jugadores de Lyra
en esta primera versión; no se modificó su HealthSet ni su sistema de muerte/respawn.

La integración es deliberadamente **opt-in por mapa**: un `HeroSandboxDirector` añade el componente
de combate únicamente en este laboratorio. El plugin normal no es todavía un Game Feature con
acciones de activación/desactivación completas. No se sustituyó el sistema de movimiento de Lyra.
Los cooldowns están en estado autoritativo del componente, no todavía en GameplayEffects de
duración configurables. Las activaciones son `ServerOnly`: la predicción local/latencia requiere
otra etapa, no una promesa de que ya tiene el tacto de un juego competitivo.

## Cómo probar

Cierra normalmente cualquier editor antes de integrar o compilar. No ejecutes dos comandos de
motor a la vez ni detengas tus servicios de IA para liberar VRAM.

```sh
python3 projects/hero-sandbox/manage.py build
python3 projects/hero-sandbox/manage.py prepare
python3 projects/hero-sandbox/manage.py test
python3 projects/hero-sandbox/manage.py smoke
python3 projects/hero-sandbox/manage.py editor
```

`prepare` requiere las dos adquisiciones verificadas descritas en
[`resources/hero-sandbox/README.md`](../resources/hero-sandbox/README.md). Reutiliza los recursos
propios ya importados, no descarga packs automáticamente ni cambia preferencias persistentes.
Después de abrir el editor, pulsa **Play**:

| Control | Acción |
| --- | --- |
| WASD + ratón | Movimiento/cámara de Lyra |
| **1** | Kit mago |
| **2** | Kit espada |
| **J** | Lanzar proyectil o atacar; pulsaciones separadas encadenan el combo |
| **K** | Desplazamiento, solo con espada |

Se usan teclas dedicadas para no confundir el ataque experimental con el arma original del
sample. La presentación/equipo/locomoción del mannequin sigue siendo provisional. Este bind directo
es una integración mínima; la siguiente etapa debe llevarlo al InputConfig/AbilitySet del héroe.

Para el menú y los modos originales, sin el director experimental:

```sh
python3 projects/hero-sandbox/manage.py gold
```

El antiguo `.studio/launch_lyra.py` tiene una lista exacta de fuentes y rechazará la adición del
plugin. **No se debilitó ni editó ese lanzador.** El nuevo verifica los mismos 818 hashes originales,
la bóveda y, por separado, nuestra extensión. La ruta de juego original permanece disponible con
`gold`; el plugin solo registra su propio directorio de experiencias fuera del laboratorio.

## Animaciones y modelos: qué significa “reutilizar”

La biblioteca gratuita **UAL2 Standard** se importó en la primera preparación como **43 secuencias
Unreal, nueve con nombre de espada, y una malla esquelética**. No confundas esos objetos importados
con los 130+ clips anunciados para el pack completo o con 43 ataques distintos. Se conservó la
variante sin root motion para empezar; el archivo con root motion permanece en la descarga.

En el mapa se preparan demostraciones con el **rig propio del pack**. Esto permite comprobar un
recurso sin cambiar la locomoción de Lyra. **No son montages retargeteados al jugador de Lyra.**
La espada del jugador tiene un movimiento procedural provisional del arma; el cuerpo todavía no
reproduce los clips de combate importados. El staff es un placeholder original hecho con primitivas.
La claymore CC0 se importa localmente, pero agarre, escala, orientación y aspecto requieren revisión.
El dagger no se importó: el servidor devolvió HTML y el control de tipo lo rechazó.

Próximo trabajo artístico: validar el rig → IK Rig/IK Retargeter → comprobar pie/mano y root motion
→ montar un ataque sobre la capa correcta de Lyra → alinear la ventana de daño autoritativa →
revisar en dos clientes. Un clip de “slash” no incorpora por sí solo daño, cancelaciones o combo.
Los recursos permitidos para el motor no se suben por ello automáticamente a una IA.

## Verificación y límites

- **92 regresiones de repositorio pasaron** en la pasada final auditada
  `hero-sandbox-v1-3d145b13b0ff`, incluidas regresiones de mapa parcial e identidad fuente/binario
  y reglas C++ compiladas desde el mismo header
  del componente y controles de licencias/descarga/ZIP. No prueban el render ni el transporte de red.
- El plugin compila con el toolchain estricto del motor; los **818 archivos base y la bóveda**
  permanecen iguales. La primera compilación encontró un nombre de argumento requerido por las
  macros de replicación; se corrigió y se añadió una regresión, sin relajar el compilador.
- La primera preparación importó recursos, pero falló al asignar una propiedad de WorldSettings
  que Python considera de solo lectura en instancias. Se preservó el mapa parcial y su inventario.
  Un adaptador nativo acotado solo puede asignar nuestra experiencia a nuestros mapas: no cambia
  la clase por defecto ni ningún mapa del sample. La preparación posterior
  `prepare-234ebd983803` **pasó**, con mapa/experiencia/recursos guardados, salida 0, marcador de
  cierre normal y cero errores/fatals.
- Las **tres pruebas nativas de reglas** reportaron `Success` en `test-b74b5362d4a4`. La salida fue
  0, sin errores/fatals, pero faltó el marcador estricto de cierre normal; el lanzador conserva esa
  salvedad como `blocked` en vez de falsear una aprobación completa de ciclo de vida.
- El smoke real del mapa **pasó** en `smoke-2f06abeaaec7`: vida **100 → 75 → 55 → 35 → 5**,
  cuatro activaciones primarias, un proyectil, daño una vez por swing y desplazamiento. Salida 0,
  marcador normal y cero errores/fatals. Es ejecución **standalone, NullRHI, con solicitudes por API**:
  no acredita teclas físicas, animación retargeteada, red, imagen, sonido escuchado ni FPS.
- El smoke anterior detectó un spawn demasiado cercano al dueño y una selección ambigua de canales
  de colisión. Se corrigieron usando una salida de proyectil fuera de la cápsula, comprobación de
  cobertura hasta la salida y `AddObjectTypesToQuery(ECC_Pawn)` explícito. El smoke conserva los
  valores de vida y contadores para no ocultar regresiones. No se eliminó la prueba de daño.
- El modo `-game` del ejecutable de editor intentaba cargar scripts Python de inicialización para
  herramientas de editor y registraba 58 errores. La pasada aceptada usa el argumento documentado
  **`-DisablePython` solo en esa sesión de juego**; no se editó el sample ni se ignoraron errores.
  Preparación y editor siguen usando su ruta correspondiente. Referencia:
  [argumentos oficiales](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-command-line-arguments-reference).
- El lanzador exige una compilación exitosa que coincida con **fuente y binario exactos**, y que el
  mapa/assets coincidan con la preparación completa. Un `.so` viejo tras una compilación fallida,
  un mapa parcial o archivos propios modificados sin revisar no se aceptan por existir en disco.
- **Sesión gráfica iniciada:** job `editor-86c4f6e041b5`, PID **138488**. La observación estructural
  confirmó proceso e inicialización, no visibilidad ni aprobación humana. El editor registra errores
  en las categorías PixelStreaming2RTC, PIE/Blueprint y AIAssistant. No hay causa/impacto establecidos
  por esa clasificación; no confundir el smoke standalone aceptado con una pasada gráfica sin errores.
  Evidencia: `.studio/evidence/hero-sandbox-editor-error-categories.json`. No se cambian código,
  scripts, mapas o configuración mientras esta sesión está abierta: cerrar/checkpoint antes de corregir.
- Los resultados nativos/de gameplay se registran en `.studio/evidence/hero-sandbox-job-*.json`;
  los logs crudos y los assets están solo en `.studio/`. Un exit code 0 sin resultado fresco no basta.
- **Revisión visual, retargeting del jugador, sonido escuchado, FPS/frame times, pruebas de red y
  aceptación humana siguen pendientes.** No se han ejecutado dos clientes ni un benchmark gráfico.
  La siguiente etapa debe verificar RPC/replicación y luego medir el recorrido, antes de presentar
  este laboratorio como un héroe multijugador terminado.

Para medir rendimiento real, repetir el mismo recorrido con caché caliente y registrar `stat fps`
y `stat unit` (Frame/Game/Draw/GPU). No atribuir una mejora del arranque a una mejora medida de FPS.
No se han reducido los gráficos globales ni cambiado los ajustes persistentes para ocultar lag.
