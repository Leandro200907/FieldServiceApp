# Trazabilidad de servicios de campo: de la ODV a la factura

**Análisis de dominio, actores, casos de uso y requisitos**
Documento de trabajo — versión 3 — septiembre de 2026

> **Cambios respecto de la versión 2.** (1) Notación de la matriz: se separa la **conformidad** del inspector (C) de la **aprobación interna** (A). (2) La plataforma deja de figurar como actor de sus propios casos de uso; el reloj y los sistemas externos sí son actores. (3) La aprobación interna del parte pasa a ser **opcional** (hoy no existe en la práctica). (4) La conformidad del inspector admite tres canales: en sitio, enlace por mail y enlace por WhatsApp. (5) Planificador y almacén quedan fuera de alcance de la v1. (6) Se incorpora el rol real de Seguridad e higiene. (7) Se corrigen inconsistencias entre la matriz de casos de uso y los perfiles. (8) Se agrega la regla de segregación de funciones y la fórmula de autorización.

> **Aclaración de fondo sobre el rol de la empresa.** La empresa de servicios **no certifica ni emite habilitas**. Eso lo hace la operadora. Lo que la empresa produce en campo es el **parte / hoja de trabajo**: el técnico selecciona la o las líneas de la ODV, edita las cantidades ejecutadas y genera un formulario estándar que se envía al inspector para su **firma electrónica**. Con ese parte firmado, la empresa lo sube al portal de la operadora, y recién ahí la operadora emite el **certificado / habilita**, que es el documento que autoriza a facturar. Firma del parte y certificado son dos hechos distintos y en ese orden. Todo el documento usa ese vocabulario.

---

## 1. De qué se trata el proyecto

Producto SaaS de trazabilidad para empresas de servicios de campo en oil & gas. Toma la ODV que espeja la OC del cliente y la abre en sus líneas de servicio, y sigue cada línea a lo largo de todo su recorrido —trabajo asignado, ejecutado, parte firmado por el inspector en campo, certificado emitido por la operadora, saldo consumido contra lo contratado y factura emitida— mostrando en un tablero el estado de cada una y dónde se traba la plata.

Resuelve un problema que en la práctica es de caja: servicios prestados cuyo parte nunca se firma, partes firmados que quedan sin subir al portal, certificados que la operadora no emite a tiempo, líneas de orden de compra que se agotan sin que nadie avise, y facturas emitidas contra imputaciones mal hechas que el cliente rechaza.

Contempla además el control de la documentación habilitante de cada Field Service (para no asignar a alguien con un documento vencido) y un Gantt de control de tiempos del Field Service, real contra estimado, con causas.

El alcance de la v1 llega hasta la facturación, sin cobranzas ni interfaz bancaria. El modelo comercial es entrega del producto más suscripción mensual, y el mercado inicial es la cuenca neuquina.

> **Tesis del producto.** No es una ticketera ni un gestor documental. Es un **control de consumo de contrato con evidencia firmada**. Todo lo que no aporte a esa definición es accesorio.

---

## 2. Por qué no es una ticketera genérica

Cualquier ticketera cubre el mismo núcleo: objeto con identificador y adjuntos, clasificación por tipo y prioridad, máquina de estados, asignación a responsables y colas, SLA con relojes y alertas, hilo de comentarios, log de cambios, reportes de backlog y tiempos, y transversales de usuarios, roles y multiempresa. Ese es el 80% común, y es también la razón por la que el mercado genérico está saturado y con precios de commodity.

Buena parte de ese esqueleto ya está en este producto: la línea de ODV funciona como el ticket, el parte firmado como el adjunto probatorio, la emisión del certificado como la transición que habilita facturar, y el vencimiento del plazo del certificado como el SLA. La diferencia está en lo que una ticketera no tiene:

- **consumo contra un saldo contratado**
- **firma del inspector en campo sobre el parte, como evento que dispara el pedido de certificado**
- **conciliación del certificado contra el parte, y de la factura contra el certificado**

De ahí se desprenden dos riesgos. Generalizar antes de tiempo —campos dinámicos, workflows configurables, tipos de ticket arbitrarios— duplica el esfuerzo sin mover la aguja del cliente. Y posicionarse como ticketera invita a la comparación con Jira y con el precio de Jira; posicionarse como control de servicio y facturación invita a la comparación con la plata que hoy se pierde.

La generalidad, si la hay, va puertas adentro: un núcleo de *entidad con estados y evidencia* reusable entre este producto y el de remitos y conformados. Genérico por dentro, específico por fuera.

---

## 3. Actores

### 3.1 Del lado de la empresa de servicios (cliente que paga)

- **Técnico / cuadrilla de campo.** Ve las órdenes de trabajo del día, selecciona la o las líneas de ODV que está trabajando, edita las cantidades ejecutadas, adjunta evidencia y genera el parte para enviarlo a la firma del inspector en el yacimiento. Trabaja offline.
- **Supervisor / jefe de base.** Revisa los legajos de documentos habilitantes de cada Field Service (matrícula, curso de seguridad, ART, apto médico, etc.) con su vencimiento. Asigna trabajos, corrige imputaciones y persigue lo que quedó sin firmar. Si la empresa habilita la aprobación interna (opcional, ver 11.3), revisa y aprueba el parte. Da seguimiento al Gantt.
- **Seguridad e higiene.** Consigue toda la documentación habilitante que necesitan los técnicos y hoy la distribuye subiéndola a un drive o enviándola por mail a los técnicos, al supervisor o a ambos. En el sistema, es quien carga y actualiza los documentos en el legajo de cada técnico. En oil & gas no es opcional: un documento faltante o vencido bloquea la prestación del servicio.
- **Planificador** *(fuera de alcance v1)*. Recibe el pedido de la operadora y arma la agenda. En la v1 la planificación y asignación la hace el supervisor.
- **Almacén / pañol** *(fuera de alcance v1)*. Entrega materiales y repuestos que se imputan como consumo contra la línea. En la v1 el consumo de materiales lo registra el técnico en el parte.
- **Administración / facturación.** Recibe el parte firmado por el inspector, lo sube al portal de la operadora, hace el seguimiento hasta que llega el certificado, lo cruza contra el parte, emite la factura y la carga en el portal del cliente. Necesita ver el vínculo factura ↔ certificado ↔ parte ↔ líneas de ODV para defender un rechazo.
- **Comercial.** Carga la ODV espejo de la OC del cliente con sus líneas y saldos, monitorea consumo por contrato y mira los indicadores del tablero.
- **Administrador de la empresa.** Usuarios, roles y permisos, datos maestros, plantillas de parte, reglas de aprobación e integraciones. Rol de configuración, no de operación diaria.
- **Subcontratista.** Es el técnico con alcance recortado: mismos casos de uso, visibilidad limitada a sus propias órdenes de trabajo, sin acceso a precios.

### 3.2 Del lado de la operadora (no pagan, pero sin ellos no cierra el circuito)

- **Inspector.** Presta su conformidad sobre el parte firmándolo. Es un actor **externo, participante y no usuario**: participa en un caso de uso (dar conformidad al parte), pero no tiene cuenta, no inicia nada y no consume licencia. En campo a veces se lo llama «certificador», pero **no emite el certificado**: eso lo hace el contract administrator, después, en el portal. Por eso el sistema lo llama siempre «inspector».
- **Contract administrator / comprador.** Emite y amplía la OC. Recibe el parte firmado que se sube al portal, y **emite el certificado / habilita (HES)** que envía al cliente. No usa el sistema, pero define la estructura de líneas que hay que replicar fielmente.

La OC trae los datos de contacto (mail y WhatsApp) del inspector y del contract administrator. Al inspector se le envía el parte para su firma; al contract administrator, el parte firmado y el reclamo del certificado / habilita.
- **Cuentas a pagar.** Recibe la factura y los respaldos. El producto gana o pierde ahí.

### 3.3 Otros

- **Administrador de la plataforma** (el operador del SaaS): tenants, planes, salud del sistema, soporte con acceso auditado, migraciones, versiones. No debe poder tocar datos de negocio sin dejar rastro.
- **Auditor externo / contador.** Solo lectura sobre la evidencia. Define requisitos de retención y exportación.
- **Sistemas externos y reloj:** el ERP del proveedor, el portal de la operadora (Ariba, Coupa o propio), ARCA para el CAE, y el reloj —los vencimientos inician casos de uso propios. Estos sí son actores.
- **La plataforma no es actor de sus propios casos de uso.** Sus validaciones, cálculos y verificaciones (incluido el agente que controla exactitud entre ODV y OC, entre certificado y parte, y entre certificado y factura) son comportamiento del sistema: aparecen dentro de la descripción de cada caso de uso, no como un actor más.

> **Sobre el inspector.** Modelarlo como usuario sería un error caro: alta de credenciales, recuperación de contraseña y soporte a gente que no paga y que rota permanentemente; ninguna operadora va a registrar a sus inspectores en el sistema de un proveedor; y aparecen cuentas externas dentro del tenant del cliente. Lo que sí necesita es **identidad registrada aunque no autenticada**: nombre, DNI o legajo, empresa, cargo, y la constancia de cómo firmó el parte. Es un dato del hecho, no un perfil.

---

## 4. Matriz de actores y casos de uso

Referencias: **E** ejecuta · **A** aprueba internamente (decisión de la empresa) · **C** presta conformidad (manifestación de un tercero; no es una autorización dentro del sistema) · **L** solo lectura · **→** recibe la notificación.
TEC técnico · SUP supervisor · SYH seguridad e higiene · FAC administración / facturación · COM comercial y gerencia · ADE administrador de la empresa · SUB subcontratista · INS inspector · AUD auditor · REL reloj (disparador por tiempo) · POR portal de la operadora · ARCA.

### 4.1 Contrato y órdenes (OC del cliente → ODV espejo)

| Caso de uso | Actores |
|---|---|
| Alta de ODV con líneas, precios y saldos, espejando la OC (incluye los contactos del inspector y del contract administrator) | COM E · FAC L |
| Ampliar o modificar líneas de ODV | COM E · SUP L |
| Consultar saldo disponible por línea, en importes | COM L · FAC L · SUP L |
| Consultar disponibilidad de saldo por línea, como semáforo | TEC L · SUB L |
| Alerta de saldo por agotarse (se dispara al recalcular el saldo tras la firma de un parte) | → COM, SUP |
| Cerrar o anular ODV | COM E · aprobación a definir (ver pendientes) |

### 4.2 Asignación, ejecución y parte / hoja de trabajo

| Caso de uso | Actores |
|---|---|
| Cargar y actualizar documentos habilitantes en el legajo del técnico o subcontratista | SYH E · SUP L |
| Consultar el propio legajo en el dispositivo, también offline | TEC L · SUB L |
| Alerta por documento habilitante próximo a vencer | REL → SYH, SUP |
| Crear orden de trabajo contra línea de ODV | SUP E |
| Asignar cuadrilla o subcontratista (incluye validar la vigencia de los documentos habilitantes; si hay alguno vencido, bloquea o exige excepción registrada) | SUP E |
| Seleccionar la/s línea/s de ODV que se está trabajando y editar cantidades | TEC E · SUB E |
| Registrar avance, horas y equipos en campo | TEC E · SUB E |
| Registrar materiales consumidos | TEC E · SUB E |
| Adjuntar evidencia (fotos, mediciones, ATS) | TEC E · SUB E |
| Registrar horas improductivas con causal, cuando no se puede prestar el servicio por causas ajenas | TEC E · SUB E |
| Generar el parte / hoja de trabajo desde la orden ejecutada | TEC E · SUP E |
| Revisar y aprobar internamente el parte *(opcional, configurable por tipo de servicio)* | SUP A |
| Enviar el parte al inspector por enlace de un solo uso, por mail o WhatsApp, al contacto que figura en la ODV | TEC E · SUP E |
| Editar la identidad del inspector si en el momento firma alguien distinto del que figura en la ODV | TEC E |
| Prestar conformidad en sitio, firmando en el dispositivo del técnico (admite offline) | TEC E · INS C |
| Prestar conformidad por enlace | INS C |
| Marcar inicio y fin de trabajo (base del Gantt) | TEC E |
| Sincronizar trabajo cargado offline (automático al recuperar señal) | TEC E |

### 4.3 Portal de la operadora y certificado / habilita

| Caso de uso | Actores |
|---|---|
| Subir el parte firmado al portal de la operadora | FAC E · POR |
| Enviar el parte firmado al contract administrator y reclamarle el certificado / habilita | FAC E |
| Alerta por vencimiento del plazo de entrega del certificado que surge de la OC/ODV | REL → FAC |
| Recibir el certificado (mail o drive) y cruzarlo contra el parte (la plataforma asiste el cruce) | FAC E |
| Registrar número de certificado recibido | FAC E |
| Registrar rechazo, observación o certificado parcial | FAC E |
| Reclamar la diferencia cuando el certificado no coincide con el parte | FAC E |

### 4.4 Facturación

| Caso de uso | Actores |
|---|---|
| Ver partes con certificado recibido, listos para facturar | FAC E |
| Verificar saldo antes de emitir (la plataforma calcula) | FAC E |
| Emitir factura vinculada a uno o más certificados | FAC E · ARCA |
| Controlar aprobación de la factura electrónica | FAC E |
| Registrar rechazo de factura y recircular | FAC E · COM L |
| Exportar respaldo completo de un caso | FAC E · AUD L |

### 4.5 Control y administración

| Caso de uso | Actores |
|---|---|
| Tablero de estados por línea y cuellos de botella | COM E · SUP L · FAC L |
| Vista Gantt de ODV asignadas por técnico, tiempo estimado vs. real (a partir del inicio y fin de tarea marcados en campo) | SUP L · COM L |
| Consultar log de auditoría | ADE L · AUD L |
| Alta y baja de usuarios, asignación de permisos | ADE E |
| Configurar maestros, plantillas y reglas de aprobación | ADE E |
| Configurar integración con ERP | ADE E · ERP |

> **Tres conclusiones que salen de la matriz.**
> 1. El inspector aparece siempre prestando conformidad (C), nunca ejecutando ni aprobando en el sentido interno: no necesita cuenta.
> 2. Ningún actor operativo puede editar un parte firmado; el único camino es anular y rehacer con aprobación. Esa regla sostiene todo el argumento probatorio.
> 3. De acá salen cinco perfiles base —campo, supervisión, administración, comercial y configuración— más dos accesos de solo lectura. Los permisos deben ser **acumulables**: en empresas chicas el jefe de base también factura y administra usuarios. Cuando un caso de uso lo ejecuta alguien que no tiene el perfil que le corresponde (por ejemplo, el supervisor registrando un certificado), es porque acumula ese perfil, no porque su perfil lo incluya.

---

## 5. Requisitos no funcionales

**Conectividad y datos.** Operación offline completa con sincronización diferida y resolución de conflictos. Tolerancia a días sin señal. Compresión de fotos: la subida se hace con datos móviles caros y lentos. La lista de líneas de ODV debe descargarse antes de salir a campo, no consultarse en el momento.

**Integridad probatoria.** Log inmutable con quién, qué y cuándo. Parte firmado no editable. Sellado de tiempo y geolocalización en tiempo real del momento de la firma. Retención de documentos por el plazo fiscal y contractual (mínimo diez años en Argentina). Exportación completa de la evidencia de un caso.

**Seguridad.** Multi-tenant con aislamiento estricto entre empresas. Permisos acumulables por rol. Cifrado en tránsito y en reposo. Manejo del dispositivo perdido o robado, que en campo ocurre.

**Usabilidad en contexto real.** Uso con guantes, a pleno sol, con la tablet mojada. Generar un parte en menos de dos o tres minutos. Pantallas legibles para gente que no es de sistemas. Si al técnico le cuesta, no lo usa y el producto muere ahí.

**Operación.** Disponibilidad razonable —esto no es control de proceso— pero con backup y restauración probados. Alta de un tenant nuevo sin intervención de desarrollo. Migración de datos históricos en el onboarding.

**Documentación del personal.** Cada técnico y subcontratista tiene un legajo de documentos habilitantes (matrícula, curso de seguridad, ART, apto médico, etc.) con fecha de vencimiento propia. El sistema debe impedir o alertar la asignación a una línea de ODV si algún documento requerido por la operadora está vencido al momento de asignar, no recién cuando el trabajo ya se ejecutó.

**Cumplimiento y localización.** Ley 25.326 de protección de datos personales. Requisitos de facturación electrónica de ARCA si se emite desde el sistema. Ley 25.506, que define hasta dónde el parte firmado en tablet es oponible. Castellano rioplatense, pesos y dólares, huso horario argentino.

---

## 6. El arranque del circuito: la OC del cliente y la ODV espejo

Si la ODV entra mal, todo lo que sigue está mal: cada parte se imputa contra una línea que no existe o que tiene otro precio, y el error aparece recién cuando la operadora rechaza la factura. Es un caso de uso de primera clase, no un trámite de carga.

Un repositorio tipo Drive sirve para guardar el PDF original, y conviene tenerlo. Lo que no sirve es como fuente de datos: el sistema necesita las líneas estructuradas —número, descripción, unidad, cantidad, precio unitario, moneda, saldo— y eso hay que extraerlo de alguna manera.

| Vía de ingreso | Evaluación |
|---|---|
| Carga manual asistida | Camino de v1. Una OC marco se carga una vez y se usa durante meses. |
| Importación por planilla | La operadora casi siempre puede exportar el detalle a Excel o CSV. Importador con validación previa: barato y cubre la mayoría. |
| Carpeta vigilada (Drive) | El PDF cae, el sistema lo archiva y abre una tarea de carga. Automatiza el archivo, no la extracción. |
| Extracción con IA sobre el PDF | Genera un borrador que alguien revisa y confirma. Viable, pero exige siempre revisión humana: una línea leída mal es plata mal facturada. |
| Integración con el portal de la operadora | Lo correcto, y lo que no se consigue hasta tener un cliente que abra la puerta. |

### 6.1 La OC cambia, y los cambios son retroactivos

Las modificaciones son casi siempre retroactivas en la práctica: la operadora amplía el saldo en octubre para cubrir trabajo ejecutado en septiembre. Si el sistema pisa el valor anterior, se pierde justamente la evidencia de que el trabajo estaba fuera de saldo cuando se hizo, que es la discusión que después hay que dar.

La forma de modelarlo es **no editar nunca la línea**. La línea tiene versiones, cada una con su vigencia y su motivo, y el parte se ata a la versión vigente al momento de la firma. El parte queda congelado con el precio y las condiciones que tenía cuando el inspector firmó, aunque después la línea cambie tres veces.

| Tipo de cambio | Tratamiento |
|---|---|
| Ampliación de cantidad o monto | Lo más común. Suma saldo, no toca lo ya ejecutado. |
| Cambio de precio unitario | Por redeterminación o ajuste, con fecha de vigencia. Lo firmado antes queda al precio viejo. Fuente habitual de rechazo de facturas. |
| Alta de líneas nuevas | Servicio no previsto que se agrega al contrato. |
| Reducción o cierre de línea | Peligroso si ya hay partes que superan el nuevo saldo. El sistema avisa, no deja el número en rojo silencioso. |
| Cambio de descripción o centro de costo | Parece cosmético y no lo es: la imputación es lo que la operadora valida. |
| Anulación de la OC completa | Con partes vivos colgando. |

> **Dos reglas que se desprenden.** El saldo disponible no es un campo que se actualiza: es el resultado de sumar las versiones de la línea y restar lo ejecutado contra ella. Guardado como número editable, tarde o temprano se desincroniza y nadie sabe por qué.
>
> Y el sistema **debe permitir prestar el servicio sin saldo**, marcándolo como excepción visible: en la realidad el trabajo se hace igual y la ampliación llega después. Si se bloquea, el técnico hace el parte en papel y se pierde el dato. El indicador «trabajo ejecutado sin saldo disponible» es probablemente el más vendible del producto, porque es plata que hoy se pierde entera y que nadie está mirando.

Queda por confirmar un punto de modelo: muchas operadoras trabajan con **OC marco abiertas** contra las que se liberan pedidos. Eso implica dos niveles —contrato y liberación— y el parte cuelga del segundo. Vale la pena verificar cómo lo maneja Oldelval antes de fijar el modelo.

---

## 7. Base de hechos y trazabilidad

Nada se pisa: todo hecho queda registrado. Lo que hace falta es un **registro de hechos inmutable**, append-only, donde cada hecho se guarda con qué pasó, sobre qué entidad, cuándo pasó en la realidad, cuándo se registró, quién lo registró y con qué evidencia. Nada se actualiza ni se borra: se agrega un hecho nuevo que corrige o revierte al anterior. El estado actual —saldo de la línea, estado del parte, estado del certificado— es una proyección calculada a partir de esos hechos, recalculable desde cero.

Eso da trazabilidad total, reconstrucción del estado a cualquier fecha pasada y defensa probatoria frente a la operadora. Y se hace con Postgres, sin nada exótico.

**Bitemporalidad.** Hay que guardar siempre las dos fechas, la del hecho y la del registro. El trabajo se ejecutó el 3, se sincronizó el 7, la ampliación se firmó el 20 con vigencia desde el 1. Sin eso no se puede responder «¿había saldo el día que se hizo el trabajo?», que es exactamente la pregunta que se discute.

**Qué no hacer en v1.** Una ontología formal —RDF, triple store, grafo semántico— resuelve un problema distinto: integrar vocabularios heterogéneos entre organizaciones que no se pusieron de acuerdo. Acá el problema es el opuesto: un dominio acotado y bien definido, donde el modelo relacional con eventos da más garantías —transaccionalidad, integridad referencial— y muchísimo menos costo de mantenimiento. Si más adelante hace falta exponer el modelo semánticamente, se hace encima sin rehacer nada.

**Qué sí tomar del enfoque ontológico.** La disciplina de nombrar bien las entidades y los eventos, y usar ese mismo vocabulario en la interfaz, en el código y frente al cliente. Que «parte» y «certificado» signifiquen cada uno una sola cosa en todo el sistema, y que no se confundan entre sí ni con «conformidad» o «habilita». Ese lenguaje ubicuo es la mitad del valor del enfoque, y es gratis.

---

## 8. Captura en campo

La idea central es la correcta y es lo que hace que el producto valga: el técnico no transcribe nada, elige una o varias líneas de ODV, edita las cantidades ejecutadas y el resto del parte se completa solo. Eso baja el tiempo de carga a minutos y elimina la fuente principal de error de imputación.

| Pieza | Definición |
|---|---|
| OCR de la OC con revisión en segundo plano | El agente propone y una persona confirma. Sobre un documento que llega una vez por contrato, es razonable. Valor adicional: comparar el PDF contra lo cargado y avisar diferencias — así se detectan ampliaciones que nadie comunicó. |
| Selección de línea/s en el celular | Lista descargada localmente antes de salir a campo. Mostrar el saldo disponible al lado de cada línea, para que el técnico vea antes de trabajar que está por consumir contra una línea agotada. Puede seleccionar varias líneas en un mismo parte. |
| Edición de cantidades ejecutadas | Sobre la línea seleccionada, el técnico carga lo que efectivamente hizo. Es el dato que después se cruza contra el certificado. |
| Autocompletado de fecha, hora y ubicación | Del dispositivo, con geolocalización en tiempo real. Guardar además la hora del servidor al sincronizar, y marcar si el GPS estaba desactivado o la ubicación es simulada. No por desconfianza: si alguna vez se discute un parte, el que tiene los dos relojes gana. |
| Foto y adjuntos | El técnico puede tomar foto en el momento y adjuntarla al parte, además de mediciones y ATS. |
| Identidad del técnico | De la sesión autenticada, nunca de los datos del teléfono. Es la diferencia entre un dato declarado y uno probado, y el celular puede ser compartido por la cuadrilla. |
| Marca de inicio y fin de trabajo | El técnico marca cuándo arranca y cuándo termina. Esos dos sellos alimentan el Gantt de estimado vs. real del tablero de supervisión. |
| Formulario del parte / hoja de trabajo | Datos estándar internamente, plantilla de salida configurable por cliente. Cada operadora va a querer su formato; si el formulario es rígido, cada cliente nuevo es desarrollo. |
| Horas improductivas | Vía alternativa al parte de trabajo ejecutado, para cuando por causas ajenas no se puede prestar el servicio. El técnico elige una causal de una lista (a definir con el convenio de petroleros) y esa línea también se envía a firma del inspector, igual que un parte normal. |
| Identidad del inspector | Se autocompleta desde la ODV (que la toma de la OC), pero el técnico puede editarla si en el momento firma una persona distinta de la que figura en el documento. |

### 8.1 Firma del inspector sobre el parte

Lo que se va a implementar es firma manuscrita capturada en pantalla más metadatos: nombre, DNI, cargo, hora, ubicación y hash del parte firmado. En Argentina eso es **firma electrónica** según la Ley 25.506: válida como prueba, pero con la carga de la prueba del lado de quien la invoca si el firmante la desconoce. La **firma digital** con certificado de una autoridad certificante tiene presunción legal a favor, pero exige que el inspector tenga token o certificado, cosa que en un yacimiento no va a pasar.

En la práctica se refuerza la firma electrónica: hash del PDF del parte, sellado de tiempo, foto del firmante opcional, y sobre todo envío inmediato por mail al inspector con copia a su empresa. El acuse de recepción sin objeción dentro de X días es, comercialmente, tan fuerte como la firma.

> **Nota de posicionamiento.** No llamarlo «firma digital» en el material de venta. Llamarlo **parte con conformidad firmada y evidencia**, que es lo que es, y no expone a una discusión legal que no hace falta dar.

---

## 9. Revisión de la propuesta de arquitectura evaluada

Sobre la propuesta de cinco capas generada previamente con otra herramienta. Sirve como mapa de opciones tecnológicas, no como arquitectura de este producto.

### Aciertos

- Identificar el certificado/habilita como pieza pivote: sin él no hay factura.
- Partir el DSO en tramo operativo y tramo financiero. Es además buen argumento de venta: le muestra al cliente que la plata no se traba solo en cobranzas.
- El *offline-first* como requisito no negociable.

### Objeciones

| Objeción | Detalle |
|---|---|
| Grano equivocado en el modelo de estados | El estado está a nivel OC y debe estar a nivel línea. Un certificado cubre parcialmente varias líneas y una línea acumula muchos partes. Con estado único por OC no se puede representar «línea 3 ejecutada al 60%, línea 4 sin saldo». Todo el tablero se cae si el grano está mal elegido. |
| Falta el saldo contratado por línea | Es donde se pierde la plata. Trabajo ejecutado contra línea agotada: nunca va a haber certificado ni factura, y nadie se entera hasta el cierre. Es un control preventivo, no un dashboard de estados. |
| No hay caminos infelices | Todo el flujo modelado es feliz. Faltan certificado rechazado u observado, parte que no se firma, factura rechazada por imputación, ampliación de OC, anulación. Ahí vive el dolor del cliente. |
| El OCR del certificado es fundación y debería ser optimización | Es la pieza más cara y más frágil, puesta como central. Con operadoras que usan SAP o Ariba, el número de certificado suele venir por portal o cantado por el contract admin, no en un PDF prolijo por mail. Un campo donde alguien pega el número y sube el adjunto da el 90% del valor con el 5% del esfuerzo. |
| Contradice el alcance de v1 | El estado «Cobrado» y el DSO financiero requieren conciliación bancaria, explícitamente fuera de alcance. El producto ya se justifica mostrando trabajos sin parte firmado y partes sin certificado. |
| La economía del stack no cierra | Azure Functions + Document Intelligence + Blob + Power BI + iPaaS, con Flutter arriba: cinco proveedores y cinco costos fijos para un producto que debe dejar USD 1.000 por mes. Power BI además se licencia por usuario, lo que lo hace problemático de revender dentro de un SaaS. |
| Falta lo que sostiene la propuesta de valor | Multi-tenant, permisos acumulables y sobre todo el log inmutable. La arquitectura tiene que decir explícitamente que un parte firmado no se edita: se anula y se rehace, con todo registrado. |

> **Error de fondo.** La propuesta modela un flujo documental. Este producto es un control de consumo de contrato con evidencia firmada. La alternativa más barata y más fácil de cambiar es un backend monolítico sobre Postgres, con el tablero construido dentro de la misma aplicación y los archivos en object storage.

---

## 10. Decisiones tomadas y pendientes

### Tomadas

| Decisión | Fundamento |
|---|---|
| La empresa produce el parte; la operadora emite el certificado | Es el reparto real de roles. El sistema no debe dar a entender que la empresa certifica. |
| Alcance v1 hasta facturación, sin cobranzas ni banco | Recorte sostenido: el valor ya se demuestra con lo no firmado y lo no facturado. |
| Grano de estado a nivel línea de ODV, no a nivel OC | Es el único grano que soporta ejecuciones parciales y saldos. |
| Versionado de líneas; nada se pisa | Los cambios de OC son retroactivos y hay que poder reconstruir el pasado. |
| Registro de hechos append-only con bitemporalidad; sin ontología formal | Da trazabilidad total sobre Postgres, sin el costo de un stack semántico. |
| Inspector como participante externo, no como usuario | Ninguna operadora registra a sus inspectores en el sistema de un proveedor. |
| Parte firmado inmutable: anular y rehacer | Es la regla que sostiene todo el argumento probatorio. |
| Permisos acumulables, no un rol por usuario | En empresas chicas una persona junta supervisión, facturación y configuración. |
| Se permite prestar el servicio sin saldo, marcado como excepción | Si se bloquea, el técnico hace el parte en papel y se pierde el dato. |
| Firma electrónica reforzada, comunicada como parte con conformidad firmada | Evita una discusión legal innecesaria y describe con precisión lo que el sistema hace. |

### Pendientes

- Confirmar si las operadoras del caso trabajan con OC marco y liberaciones, y si el parte cuelga del segundo nivel. Verificar con el contacto en Oldelval.
- Definir si el subcontratista entra en la v1 o queda para una versión posterior, y en ese caso si genera el parte y obtiene la conformidad él mismo o lo hace la empresa con lo que él carga.
- Definir quién aprueba el cierre o la anulación de una ODV (hoy figura el administrador de la empresa, que es un perfil de configuración y no debería aprobar decisiones comerciales).
- Definir el perfil de Seguridad e higiene: perfil propio acotado a legajos, o permiso agregado a otro perfil.
- Definir qué tipos de servicio exigen aprobación interna del parte y en qué momento (antes o después de la conformidad del inspector).
- Relevar los formatos de parte exigidos por las principales operadoras, para dimensionar el motor de plantillas.
- Fijar el glosario definitivo del dominio y usarlo en interfaz, código y material comercial.
- Resolver el caso del certificado parcial: anular y partir en dos, versus registrar monto menor.
- Definir qué documentos habilitantes exige cada operadora por técnico y con qué anticipación se alerta el vencimiento (los carga Seguridad e higiene).
- Definir el listado de causales de horas improductivas, alineado al convenio de petroleros.
- Definir si el vencimiento del plazo del certificado dispara un reclamo automático a la operadora o solo una alerta interna.
- Diseñar la vista Gantt del tablero (por técnico, por ODV) como complemento del tablero de estados.

### Glosario en construcción

| Término | Significado único en el sistema |
|---|---|
| Orden de compra (OC) | Documento del cliente que habilita el servicio y contiene líneas con saldo. |
| ODV | Orden de venta interna que espeja la OC del cliente, línea por línea. |
| Línea de ODV | Unidad mínima contratada. Grano de todo el sistema. Tiene versiones. |
| Orden de trabajo | Tarea asignada a una cuadrilla, imputada contra una línea de ODV. |
| Parte / hoja de trabajo | Documento que genera el técnico en campo con las cantidades ejecutadas; se envía al inspector para firma electrónica. Es el documento de la empresa. |
| Inspector | Representante de la operadora que presta conformidad sobre el parte. En campo a veces se lo llama «certificador», pero no emite el certificado. |
| Conformidad | Firma del inspector sobre el parte. Es la manifestación de un tercero, no una aprobación interna ni un certificado. |
| Aprobación interna | Revisión opcional del parte por parte del supervisor. Es una decisión de la empresa. |
| Certificado / habilita (HES) | Documento que emite la operadora en su portal a partir del parte firmado; es el que habilita a facturar. Es el documento de la operadora. |
| Saldo disponible | Resultado de las versiones de la línea menos lo ejecutado. Nunca un campo editable. |
| Documento habilitante | Documento del legajo del técnico (matrícula, curso de seguridad, ART, etc.) con vencimiento propio, requisito de la operadora para poder asignarlo a una línea de ODV. |
| Horas improductivas | Registro alternativo al parte de trabajo ejecutado, para cuando por causas ajenas al técnico no se puede prestar el servicio; lleva causal y también va a firma del inspector. |

---

## 11. Estados y transiciones

Hay cuatro máquinas de estado distintas y el error más común es fusionarlas. Van separadas, con los puntos de acople explícitos.

### 11.1 Línea de ODV

Es la única que no representa un flujo sino una condición del contrato. El paso a *Agotada* o *Excedida* lo dispara el sistema al firmar un parte, no una persona; la vuelta a *Vigente* la dispara una nueva versión de la línea. Cerrar una línea con partes vivos debe pedir confirmación explícita, no bloquear.

| Estado | Significado | Sale hacia |
|---|---|---|
| Vigente | Con saldo disponible | Agotada, Excedida, Suspendida, Cerrada |
| Agotada | Saldo consumido al 100% | Vigente (por ampliación), Cerrada |
| Excedida | Ejecutado por encima del saldo | Vigente (ampliación), Cerrada |
| Suspendida | Bloqueada por decisión comercial | Vigente, Cerrada |
| Cerrada | No admite más consumo | terminal |

### 11.2 Orden de trabajo

| Estado | Transiciones | Quién |
|---|---|---|
| Planificada | → Asignada | SUP |
| Asignada | → En ejecución, → Cancelada, → Reasignada | SUP, TEC |
| En ejecución | → Ejecutada, → Suspendida | TEC |
| Suspendida | → En ejecución, → Cancelada | SUP |
| Ejecutada | → Cerrada (al generarse el parte) | automático |
| Cancelada | terminal | SUP |

*Ejecutada* no significa que el parte esté firmado. Una orden puede quedar ejecutada durante semanas sin que nadie genere el parte, y ese hueco es uno de los indicadores del tablero.

### 11.3 Parte / hoja de trabajo — el ciclo central

El ciclo tiene dos parámetros que se configuran por tipo de servicio:

- **Aprobación interna:** no existe (valor por defecto, que refleja la práctica actual), previa a la conformidad, o posterior a la conformidad.
- **Canal de conformidad:** en sitio (el inspector firma en el dispositivo del técnico), enlace por mail o enlace por WhatsApp. Los tres pueden convivir; se elige en cada parte.

La conformidad en sitio es la única que funciona sin señal. Los dos canales por enlace exigen que el parte esté sincronizado antes de enviarse. La aprobación previa también exige conectividad entre la generación del parte y la firma, así que en campo sin señal solo es viable la combinación sin aprobación o con aprobación posterior.

```
   Borrador
   editable, en el dispositivo o sincronizado
        |
        +------------------------------+
        | (con aprobación previa)      | (sin aprobación, o con aprobación posterior)
        v                              |
   Pendiente de aprobación <--> Devuelto a corrección
        |                              |
        v                              |
   Aprobado internamente               |
        |                              |
        +------------------------------+
        |
        +--> en sitio: el inspector firma en el dispositivo
        +--> por enlace: Enviado a conformidad (mail o WhatsApp)
        |          |
        |          +--> No conforme --> Devuelto a corrección
        v
   Firmado por el inspector             (inmutable desde acá)
        |
        +--> (con aprobación posterior) Pendiente de revisión --> Anulado (si hay error)
        |
        v
   Subido al portal de la operadora  -------->  Observado
   corre el reloj del certificado               rechazo u observación de la operadora
        |                                             |
        v                                             |
   Certificado recibido                               |
   habilitado para facturar                           |
        |                                             v
        v                                        Anulado
   Facturado  --------------------------------->  terminal, deja rastro
```

| Estado | Qué significa | Transiciones válidas |
|---|---|---|
| Borrador | Cargado en el dispositivo, sincronizado o no | → Pendiente de aprobación (aprobación previa), → Enviado a conformidad (enlace), → Firmado (en sitio). Único estado editable |
| Pendiente de aprobación | Solo con aprobación previa: espera al supervisor | → Aprobado internamente, → Devuelto a corrección |
| Devuelto a corrección | Con observaciones del supervisor o no conforme del inspector | → Borrador |
| Aprobado internamente | Solo con aprobación previa: listo para la conformidad | → Enviado a conformidad, → Firmado (en sitio), → Anulado |
| Enviado a conformidad | Enlace de un solo uso enviado al inspector por mail o WhatsApp | → Firmado, → Devuelto a corrección (no conforme), → Borrador (el enlace venció sin respuesta; se puede reenviar) |
| Firmado por el inspector | Conformidad del inspector capturada sobre el parte | → Pendiente de revisión (aprobación posterior), → Subido al portal. Inmutable desde acá |
| Pendiente de revisión | Solo con aprobación posterior: el supervisor revisa un parte ya firmado | → Subido al portal (revisado sin objeciones), → Anulado (se rehace y vuelve a firma) |
| Subido al portal | Se subió a la operadora; corre el reloj del certificado | → Certificado recibido, → Observado, → Vencido sin respuesta |
| Observado | Rechazo u observación de la operadora | → Anulado (y se rehace) |
| Vencido sin respuesta | Superó el plazo configurado sin certificado | → Certificado recibido (llegó tarde), → Observado |
| Certificado recibido | La operadora emitió el certificado; habilitado para facturar | → Facturado, → Anulado |
| Facturado | Vinculado a una factura emitida | → Anulado (solo con nota de crédito) |
| Anulado | Terminal. Deja rastro y referencia al reemplazo | — |

> **Dos reglas duras.** Desde *Firmado* en adelante nada se edita: el único camino es *Anulado* más un parte nuevo que lo referencia. Y *Anulado* nunca borra: es un hecho más en el registro.
>
> **Caso a decidir.** Si el certificado llega parcial —la operadora aprueba menos de lo que dice el parte— eso no es *Observado*. Es un parte que se anula y se parte en dos: uno por el monto aprobado y otro por la diferencia en disputa, que se reclama. Modelarlo como «certificado recibido con monto menor» hace perder el rastro del reclamo.

### 11.4 Factura

| Estado | Transiciones |
|---|---|
| Borrador | → Emitida, → Descartada |
| Emitida | → Presentada al cliente, → Anulada por NC |
| Presentada | → Aprobada, → Rechazada |
| Rechazada | → Anulada por NC (los partes vuelven a Certificado recibido) |
| Aprobada | → Cobrada (fuera de alcance v1) |
| Anulada por NC | terminal |

El control de aprobación de la factura electrónica cierra el ciclo. El rechazo de factura es la transición más valiosa del sistema, porque devuelve los partes a la cola en lugar de dejarlos perdidos.

### 11.5 Acoples entre máquinas

- Parte pasa a *Firmado* → se recalcula el saldo de la línea, que puede pasar a *Agotada* o *Excedida*.
- Parte pasa a *Firmado* con aprobación posterior configurada → genera tarea de revisión para el supervisor.
- Parte pasa a *Facturado* → la factura lo referencia; un parte no puede facturarse dos veces.
- Factura pasa a *Anulada por NC* → los partes vuelven a *Certificado recibido*.
- Orden de trabajo queda *Ejecutada* sin parte durante X días → alerta.

> **Los tres relojes a parametrizar por cliente:** ejecutado sin parte, firmado sin subir al portal, y subido sin certificado. Ahí es donde se congela la plata, y son exactamente las tres métricas del tramo operativo del DSO.

---

## 12. Autenticación, permisos y seguridad

### 12.1 Autenticación

Tres poblaciones con necesidades distintas, y conviene no darles el mismo mecanismo.

**Usuarios de oficina** (supervisión, administración, comercial): usuario y contraseña con segundo factor. Lo razonable es soportar además inicio de sesión con Google o Microsoft, porque casi todas estas empresas ya tienen uno de los dos y se evita la gestión de contraseñas. SSO empresarial (SAML/OIDC) es pedido de clientes grandes; dejarlo previsto pero no construirlo en v1.

**Técnicos de campo**: acá la fricción mata. Login inicial con credencial, y después sesión larga en el dispositivo con desbloqueo por PIN o biometría. Nadie va a tipear una contraseña compleja con guantes. El token del dispositivo debe poder revocarse desde el panel: si el celular se pierde o el técnico renuncia, el supervisor lo desactiva y el dispositivo se borra en la próxima conexión.

**Inspector**: no autentica. Firma el parte sobre la sesión del técnico, o desde un link de un solo uso con vencimiento corto enviado por mail o WhatsApp. Ese link es un token firmado, de uso único, atado a un parte específico y a un destinatario, sin capacidad de navegar a ningún otro dato.

### 12.2 Autorización

El modelo es permisos acumulables, no un rol por usuario. Cinco perfiles base más dos de solo lectura, y una persona puede tener varios.

| Perfil | Permisos que agrupa |
|---|---|
| Campo | Ver órdenes asignadas y el propio legajo, cargar avance, generar parte, enviar a conformidad, capturar la conformidad en sitio |
| Supervisión | Todo lo de campo, más crear y asignar órdenes de trabajo, aprobar internamente (si está habilitado), devolver y anular |
| Administración / Facturación | Subir al portal, reclamar y registrar certificados, facturación, exportación de respaldos |
| Comercial | ODV y líneas, precios, tablero completo |
| Configuración | Usuarios, permisos, maestros, plantillas, integraciones |
| Lectura auditoría | Evidencia y log, sin precios |
| Lectura gerencial | Tablero e indicadores, sin edición |

Tres dimensiones adicionales de alcance, que son lo que realmente diferencia a un usuario de otro:

- **Por base o zona** — el jefe de Añelo no ve lo de Rincón.
- **Por cliente u operadora.**
- **Por sensibilidad del dato** — el técnico no debería ver precios ni saldos en pesos; le alcanza con ver si hay saldo o no, en forma de semáforo. Esto no es paranoia: los técnicos rotan entre empresas competidoras.

El subcontratista se resuelve con el perfil de campo más un alcance restringido a sus propias órdenes y sin visibilidad de precios. Ningún rol nuevo.

Seguridad e higiene necesita cargar documentos en los legajos, cosa que ninguno de los siete perfiles cubre. Queda pendiente definir si tiene perfil propio o un permiso agregado a otro.

**Autorización efectiva.** Tener el perfil no alcanza. Cada acción se autoriza si se cumplen cuatro cosas: **permiso + alcance + estado + condiciones**.

- El **permiso** dice qué acción puede hacer el usuario (por ejemplo, anular un parte).
- El **alcance** dice sobre qué objetos: tenant, base, operadora, sensibilidad. Es estable y se resuelve con RLS y filtros.
- El **estado** dice si el objeto admite esa acción en este momento, según la máquina de estados de la sección 11. Es dinámico y se valida al ejecutar. Un supervisor con permiso de anular puede anular un parte firmado, pero nadie puede editarlo.
- Las **condiciones** son reglas adicionales, como la de segregación de funciones.

Alcance y estado no se mezclan: uno filtra qué objetos ve el usuario, el otro valida qué puede hacer con ellos en ese momento. La autoridad final es siempre el backend; que la interfaz oculte un botón no es seguridad.

**Segregación de funciones.** Cuando la aprobación interna está habilitada, quien generó el parte no debería aprobarlo. En empresas chicas donde no hay otra persona, se permite como **excepción visible y auditada**, con el mismo criterio que trabajar sin saldo: el sistema no bloquea, pero lo registra y lo muestra.

### 12.3 Seguridad

**Aislamiento multi-tenant.** Es la decisión más cara de revertir. Con Postgres, la vía sólida es *row-level security* con el identificador de tenant forzado a nivel de sesión de base, no filtrado en el código de la aplicación. Filtrar en el código funciona hasta que alguien olvida un `where` en una consulta nueva, y ese día un cliente ve datos de otro. Con RLS el olvido devuelve cero filas en lugar de datos ajenos.

**El dispositivo en campo.** Es la superficie de ataque más expuesta. Base local cifrada, sin datos de otros clientes en el dispositivo, expiración de la sesión si no sincroniza en X días, y borrado remoto. Descargar solo las órdenes asignadas a esa persona, no todo el catálogo.

**Integridad de la evidencia.** Los archivos van a object storage con acceso por URL firmada de vida corta, nunca públicos. Cada parte firmado guarda su hash; si alguien reemplaza el archivo, el hash no coincide y el sistema lo detecta. El log de auditoría es append-only, sin permisos de update ni delete sobre esa tabla ni siquiera para el rol de aplicación.

**El administrador de plataforma.** Esto es lo que más suele descuidarse y en este producto es crítico: el acceso propio de soporte tiene que ser de solo lectura por defecto, con impersonación limitada en tiempo, registrada y visible para el cliente. Si el proveedor puede editar silenciosamente un parte firmado, el argumento probatorio no resiste una pregunta de un abogado.

**Datos personales.** El parte guarda nombre, DNI, firma y ubicación de personas. Eso cae bajo la Ley 25.326: base de datos registrable, finalidad declarada, y política de retención. La retención larga que se necesita por prueba conviene documentarla como fundamento legítimo, no dejarla implícita.

### 12.4 Qué queda fuera de la v1

Sin culpa: SSO empresarial, gestión de dispositivos móviles (MDM), y cualquier certificación formal tipo ISO 27001.

No se puede dejar afuera: el aislamiento por RLS y el log inmutable. Ambos son casi imposibles de retrofitear sin reescribir.

---

## 13. Flujos de trabajo

Ya no es "qué hace cada actor" sino en qué orden pasan las cosas, qué dispara cada paso y adónde va si algo sale mal.

### 13.1 Alta y versionado de ODV

| Paso | Dispara | Actor/sistema | Resultado |
|---|---|---|---|
| 1 | Llega la OC (PDF, planilla o portal) | COM / ADE | Archivo en repositorio |
| 2 | Extracción de líneas (manual, planilla o IA asistida) | COM / ADE | Borrador de líneas |
| 3 | Validación y confirmación de líneas | COM | Línea de ODV creada, estado *Vigente* |
| 4 | *(rama)* Llega una modificación de una OC existente | Operadora | Nueva versión de la línea, con vigencia y motivo |
| 5 | Recalcular saldo por línea | — (automático) | Saldo actualizado, puede cambiar el estado de la línea |

Este flujo no termina nunca: el paso 4 se repite durante toda la vida del contrato. Por eso la OC es un flujo abierto, no un alta única.

### 13.2 Ejecución en campo

| Paso | Dispara | Actor | Resultado |
|---|---|---|---|
| 1 | Orden de trabajo asignada (previa validación de documentos habilitantes) | SUP | Orden en estado *Asignada* |
| 2 | Técnico descarga sus órdenes, las líneas de ODV vigentes y su legajo | TEC (antes de salir a campo) | Datos locales en el dispositivo |
| 3 | Técnico marca inicio, selecciona línea/s, edita cantidades, carga avance y adjunta evidencia y fotos | TEC / SUB | Orden en *En ejecución* |
| 4 | Técnico marca fin de tarea | TEC | Orden en *Ejecutada* |
| 5 | Sincroniza cuando hay señal (automático) | TEC | Datos en servidor |
| 6 | *(rama)* Si no se genera el parte en X días | Reloj | Alerta a SUP y COM |
| 3b | *(rama)* No puede prestar el servicio por causa ajena | TEC | Registra horas improductivas con causal en lugar de avance normal; esa línea también se envía a firma del inspector |

El inicio y el fin de tarea (pasos 3 y 4) son la base del Gantt de estimado vs. real. El punto 6 conecta este flujo con el tablero: es la primera de las tres métricas del tramo operativo.

### 13.3 Parte / hoja de trabajo → certificado (el flujo central)

Los pasos 2 y 4 dependen de la configuración de aprobación interna del tipo de servicio (ver 11.3). Por defecto no hay aprobación, y el flujo va de 1 a 3 y de 3 a 5.

| Paso | Dispara | Actor | Resultado |
|---|---|---|---|
| 1 | Se genera el parte desde la orden ejecutada | TEC / SUP | Parte en *Borrador* |
| 2 | *(solo con aprobación previa)* El supervisor revisa | SUP (distinto de quien generó el parte, salvo excepción registrada) | *Aprobado internamente*, o *Devuelto a corrección* (vuelve a 1) |
| 3a | Conformidad en sitio: el inspector firma en el dispositivo del técnico; admite offline | TEC E · INS C | *Firmado*, inmutable desde acá |
| 3b | Conformidad por enlace: se envía un enlace de un solo uso por mail o WhatsApp al contacto que figura en la ODV | TEC / SUP E · INS C | *Enviado a conformidad* → *Firmado*, o *Devuelto a corrección* si el inspector no presta conformidad (vuelve a 1) |
| 4 | *(solo con aprobación posterior)* Sincroniza y el supervisor revisa el parte firmado | SUP | Sigue a 5, o *Anulado* con parte nuevo (vuelve a 1) |
| 5 | Administración sube el parte firmado al portal de la operadora | FAC · POR | *Subido al portal*, arranca el reloj del certificado (plazo que surge de la OC/ODV) |
| 6 | Administración envía el parte firmado al contract administrator y le reclama el certificado / habilita | FAC | Reclamo registrado |
| 7a | La operadora emite el certificado | Operadora / FAC | *Certificado recibido* → se cruza contra el parte |
| 7b | *(rama)* Observación o rechazo | Operadora / FAC | *Observado* → *Anulado* → vuelve al paso 1 con nuevo parte |
| 7c | *(rama)* Vence el plazo sin certificado | REL → FAC | *Vencido sin respuesta* → dispara reclamo/alerta |
| 7d | *(rama)* Certificado parcial (no coincide con el parte) | FAC | El parte se anula y se parte en dos: uno por el monto aprobado (a facturar), otro por la diferencia, que se reclama (vuelve a 7b para ese remanente) |

Los pasos 5 a 7 son el corazón del producto: ahí se sube al portal, se reclama el certificado, corre el plazo de entrega y se cruza el certificado recibido contra el parte para decidir si se factura o se reclama la diferencia.

> **Pendiente de definir.** Al vencer el plazo sin certificado (7c), ¿el sistema dispara un reclamo automático hacia la operadora (mail o portal) o solo una alerta interna a Administración/Comercial para que una persona lo gestione? Impacta si se necesita integración de envío saliente o alcanza con la alerta.

### 13.4 Facturación

| Paso | Dispara | Actor | Resultado |
|---|---|---|---|
| 1 | Parte en *Certificado recibido* y cruzado OK aparece en la cola | — (automático) | Visible para FAC |
| 2 | Se verifica saldo | FAC (la plataforma calcula) | Bloquea o marca excepción |
| 3 | Se emite la factura, vinculada a uno o más certificados | FAC · ARCA | Partes en *Facturado* |
| 4 | Se presenta al cliente | FAC | Factura *Presentada* |
| 5 | Se controla la aprobación de la factura electrónica | FAC | Factura *Aprobada* o *Rechazada* |
| 5a | Aprobada | Operadora | Fin del alcance v1 |
| 5b | *(rama)* Rechazada | Operadora | Los partes vuelven a *Certificado recibido*; factura *Anulada por NC* |

### 13.5 Flujo transversal — alertas y tablero

No es un flujo lineal sino un observador continuo sobre los otros flujos:

- Ejecutado sin parte (13.2 → alerta)
- Firmado sin subir al portal (13.3, entre pasos 3 y 5)
- Subido sin certificado (13.3, entre pasos 5 y 7)
- Saldo por agotarse (13.1, paso 5)
- Documento habilitante próximo a vencer (legajos, a cargo de Seguridad e higiene)

Estas cinco alertas son, en términos de arquitectura, el mismo mecanismo aplicado a distintos relojes: un job que compara la fecha del último hecho contra un umbral configurable por cliente.

---

## 14. Modelo de datos

Dos capas: una tabla de hechos que es la fuente de verdad, y las entidades como proyecciones calculadas sobre esos hechos (ver sección 7). Si se modelan solo las entidades con campos mutables, se pierde exactamente la trazabilidad que es la base del producto.

### 14.1 Capa 1 — el registro de hechos

Una sola tabla append-only que sostiene todo el sistema.

| Campo | Qué guarda |
|---|---|
| `id_hecho` | identificador único |
| `id_tenant` | aislamiento multi-tenant, obligatorio en cada fila |
| `tipo_hecho` | ej. `linea_odv_creada`, `parte_firmado`, `parte_subido_portal`, `certificado_recibido`, `factura_emitida`, `factura_aprobada` |
| `id_entidad` | a qué entidad de negocio se refiere |
| `tipo_entidad` | `linea_odv`, `orden_trabajo`, `parte`, `certificado`, `factura` |
| `fecha_hecho` | cuándo pasó en la realidad |
| `fecha_registro` | cuándo se guardó en el sistema — la bitemporalidad de la sección 7 |
| `actor` | quién lo generó (usuario, o `sistema` para lo automático) |
| `payload` | JSON con los datos específicos de ese tipo de hecho |
| `hecho_anterior_id` | si corrige o revierte un hecho previo, lo referencia — nunca se borra nada |
| `hash_evidencia` | si el hecho tiene un archivo asociado (parte firmado, PDF de OC, certificado) |

Cada fila es inmutable. Un parte que se anula no se borra ni se actualiza: se agrega un hecho `parte_anulado` que referencia al original, y otro `parte_creado` para el reemplazo.

### 14.2 Capa 2 — entidades (proyecciones)

Tablas normales, pero conceptualmente son una "foto" recalculable a partir de la capa 1. En la práctica se actualizan al vuelo cuando llega un hecho nuevo, para no recalcular todo en cada lectura — pero el registro de hechos manda si alguna vez discrepan.

- **`tenant`** — la empresa cliente. Todo cuelga de acá para el aislamiento por RLS.
- **`orden_compra`** — cabecera: operadora, número, tipo (marco o directa), estado. La ODV espeja esta OC.
- **`linea_odv`** — pertenece a una ODV/OC. Tiene **versiones** (tabla separada `linea_odv_version`: precio, cantidad, vigencia desde/hasta, motivo del cambio). El saldo disponible no es un campo, es una vista calculada: suma de versiones vigentes menos suma de lo ejecutado y firmado contra esa línea.
- **`orden_trabajo`** — cuelga de una línea de ODV, tiene cuadrilla asignada, estado, marcas de inicio/fin, y las evidencias que se van adjuntando (avance, materiales, ATS, fotos).
- **`parte`** — cuelga de una orden de trabajo y de la versión de línea vigente al momento de la firma (lo ata a esa versión específica, no a la línea en general). Campos: estado, cantidades ejecutadas, inspector firmante (nombre/DNI/empresa, sin ser un usuario del sistema), firma, geolocalización, hash del PDF, referencia al parte que anula o al que reemplaza.
- **`certificado`** — documento emitido por la operadora, vinculado a uno o más partes. Campos: número, monto aprobado, fecha, estado del cruce contra el parte (coincide / parcial / observado), hash del archivo recibido.
- **`factura`** — vinculada a uno o más certificados a través de una tabla puente `factura_certificado`, porque una factura puede agrupar varios certificados y (en el caso de certificado parcial) un parte puede terminar total o parcialmente facturado.
- **`usuario`** y **`permiso`** — usuario con permisos acumulables (tabla puente usuario-perfil), más las tres dimensiones de alcance de la sección 12: zona, cliente/operadora, nivel de sensibilidad de dato.
- **`documento_habilitante`** — cuelga del técnico/subcontratista: tipo, número, vigencia desde/hasta, archivo. Alimenta la validación al asignar.

### 14.3 Relaciones clave

```
tenant 1──N orden_compra 1──N linea_odv 1──N linea_odv_version
                                  │
                                  └──N orden_trabajo 1──N parte 1──N certificado
                                                                        │
                                                                        └──N (vía puente) factura
```

### 14.4 Tres decisiones de modelado

**El saldo nunca es una columna editable.** Es una vista o una columna calculada por trigger a partir de `linea_odv_version` y lo ejecutado y firmado. Si se hace columna editable, en algún punto un `UPDATE` manual la desincroniza del historial de hechos y se pierde la garantía central del producto.

**El parte referencia una versión de línea, no la línea.** Así queda congelado con el precio vigente al momento de la firma (sección 6.1), sin importar cuántas versiones tenga la línea después.

**RLS a nivel de `id_tenant` en cada tabla**, forzado por política de Postgres, no por `WHERE` en el código de aplicación (sección 12.3).

Con esto el modelo queda en condiciones de pasar a Claude Code: entidades, relaciones, el registro de hechos como fuente de verdad, y las reglas de negocio no negociables — inmutabilidad post-firma, saldo calculado, versionado de líneas, RLS.
