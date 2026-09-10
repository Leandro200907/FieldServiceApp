# Trazabilidad de certificación de servicios de campo

**Análisis de dominio, actores, casos de uso y requisitos**
Documento de trabajo — septiembre de 2026

---

## 1. De qué se trata el proyecto

Producto para dar trazabilidad para empresas de servicios de campo en oil & gas: se genera un backlog de ODV linea x linea ( previo control vs OC cliente) , y sigue cada línea a lo largo de todo sus estados —asignaciones de trabajo, ejecucion del mismo,envio del Parte de Trabajo al cliente, seguimiento del certificado, saldo consumido contra lo contratado y factura emitida— mostrando en un tablero el estado de cada una y dónde se traba la plata. Resuelve un problema que en la práctica es de caja: servicios prestados que nunca se certifican, certificados que quedan sin firmar en una camioneta, líneas de orden de compra que se agotan sin que nadie avise, y facturas emitidas contra certificaciones mal imputadas que el cliente rechaza.Contempla control de documentacion necesaria para prestar servicio de cada Field Service, Gantt de control de tiempos de Field Service real vs estimado con causas. 

---

## 2. Actores

### 2.1 Del lado de la empresa de servicios (cliente que paga)

- **Técnico / cuadrilla de campo.** Ve las órdenes de trabajo del día, registra qué hizo contra qué línea de ODV en el celular, adjunta evidencia y captura la firma del certificador en el yacimiento. Trabaja offline. 
- **Supervisor / jefe de base.** Revisa los legajos  de cada Field Service documentos habilitantes (matrícula, curso de seguridad, ART, apto médico, etc.) con fecha de vencimiento.Asigna trabajos, revisa y aprueba antes de que salga al cliente, corrige imputaciones y persigue lo que quedó sin firmar. Da seguimiento al Gantt.
- **Seguridad e higiene / calidad.** Permisos de trabajo, ATS, checklist previo. En oil & gas no es opcional y a veces bloquea la certificación.
- **Administración / facturación.** Revise el Parte u hoja de Trabajo firmado por Inspector o Certificador, sube el mismo a portal Operadora.Recibe el  certificado, verifica contra Parte u Hoja de Trabajo, emite la factura y la carga en el portal del cliente. Necesita ver el vínculo factura ↔ certificados ↔ líneas de OC para defender un rechazo.
- **Comercial.** Carga la ODV espejo de OC del cliente con sus líneas y saldos, monitorea consumo por contrato y mira los indicadores del tablero.
- **Administrador de la empresa.** Usuarios, roles y permisos, datos maestros, plantillas de certificado, reglas de aprobación e integraciones. Rol de configuración, no de operación diaria.
- **Subcontratista.** Es el técnico con alcance recortado: mismos casos de uso, visibilidad limitada a sus propias órdenes de trabajo, sin acceso a precios.

### 2.2 Del lado de la operadora (no pagan, pero sin ellos no cierra el circuito)

- **Certificador.** Firma la conformidad en campo. Es un actor **externo, participante y no usuario**: participa en un caso de uso, pero no tiene cuenta, no inicia nada y no consume licencia.
- **Contract administrator / comprador.** Emite y amplía la OC.Revisa Parte de Servicio firmado por Certificador,emite Habilitay envia a Cliente. No usa el sistema, pero define la estructura de líneas que hay que replicar fielmente.
- **Cuentas a pagar.** Recibe la factura y los respaldos. El producto gana o pierde ahí.

### 2.3 Otros

- **Administrador de la plataforma** (el operador del SaaS): tenants, planes, salud del sistema, soporte con acceso auditado, migraciones, versiones. No debe poder tocar datos de negocio sin dejar rastro.
- **Auditor externo / contador.** Solo lectura sobre la evidencia. Define requisitos de retención y exportación.
- **Sistemas no humanos:** el ERP del proveedor, el portal de la operadora (Ariba, Coupa o propio), ARCA para el CAE, y el reloj —los disparadores por vencimiento inician casos de uso propios.Agente para verificar excactitud entre ODV y OC, entre Habilita y Parte , Habilita y Factura.

> **Sobre el certificador.** Modelarlo como usuario sería un error caro: alta de credenciales, recuperación de contraseña y soporte a gente que no paga y que rota permanentemente; ninguna operadora va a registrar a sus inspectores en el sistema de un proveedor; y aparecen cuentas externas dentro del tenant del cliente. Lo que sí necesita es **identidad registrada aunque no autenticada**: nombre, DNI o legajo, empresa, cargo, y la constancia de cómo firmó. Es un dato del hecho, no un perfil.

---

## 3. Matriz de actores y casos de uso

Referencias: **E** ejecuta · **A** aprueba · **L** solo lectura.
TEC técnico · SUP supervisor · FAC administración y facturación · COM comercial y gerencia · ADE administrador de la empresa · SUB subcontratista · CER certificador · AUD auditor · SIS sistema.

### 3.1 Contrato , órdenes de compra espejando ODV

| Caso de uso | Actores |
|---|---|
| Alta de ODV con líneas, precios y saldos | COM E · ADE E · FAC L |
| Ampliar o modificar líneas de ODV | COM E · SUP L |
| Consultar saldo disponible por línea | todos L |
| Alerta de saldo por agotarse | SIS E → COM, SUP |
| Cerrar o anular ODV | COM E · ADE A |

### 3.2 Asignacion , ejecución y Parte u Hoja de Trabajo

| Caso de uso | Actores |
|---|---|
| Crear orden de trabajo contra línea de ODV  | SUP E |
| Asignar cuadrilla o subcontratista          | SUP E |
| Registrar avance, horas y equipos en campo  | TEC E · SUB E |
| Adjuntar evidencia (fotos, mediciones, ATS) | TEC E · SUB E |
| Sincronizar trabajo cargado offline | SIS E |
| Genera Parte u Hoja de Trabajo y envia a firma electronica | TEC E · SUB E |
| Recibe el Parte u Hoja de Trabajo firmada | SUP L  · FAC L  |
| Validar vigencia de documentos habilitantes del técnico antes de asignar | SIS E · SUP L |
| Alerta por documento habilitante vencido en la asignación | SIS E → SUP E |
| Registrar horas improductivas con causal, cuando no se puede prestar el servicio por causas ajenas | TEC E · SUB E |
| Editar la identidad del certificador si en el momento firma alguien distinto del que figura en la ODV | TEC E |

### 3.3 Certificación o Habilita

| Caso de uso | Actores |
|---|---|
| Seguimiento del estado del certificado  | FAC E · SUP E |
| Recibe certificado de la operadora y control vs Parte | SIS E · FAC E |
| Registrar número de Certificado recibido | FAC E · SUP E |
| Registrar rechazo u observaciones del Certificado | FAC E · SUP E |

### 3.4 Facturación

| Caso de uso | Actores |
|---|---|
| Ver certificados con Certificado listos para facturar | FAC E |
| Verificar saldo antes de emitir | SIS E · FAC E |
| Emitir factura vinculada a certificados | FAC E |
| Registrar rechazo de factura y recircular | FAC E · COM L |
| Exportar respaldo completo de un caso | FAC E · AUD L |

### 3.5 Control y administración

| Caso de uso | Actores |
|---|---|
| Tablero de estados por línea y cuellos de botella | COM E · SUP L · FAC L |
| Vista Gantt de ODV asignadas por técnico, tiempo estimado vs. real (a partir del inicio y fin de tarea marcados en campo) | SUP L · COM L |
| Consultar log de auditoría | ADE L · AUD L · COM L |
| Alta y baja de usuarios, asignación de permisos | ADE E |
| Configurar maestros, plantillas y reglas de aprobación | ADE E |
| Configurar integración con ERP | ADE E |

> **Tres conclusiones que salen de la matriz.**
> 1. El certificador aparece una sola vez y siempre como aprobador, nunca como ejecutor: no necesita cuenta.
> 2. Ningún actor operativo puede editar un certificado firmado; el único camino es anular y rehacer con aprobación. Esa regla sostiene todo el argumento probatorio.
> 3. De acá salen cinco perfiles base —campo, supervisión, administración, comercial y configuración— más dos accesos de solo lectura. Los permisos deben ser **acumulables**: en empresas chicas el jefe de base también factura y administra usuarios.

---

## 4. Requisitos no funcionales

**Conectividad y datos.** Operación offline completa con sincronización diferida y resolución de conflictos. Tolerancia a días sin señal. Compresión de fotos: la subida se hace con datos móviles caros y lentos. La lista de líneas de OC debe descargarse antes de salir a campo, no consultarse en el momento.

**Integridad probatoria.** Log inmutable con quién, qué y cuándo. Certificado firmado no editable. Sellado de tiempo y geolocalización del momento de la firma. Retención de documentos por el plazo fiscal y contractual (mínimo diez años en Argentina). Exportación completa de la evidencia de un caso.

**Seguridad.** Multi-tenant con aislamiento estricto entre empresas. Permisos acumulables por rol. Cifrado en tránsito y en reposo. Manejo del dispositivo perdido o robado, que en campo ocurre.

**Usabilidad en contexto real.** Uso con guantes, a pleno sol, con la tablet mojada. Carga de un certificado en menos de dos o tres minutos. Pantallas legibles para gente que no es de sistemas. Si al técnico le cuesta, no lo usa y el producto muere ahí.

**Operación.** Disponibilidad razonable —esto no es control de proceso— pero con backup y restauración probados. Alta de un tenant nuevo sin intervención de desarrollo. Migración de datos históricos en el onboarding.

**Documentación del personal.** Cada técnico y subcontratista tiene un legajo de documentos habilitantes (matrícula, curso de seguridad, ART, apto médico, etc.) con fecha de vencimiento propia. El sistema debe impedir o alertar la asignación a una línea de ODV si algún documento requerido por la operadora está vencido al momento de asignar, no recién cuando el trabajo ya se ejecutó.

**Cumplimiento y localización.** Ley 25.326 de protección de datos personales. Requisitos de facturación electrónica de ARCA si se emite desde el sistema. Ley 25.506, que define hasta dónde el certificado firmado en tablet es oponible. Castellano rioplatense, pesos y dólares, huso horario argentino.

---

## 5. El arranque del circuito: la orden de compra

Si la OC entra mal, todo lo que sigue está mal: cada certificado se imputa contra una línea que no existe o que tiene otro precio, y el error aparece recién cuando la operadora rechaza la factura. Es un caso de uso de primera clase, no un trámite de carga.

Un repositorio tipo Drive sirve para guardar el PDF original, y conviene tenerlo. Lo que no sirve es como fuente de datos: el sistema necesita las líneas estructuradas —número, descripción, unidad, cantidad, precio unitario, moneda, saldo— y eso hay que extraerlo de alguna manera.

| Vía de ingreso | Evaluación |
|---|---|
| Carga manual asistida | Camino de v1. Una OC marco se carga una vez y se usa durante meses. |
| Importación por planilla | La operadora casi siempre puede exportar el detalle a Excel o CSV. Importador con validación previa: barato y cubre la mayoría. |
| Carpeta vigilada (Drive) | El PDF cae, el sistema lo archiva y abre una tarea de carga. Automatiza el archivo, no la extracción. |
| Extracción con IA sobre el PDF | Genera un borrador que alguien revisa y confirma. Viable, pero exige siempre revisión humana: una línea leída mal es plata mal facturada. |
| Integración con el portal de la operadora | Lo correcto, y lo que no se consigue hasta tener un cliente que abra la puerta. |

### 5.1 La OC cambia, y los cambios son retroactivos

Las modificaciones son casi siempre retroactivas en la práctica: la operadora amplía el saldo en octubre para cubrir trabajo ejecutado en septiembre. Si el sistema pisa el valor anterior, se pierde justamente la evidencia de que el trabajo estaba fuera de saldo cuando se hizo, que es la discusión que después hay que dar.

La forma de modelarlo es **no editar nunca la línea**. La línea tiene versiones, cada una con su vigencia y su motivo, y el certificado se ata a la versión vigente al momento de la firma. El certificado queda congelado con el precio y las condiciones que tenía cuando el certificador firmó, aunque después la línea cambie tres veces.

| Tipo de cambio | Tratamiento |
|---|---|
| Ampliación de cantidad o monto | Lo más común. Suma saldo, no toca lo ya certificado. |
| Cambio de precio unitario | Por redeterminación o ajuste, con fecha de vigencia. Lo certificado antes queda al precio viejo. Fuente habitual de rechazo de facturas. |
| Alta de líneas nuevas | Servicio no previsto que se agrega al contrato. |
| Reducción o cierre de línea | Peligroso si ya hay certificaciones que superan el nuevo saldo. El sistema avisa, no deja el número en rojo silencioso. |
| Cambio de descripción o centro de costo | Parece cosmético y no lo es: la imputación es lo que la operadora valida. |
| Anulación de la OC completa | Con certificados vivos colgando. |

> **Dos reglas que se desprenden.** El saldo disponible no es un campo que se actualiza: es el resultado de sumar las versiones de la línea y restar lo certificado. Guardado como número editable, tarde o temprano se desincroniza y nadie sabe por qué.
>
> Y el sistema **debe permitir certificar sin saldo**, marcándolo como excepción visible: en la realidad el trabajo se hace igual y la ampliación llega después. Si se bloquea, el técnico certifica en papel y se pierde el dato. El indicador «trabajo ejecutado sin saldo disponible» es probablemente el más vendible del producto, porque es plata que hoy se pierde entera y que nadie está mirando.

Queda por confirmar un punto de modelo: muchas operadoras trabajan con **OC marco abiertas** contra las que se liberan pedidos. Eso implica dos niveles —contrato y liberación— y la certificación cuelga del segundo. Vale la pena verificar cómo lo maneja Oldelval antes de fijar el modelo.

---

## 6. Base de hechos y trazabilidad

Nada se pisa: todo hecho queda registrado. Lo que hace falta es un **registro de hechos inmutable**, append-only, donde cada hecho se guarda con qué pasó, sobre qué entidad, cuándo pasó en la realidad, cuándo se registró, quién lo registró y con qué evidencia. Nada se actualiza ni se borra: se agrega un hecho nuevo que corrige o revierte al anterior. El estado actual —saldo de la línea, estado del certificado— es una proyección calculada a partir de esos hechos, recalculable desde cero.

Eso da trazabilidad total, reconstrucción del estado a cualquier fecha pasada y defensa probatoria frente a la operadora. Y se hace con Postgres, sin nada exótico.

**Bitemporalidad.** Hay que guardar siempre las dos fechas, la del hecho y la del registro. El trabajo se ejecutó el 3, se sincronizó el 7, la ampliación se firmó el 20 con vigencia desde el 1. Sin eso no se puede responder «¿había saldo el día que se hizo el trabajo?», que es exactamente la pregunta que se discute.

**Qué no hacer en v1.** Una ontología formal —RDF, triple store, grafo semántico— resuelve un problema distinto: integrar vocabularios heterogéneos entre organizaciones que no se pusieron de acuerdo. Acá el problema es el opuesto: un dominio acotado y bien definido, donde el modelo relacional con eventos da más garantías —transaccionalidad, integridad referencial— y muchísimo menos costo de mantenimiento. Si más adelante hace falta exponer el modelo semánticamente, se hace encima sin rehacer nada.

**Qué sí tomar del enfoque ontológico.** La disciplina de nombrar bien las entidades y los eventos, y usar ese mismo vocabulario en la interfaz, en el código y frente al cliente. Que «certificación» signifique una sola cosa en todo el sistema, y que no convivan «conformidad», «aprobación» y «HES» para lo mismo. Ese lenguaje ubicuo es la mitad del valor del enfoque, y es gratis.

---

## 7. Captura en campo

La idea central es la correcta y es lo que hace que el producto valga: el técnico no transcribe nada, elige una línea de OC y el resto se completa solo. Eso baja el tiempo de carga a minutos y elimina la fuente principal de error de imputación.

| Pieza | Definición |
|---|---|
| OCR de la OC con revisión en segundo plano | El agente propone y una persona confirma. Sobre un documento que llega una vez por contrato, es razonable. Valor adicional: comparar el PDF contra lo cargado y avisar diferencias — así se detectan ampliaciones que nadie comunicó. |
| Selección de línea en el celular | Lista descargada localmente antes de salir a campo. Mostrar el saldo disponible al lado de cada línea, para que el técnico vea antes de trabajar que está por consumir contra una línea agotada. |
| Autocompletado de fecha, hora y ubicación | Del dispositivo. Guardar además la hora del servidor al sincronizar, y marcar si el GPS estaba desactivado o la ubicación es simulada. No por desconfianza: si alguna vez se discute un certificado, el que tiene los dos relojes gana. |
| Identidad del técnico | De la sesión autenticada, nunca de los datos del teléfono. Es la diferencia entre un dato declarado y uno probado, y el celular puede ser compartido por la cuadrilla. |
| Formulario de hoja de trabajo | Datos estándar internamente, plantilla de salida configurable por cliente. Cada operadora va a querer su formato; si el formulario es rígido, cada cliente nuevo es desarrollo. |
| Horas improductivas | Vía alternativa al parte normal, para cuando por causas ajenas no se puede prestar el servicio. El técnico elige una causal de una lista (a definir con el convenio de petroleros) y también se envía a firma del inspector, igual que un parte de trabajo ejecutado. |
| Identidad del inspector / certificador | Se autocompleta desde la ODV, pero el técnico puede editarla si en el momento firma una persona distinta de la que figura en el documento. |

### 7.1 Firma del certificador

Lo que se va a implementar es firma manuscrita capturada en pantalla más metadatos: nombre, DNI, cargo, hora, ubicación y hash del documento firmado. En Argentina eso es **firma electrónica** según la Ley 25.506: válida como prueba, pero con la carga de la prueba del lado de quien la invoca si el firmante la desconoce. La **firma digital** con certificado de una autoridad certificante tiene presunción legal a favor, pero exige que el certificador tenga token o certificado, cosa que en un yacimiento no va a pasar.

En la práctica se refuerza la firma electrónica: hash del PDF, sellado de tiempo, foto del firmante opcional, y sobre todo envío inmediato por mail al certificador con copia a su empresa. El acuse de recepción sin objeción dentro de X días es, comercialmente, tan fuerte como la firma.

> **Nota de posicionamiento.** No llamarlo «firma digital» en el material de venta. Llamarlo **conformidad firmada con evidencia**, que es lo que es, y no expone a una discusión legal que no hace falta dar.

---

## 8. Revisión de la propuesta de arquitectura evaluada

Sobre la propuesta de cinco capas generada previamente con otra herramienta. Sirve como mapa de opciones tecnológicas, no como arquitectura de este producto.

### Aciertos

- Identificar la HES como pieza pivote: sin ella no hay factura.
- Partir el DSO en tramo operativo y tramo financiero. Es además buen argumento de venta: le muestra al cliente que la plata no se traba solo en cobranzas.
- El *offline-first* como requisito no negociable.

### Objeciones

| Objeción | Detalle |
|---|---|
| Grano equivocado en el modelo de estados | El estado está a nivel OC y debe estar a nivel línea. Una HES cubre parcialmente varias líneas y una línea acumula muchas HES. Con estado único por OC no se puede representar «línea 3 certificada al 60%, línea 4 sin saldo». Todo el tablero se cae si el grano está mal elegido. |
| Falta el saldo contratado por línea | Es donde se pierde la plata. Trabajo ejecutado contra línea agotada: nunca va a haber HES ni factura, y nadie se entera hasta el cierre. Es un control preventivo, no un dashboard de estados. |
| No hay caminos infelices | Todo el flujo modelado es feliz. Faltan HES rechazada u observada, certificado que no se firma, factura rechazada por imputación, ampliación de OC, anulación. Ahí vive el dolor del cliente. |
| El OCR de la HES es fundación y debería ser optimización | Es la pieza más cara y más frágil, puesta como central. Con operadoras que usan SAP o Ariba, el número de HES suele venir por portal o cantado por el contract admin, no en un PDF prolijo por mail. Un campo donde alguien pega el número y sube el adjunto da el 90% del valor con el 5% del esfuerzo. |
| Contradice el alcance de v1 | El estado «Cobrado» y el DSO financiero requieren conciliación bancaria, explícitamente fuera de alcance. El producto ya se justifica mostrando trabajos sin certificar y certificaciones sin facturar. |
| La economía del stack no cierra | Azure Functions + Document Intelligence + Blob + Power BI + iPaaS, con Flutter arriba: cinco proveedores y cinco costos fijos para un producto que debe dejar USD 1.000 por mes. Power BI además se licencia por usuario, lo que lo hace problemático de revender dentro de un SaaS. |
| Falta lo que sostiene la propuesta de valor | Multi-tenant, permisos acumulables y sobre todo el log inmutable. La arquitectura tiene que decir explícitamente que un certificado firmado no se edita: se anula y se rehace, con todo registrado. |

> **Error de fondo.** La propuesta modela un flujo documental. Este producto es un control de consumo de contrato con evidencia firmada. La alternativa más barata y más fácil de cambiar es un backend monolítico sobre Postgres, con el tablero construido dentro de la misma aplicación y los archivos en object storage.

---

## 9. Decisiones tomadas y pendientes

### Tomadas

| Decisión | Fundamento |
|---|---|
| Alcance v1 hasta facturación, sin cobranzas ni banco | Recorte sostenido: el valor ya se demuestra con lo no certificado y lo no facturado. |
| Grano de estado a nivel línea de OC, no a nivel OC | Es el único grano que soporta certificaciones parciales y saldos. |
| Versionado de líneas; nada se pisa | Los cambios de OC son retroactivos y hay que poder reconstruir el pasado. |
| Registro de hechos append-only con bitemporalidad; sin ontología formal | Da trazabilidad total sobre Postgres, sin el costo de un stack semántico. |
| Certificador como participante externo, no como usuario | Ninguna operadora registra a sus inspectores en el sistema de un proveedor. |
| Certificado firmado inmutable: anular y rehacer | Es la regla que sostiene todo el argumento probatorio. |
| Permisos acumulables, no un rol por usuario | En empresas chicas una persona junta supervisión, facturación y configuración. |
| Se permite certificar sin saldo, marcado como excepción | Si se bloquea, el técnico certifica en papel y se pierde el dato. |
| Firma electrónica reforzada, comunicada como conformidad firmada con evidencia | Evita una discusión legal innecesaria y describe con precisión lo que el sistema hace. |

### Pendientes

- Confirmar si las operadoras del caso trabajan con OC marco y liberaciones, y si la certificación cuelga del segundo nivel. Verificar con el contacto en Oldelval.
- Definir si el subcontratista entra en la v1 o queda para una versión posterior.
- Decidir el canal de firma del certificador: tablet del técnico o link de un solo uso a su propio celular. Hay un trade-off entre velocidad y defensa legal.
- Relevar los formatos de certificado exigidos por las principales operadoras, para dimensionar el motor de plantillas.
- Fijar el glosario definitivo del dominio y usarlo en interfaz, código y material comercial.
- Resolver el caso de la HES parcial: anular y partir en dos, versus registrar monto menor.
- Definir qué documentos habilitantes exige cada operadora por técnico, quién los carga y con qué anticipación se alerta el vencimiento.
- Definir el listado de causales de horas improductivas, alineado al convenio de petroleros.
- Definir si el vencimiento del plazo de HES dispara un reclamo automático a la operadora o solo una alerta interna.
- Diseñar la vista Gantt del tablero (por técnico, por ODV) como complemento del tablero de estados.

### Glosario en construcción

| Término | Significado único en el sistema |
|---|---|
| Orden de compra (OC) | Documento del cliente que habilita el servicio y contiene líneas con saldo. |
| Línea de OC | Unidad mínima contratada. Grano de todo el sistema. Tiene versiones. |
| Orden de trabajo | Tarea asignada a una cuadrilla, imputada contra una línea de OC. |
| Certificación | Registro de trabajo ejecutado y aceptado, firmado por el certificador. |
| Certificador | Representante de la operadora que firma la conformidad en campo. |
| HES | Hoja de entrada de servicios: el número que emite la operadora y habilita facturar. |
| Saldo disponible | Resultado de las versiones de la línea menos lo certificado. Nunca un campo editable. |
| Documento habilitante | Documento del legajo del técnico (matrícula, curso de seguridad, ART, etc.) con vencimiento propio, requisito de la operadora para poder asignarlo a una línea de ODV. |
| Horas improductivas | Registro alternativo al parte de trabajo ejecutado, para cuando por causas ajenas al técnico no se puede prestar el servicio; lleva causal y también va a firma del inspector. |

---

## 10. Estados y transiciones

Hay cuatro máquinas de estado distintas y el error más común es fusionarlas. Van separadas, con los puntos de acople explícitos.

### 10.1 Línea de OC

Es la única que no representa un flujo sino una condición del contrato. El paso a *Agotada* o *Excedida* lo dispara el sistema al certificar, no una persona; la vuelta a *Vigente* la dispara una nueva versión de la línea. Cerrar una línea con certificaciones vivas debe pedir confirmación explícita, no bloquear.

| Estado | Significado | Sale hacia |
|---|---|---|
| Vigente | Con saldo disponible | Agotada, Excedida, Suspendida, Cerrada |
| Agotada | Saldo consumido al 100% | Vigente (por ampliación), Cerrada |
| Excedida | Certificado por encima del saldo | Vigente (ampliación), Cerrada |
| Suspendida | Bloqueada por decisión comercial | Vigente, Cerrada |
| Cerrada | No admite más consumo | terminal |

### 10.2 Orden de trabajo

| Estado | Transiciones | Quién |
|---|---|---|
| Planificada | → Asignada | PLA / SUP |
| Asignada | → En ejecución, → Cancelada, → Reasignada | SUP, TEC |
| En ejecución | → Ejecutada, → Suspendida | TEC |
| Suspendida | → En ejecución, → Cancelada | SUP |
| Ejecutada | → Cerrada (al generarse la certificación) | SIS |
| Cancelada | terminal | SUP |

*Ejecutada* no significa certificada. Una orden puede quedar ejecutada durante semanas sin que nadie genere el certificado, y ese hueco es uno de los indicadores del tablero.

### 10.3 Certificación — el ciclo central

```
   Borrador
   editable, sin sincronizar
        |
        v
   Pendiente de aprobación  <-------->  Devuelto a corrección
   espera al supervisor                 con observaciones
        |
        v
   Aprobado internamente
   listo para firmar
        |
        v
   Firmado                              (inmutable desde acá)
        |
        v
   Enviado a la operadora   ---------->  Observado
   corre el reloj de la HES              rechazo del cliente
        |                                      |
        v                                      |
   HES recibida                                |
   habilitado para facturar                    |
        |                                      v
        v                                 Anulado
   Facturado  ------------------------->  terminal, deja rastro
```

| Estado | Qué significa | Transiciones válidas |
|---|---|---|
| Borrador | Cargado en el celular, sin sincronizar | → Pendiente de aprobación. Único estado editable |
| Pendiente de aprobación | Sincronizado, esperando al supervisor | → Aprobado internamente, → Devuelto a corrección |
| Devuelto a corrección | Con observaciones del supervisor | → Pendiente de aprobación |
| Aprobado internamente | Listo para firmar en campo | → Firmado, → Anulado |
| Firmado | Conformidad del certificador capturada | → Enviado. Inmutable desde acá |
| Enviado a la operadora | Corre el reloj de la HES | → HES recibida, → Observado, → Vencido sin respuesta |
| Observado por el cliente | Rechazo u observación de la operadora | → Anulado (y se rehace) |
| Vencido sin respuesta | Superó el plazo configurado | → HES recibida (llegó tarde), → Observado |
| HES recibida | Habilitado para facturar | → Facturado, → Anulado |
| Facturado | Vinculado a una factura emitida | → Anulado (solo con nota de crédito) |
| Anulado | Terminal. Deja rastro y referencia al reemplazo | — |

> **Dos reglas duras.** Desde *Firmado* en adelante nada se edita: el único camino es *Anulado* más un certificado nuevo que lo referencia. Y *Anulado* nunca borra: es un hecho más en el registro.
>
> **Caso a decidir.** Si la HES llega parcial —la operadora aprueba menos de lo certificado— eso no es *Observado*. Es un certificado que se anula y se parte en dos: uno por el monto aprobado y otro por la diferencia en disputa. Modelarlo como «HES recibida con monto menor» hace perder el rastro del reclamo.

### 10.4 Factura

| Estado | Transiciones |
|---|---|
| Borrador | → Emitida, → Descartada |
| Emitida | → Presentada al cliente, → Anulada por NC |
| Presentada | → Aceptada, → Rechazada |
| Rechazada | → Anulada por NC (los certificados vuelven a HES recibida) |
| Aceptada | → Cobrada (fuera de alcance v1) |
| Anulada por NC | terminal |

El rechazo de factura es la transición más valiosa del sistema, porque devuelve los certificados a la cola en lugar de dejarlos perdidos.

### 10.5 Acoples entre máquinas

- Certificación pasa a *Firmado* → se recalcula el saldo de la línea, que puede pasar a *Agotada* o *Excedida*.
- Certificación pasa a *Facturado* → la factura la referencia; un certificado no puede facturarse dos veces.
- Factura pasa a *Anulada por NC* → los certificados vuelven a *HES recibida*.
- Orden de trabajo queda *Ejecutada* sin certificación durante X días → alerta.

> **Los tres relojes a parametrizar por cliente:** ejecutado sin certificar, firmado sin enviar, y enviado sin HES. Ahí es donde se congela la plata, y son exactamente las tres métricas del tramo operativo del DSO.

---

## 11. Autenticación, permisos y seguridad

### 11.1 Autenticación

Tres poblaciones con necesidades distintas, y conviene no darles el mismo mecanismo.

**Usuarios de oficina** (supervisión, administración, comercial): usuario y contraseña con segundo factor. Lo razonable es soportar además inicio de sesión con Google o Microsoft, porque casi todas estas empresas ya tienen uno de los dos y se evita la gestión de contraseñas. SSO empresarial (SAML/OIDC) es pedido de clientes grandes; dejarlo previsto pero no construirlo en v1.

**Técnicos de campo**: acá la fricción mata. Login inicial con credencial, y después sesión larga en el dispositivo con desbloqueo por PIN o biometría. Nadie va a tipear una contraseña compleja con guantes. El token del dispositivo debe poder revocarse desde el panel: si el celular se pierde o el técnico renuncia, el supervisor lo desactiva y el dispositivo se borra en la próxima conexión.

**Certificador**: no autentica. Firma sobre la sesión del técnico, o desde un link de un solo uso con vencimiento corto. Ese link es un token firmado, de uso único, atado a un certificado específico y a un destinatario, sin capacidad de navegar a ningún otro dato.

### 11.2 Autorización

El modelo es permisos acumulables, no un rol por usuario. Cinco perfiles base más dos de solo lectura, y una persona puede tener varios.

| Perfil | Permisos que agrupa |
|---|---|
| Campo | Ver órdenes asignadas, cargar avance, generar certificado, capturar firma |
| Supervisión | Todo lo de campo, más asignar, aprobar, devolver y anular |
| Administración | HES, facturación, exportación de respaldos |
| Comercial | OC y líneas, precios, tablero completo |
| Configuración | Usuarios, permisos, maestros, plantillas, integraciones |
| Lectura auditoría | Evidencia y log, sin precios |
| Lectura gerencial | Tablero e indicadores, sin edición |

Tres dimensiones adicionales de alcance, que son lo que realmente diferencia a un usuario de otro:

- **Por base o zona** — el jefe de Añelo no ve lo de Rincón.
- **Por cliente u operadora.**
- **Por sensibilidad del dato** — el técnico no debería ver precios ni saldos en pesos; le alcanza con ver si hay saldo o no, en forma de semáforo. Esto no es paranoia: los técnicos rotan entre empresas competidoras.

El subcontratista se resuelve con el perfil de campo más un alcance restringido a sus propias órdenes y sin visibilidad de precios. Ningún rol nuevo.

### 11.3 Seguridad

**Aislamiento multi-tenant.** Es la decisión más cara de revertir. Con Postgres, la vía sólida es *row-level security* con el identificador de tenant forzado a nivel de sesión de base, no filtrado en el código de la aplicación. Filtrar en el código funciona hasta que alguien olvida un `where` en una consulta nueva, y ese día un cliente ve datos de otro. Con RLS el olvido devuelve cero filas en lugar de datos ajenos.

**El dispositivo en campo.** Es la superficie de ataque más expuesta. Base local cifrada, sin datos de otros clientes en el dispositivo, expiración de la sesión si no sincroniza en X días, y borrado remoto. Descargar solo las órdenes asignadas a esa persona, no todo el catálogo.

**Integridad de la evidencia.** Los archivos van a object storage con acceso por URL firmada de vida corta, nunca públicos. Cada documento firmado guarda su hash; si alguien reemplaza el archivo, el hash no coincide y el sistema lo detecta. El log de auditoría es append-only, sin permisos de update ni delete sobre esa tabla ni siquiera para el rol de aplicación.

**El administrador de plataforma.** Esto es lo que más suele descuidarse y en este producto es crítico: el acceso propio de soporte tiene que ser de solo lectura por defecto, con impersonación limitada en tiempo, registrada y visible para el cliente. Si el proveedor puede editar silenciosamente un certificado firmado, el argumento probatorio no resiste una pregunta de un abogado.

**Datos personales.** El certificado guarda nombre, DNI, firma y ubicación de personas. Eso cae bajo la Ley 25.326: base de datos registrable, finalidad declarada, y política de retención. La retención larga que se necesita por prueba conviene documentarla como fundamento legítimo, no dejarla implícita.

### 11.4 Qué queda fuera de la v1

Sin culpa: SSO empresarial, gestión de dispositivos móviles (MDM), y cualquier certificación formal tipo ISO 27001.

No se puede dejar afuera: el aislamiento por RLS y el log inmutable. Ambos son casi imposibles de retrofitear sin reescribir.

---

## 12. Flujos de trabajo

Ya no es "qué hace cada actor" sino en qué orden pasan las cosas, qué dispara cada paso y adónde va si algo sale mal.

### 12.1 Alta y versionado de OC

| Paso | Dispara | Actor/sistema | Resultado |
|---|---|---|---|
| 1 | Llega la OC (PDF, planilla o portal) | COM / ADE | Archivo en repositorio |
| 2 | Extracción de líneas (manual, planilla o IA asistida) | COM / ADE | Borrador de líneas |
| 3 | Validación y confirmación de líneas | COM | Línea de OC creada, estado *Vigente* |
| 4 | *(rama)* Llega una modificación de una OC existente | Operadora | Nueva versión de la línea, con vigencia y motivo |
| 5 | Recalcular saldo por línea | SIS | Saldo actualizado, puede cambiar el estado de la línea |

Este flujo no termina nunca: el paso 4 se repite durante toda la vida del contrato. Por eso la OC es un flujo abierto, no un alta única.

### 12.2 Ejecución en campo

| Paso | Dispara | Actor | Resultado |
|---|---|---|---|
| 1 | Orden de trabajo asignada | SUP | Orden en estado *Asignada* |
| 2 | Técnico descarga sus órdenes y las líneas de ODV vigentes | TEC (offline) | Datos locales en el dispositivo |
| 3 | Técnico ejecuta, carga avance, adjunta evidencia | TEC / SUB | Orden en *En ejecución* |
| 4 | Técnico marca fin de tarea | TEC | Orden en *Ejecutada* |
| 5 | Sincroniza cuando hay señal | SIS | Datos en servidor |
| 6 | *(rama)* Si no certifica en X días | Reloj | Alerta a SUP y COM |
| 3b | *(rama)* No puede prestar el servicio por causa ajena | TEC | Registra horas improductivas con causal en lugar de avance normal, y esa línea también se envía a firma del inspector |

El punto 6 conecta este flujo con el tablero: es la primera de las tres métricas del tramo operativo.

### 12.3 Parte u Hoja de Trabajo (el flujo central)

| Paso | Dispara | Actor | Resultado |
|---|---|---|---|
| 1 | Se genera el Parte u Hoja de Trabajo desde la orden ejecutada | TEC / SUP | Parte u Hoja de Trabajo en *Borrador* |
| 2 | Sincroniza | SIS | *Pendiente de aprobación* |
| 3 | Supervisor revisa | SUP | *Aprobado internamente* o *Devuelto a corrección* (vuelve a 1) |
| 4 | Captura de firma en sitio | TEC + CER | *Firmado* — inmutable desde acá |
| 5 | Envío automático a la operadora | SIS | *Enviado*, arranca el reloj de Certificado |
| 6a | Llega Certificado | FAC | *Certificado recibida* → habilita facturar |
| 6b | *(rama)* Observación del cliente | FAC | *Observado* → *Anulado* → vuelve al paso 1 con nuevo certificado |
| 6c | *(rama)* Vence el plazo sin respuesta | Reloj | *Vencido sin respuesta* → alerta a COM |
| 6d | *(rama)* Certificado parcial | FAC | Certificado se anula y se parte en dos: uno al monto aprobado, otro por la diferencia (vuelve a 6b para ese remanente) |

Los pasos 6a-6d son el corazón del producto: ahí compiten la mayoría de las variantes reales.

> **Pendiente de definir.** Al vencer el plazo sin respuesta (6c), ¿el sistema dispara un reclamo automático hacia la operadora (mail o portal) o solo una alerta interna a Comercial para que una persona lo gestione? Impacta si se necesita integración de envío saliente o alcanza con la alerta.

### 12.4 Facturación

| Paso | Dispara | Actor | Resultado |
|---|---|---|---|
| 1 | Certificado en *Certificado recibido* aparece en la cola | SIS | Visible para FAC |
| 2 | Se verifica saldo | SIS | Bloquea o marca excepción |
| 3 | Se emite la factura, vinculada a uno o más certificados | FAC | Certificados en *Facturado* |
| 4 | Se presenta al cliente | FAC | Factura *Presentada* |
| 5a | Aceptada | Operadora | Fin del alcance v1 |
| 5b | *(rama)* Rechazada | Operadora | Certificados vuelven a *Certificado recibido*; factura *Anulada por NC* |

### 12.5 Flujo transversal — alertas y tablero

No es un flujo lineal sino un observador continuo sobre los otros cuatro:

- Ejecutado sin certificar (13.2 → alerta)
- Firmado sin enviar (13.3, entre pasos 4 y 5)
- Enviado sin Certificar (13.3, entre pasos 5 y 6)
- Saldo por agotarse (13.1, paso 5)

Estas cuatro alertas son, en términos de arquitectura, el mismo mecanismo aplicado a distintos relojes: un job que compara la fecha del último hecho contra un umbral configurable por cliente.

---

## 13. Modelo de datos

Dos capas: una tabla de hechos que es la fuente de verdad, y las entidades como proyecciones calculadas sobre esos hechos (ver sección 7). Si se modelan solo las entidades con campos mutables, se pierde exactamente la trazabilidad que es la base del producto.

### 13.1 Capa 1 — el registro de hechos

Una sola tabla append-only que sostiene todo el sistema.

| Campo | Qué guarda |
|---|---|
| `id_hecho` | identificador único |
| `id_tenant` | aislamiento multi-tenant, obligatorio en cada fila |
| `tipo_hecho` | ej. `linea_odv_creada`, `parte_firmado`, `certificado_recibido`, `factura_emitida` |
| `id_entidad` | a qué entidad de negocio se refiere |
| `tipo_entidad` | `linea_odv3. Matriz de actores y casos de uso

Referencias: **E** ejecuta · **A** aprueba · **L** solo lectura.
TEC técnico · SUP supervisor · FAC administración y facturación · COM comercial y gerencia · ADE administrador de la empresa · SUB subcontratista · CER certificador · AUD auditor · SIS sistema.

### 3.1 Contrato , órdenes de compra espejando ODV

| Caso de uso | Actores |
|---|---|
| Alta de ODV con líneas, precios y saldos | COM E · ADE E · FAC L |
| Ampliar o modificar líneas de ODV | COM E · SUP L |
| Consultar saldo disponible por línea | todos L |
| Alerta de saldo por agotarse | SIS E → COM, SUP |
| Cerrar o anular ODV | COM E · ADE A |

### 3.2 Asignacion , ejecución y Parte u Hoja de Trabajo

| Caso de uso | Actores |
|---|---|
| Crear orden de trabajo contra línea de ODV  | SUP E |
| Asignar cuadrilla o subcontratista          | SUP E |
| Registrar avance, horas y equipos en campo  | TEC E · SUB E |
| Adjuntar evidencia (fotos, mediciones, ATS) | TEC E · SUB E |
| Sincronizar trabajo cargado offline | SIS E |
| Genera Parte u Hoja de Trabajo y envia a firma electronica | TEC E · SUB E |
| Recibe el Parte u Hoja de Trabajo firmada | SUP L  · FAC L  |
| Validar vigencia de documentos habilitantes del técnico antes de asignar | SIS E · SUP L |
| Alerta por documento habilitante vencido en la asignación | SIS E → SUP E |
| Registrar horas improductivas con causal, cuando no se puede prestar el servicio por causas ajenas | TEC E · SUB E |
| Editar la identidad del certificador si en el momento firma alguien distinto del que figura en la ODV | TEC E |

### 3.3 Certificación o Habilita

| Caso de uso | Actores |
|---|---|
| Seguimiento del estado del certificado  | FAC E · SUP E |
| Recibe certificado de la operadora y control vs Parte | SIS E · FAC E |
| Registrar número de Certificado recibido | FAC E · SUP E |
| Registrar rechazo u observaciones del Certificado | FAC E · SUP E |

### 3.4 Facturación

| Caso de uso | Actores |
|---|---|
| Ver certificados con Certificado listos para facturar | FAC E |
| Verificar saldo antes de emitir | SIS E · FAC E |
| Emitir factura vinculada a certificados | FAC E |
| Registrar rechazo de factura y recircular | FAC E · COM L |
| Exportar respaldo completo de un caso | FAC E · AUD L |

### 3.5 Control y administración

| Caso de uso | Actores |
|---|---|
| Tablero de estados por línea y cuellos de botella | COM E · SUP L · FAC L |
| Vista Gantt de ODV asignadas por técnico, tiempo estimado vs. real (a partir del inicio y fin de tarea marcados en campo) | SUP L · COM L |
| Consultar log de auditoría | ADE L · AUD L · COM L |
| Alta y baja de usuarios, asignación de permisos | ADE E |
| Configurar maestros, plantillas y reglas de aprobación | ADE E |
| Configurar integración con ERP | ADE E |`, `orden_trabajo`, `certificacion`, `factura` |
| `fecha_hecho` | cuándo pasó en la realidad |
| `fecha_registro` | cuándo se guardó en el sistema — la bitemporalidad de la sección 7 |
| `actor` | quién lo generó (usuario, o `sistema` para lo automático) |
| `payload` | JSON con los datos específicos de ese tipo de hecho |
| `hecho_anterior_id` | si corrige o revierte un hecho previo, lo referencia — nunca se borra nada |
| `hash_evidencia` | si el hecho tiene un archivo asociado (certificado firmado, PDF de OC) |

Cada fila es inmutable. Un certificado que se anula no se borra ni se actualiza: se agrega un hecho `certificado_anulado` que referencia al original, y otro `certificado_creado` para el reemplazo.

### 13.2 Capa 2 — entidades (proyecciones)

Tablas normales, pero conceptualmente son una "foto" recalculable a partir de la capa 1. En la práctica se actualizan al vuelo cuando llega un hecho nuevo, para no recalcular todo en cada lectura — pero el registro de hechos manda si alguna vez discrepan.

- **`tenant`** — la empresa cliente. Todo cuelga de acá para el aislamiento por RLS.
- **`orden_compra`** — cabecera: operadora, número, tipo (marco o directa), estado.
- **`linea_oc`** — pertenece a una OC. Tiene **versiones** (tabla separada `linea_oc_version`: precio, cantidad, vigencia desde/hasta, motivo del cambio). El saldo disponible no es un campo, es una vista calculada: suma de versiones vigentes menos suma de certificaciones activas contra esa línea.
- **`orden_trabajo`** — cuelga de una línea de OC, tiene cuadrilla asignada, estado, y las evidencias que se van adjuntando (avance, materiales, ATS).
- **`certificacion`** — cuelga de una orden de trabajo y de la versión de línea vigente al momento de la firma (la ata a esa versión específica, no a la línea en general). Campos: estado, certificador (nombre/DNI/empresa, sin ser un usuario del sistema), firma, hash del PDF, número de HES, referencia al certificado que anula o al que reemplaza.
- **`factura`** — vinculada a uno o más certificados a través de una tabla puente `factura_certificacion`, porque una factura puede agrupar varios certificados y (en el caso de HES parcial) un certificado puede terminar total o parcialmente facturado.
- **`usuario`** y **`permiso`** — usuario con permisos acumulables (tabla puente usuario-perfil), más las tres dimensiones de alcance de la sección 12: zona, cliente/operadora, nivel de sensibilidad de dato.

### 13.3 Relaciones clave

```
tenant 1──N orden_compra 1──N linea_oc 1──N linea_oc_version
                                  │
                                  └──N orden_trabajo 1──N certificacion
                                                              │
                                                              └──N (vía puente) factura
```

### 13.4 Tres decisiones de modelado

**El saldo nunca es una columna editable.** Es una vista o una columna calculada por trigger a partir de `linea_oc_version` y las certificaciones activas. Si se hace columna editable, en algún punto un `UPDATE` manual la desincroniza del historial de hechos y se pierde la garantía central del producto.

**La certificación referencia una versión de línea, no la línea.** Así el certificado queda congelado con el precio vigente al momento de la firma (sección 6.1), sin importar cuántas versiones tenga la línea después.

**RLS a nivel de `id_tenant` en cada tabla**, forzado por política de Postgres, no por `WHERE` en el código de aplicación (sección 12.3).

Con esto el modelo queda en condiciones de pasar a Claude Code: entidades, relaciones, el registro de hechos como fuente de verdad, y las reglas de negocio no negociables — inmutabilidad post-firma, saldo calculado, versionado de líneas, RLS.
