# Hero Lab para Lyra — prototipo original, no personajes terminados

Fuente reproducible: `projects/hero-sandbox/`. Recursos: `resources/hero-sandbox/catalog.json`.
Trabajamos sobre la copia local de **Lyra 5.8 / Unreal 5.8.4 para Linux**, no sobre NovanodeLab.

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
