import type { paths } from "./generated/modulo1";

// Derived from parameters in the pinned OpenAPI; auth/storage excluded.
export const idempotentPostPaths = [
  "/v1/comandos/alta_de_sujeto",
  "/v1/comandos/baja_de_sujeto",
  "/v1/comandos/cancelar_oc",
  "/v1/comandos/cargar_documento",
  "/v1/comandos/cargar_requisito_particular",
  "/v1/comandos/configurar_alertas",
  "/v1/comandos/configurar_canales",
  "/v1/comandos/configurar_drive",
  "/v1/comandos/confirmar_documento",
  "/v1/comandos/confirmar_subida_de_evidencia",
  "/v1/comandos/crear_certificado_respaldo",
  "/v1/comandos/copiar_definicion_global",
  "/v1/comandos/copiar_matriz_global",
  "/v1/comandos/dar_de_alta_definicion_de_requisito",
  "/v1/comandos/dar_de_baja_definicion_de_requisito",
  "/v1/comandos/descartar_archivo_drive",
  "/v1/comandos/escanear_drive",
  "/v1/comandos/generar_paquete_entrega",
  "/v1/comandos/importar_lote",
  "/v1/comandos/importar_planilla_operadoras",
  "/v1/comandos/invalidar_evidencia",
  "/v1/comandos/preparar_subida_de_evidencia",
  "/v1/comandos/proponer_documento",
  "/v1/comandos/publicar_version_de_matriz",
  "/v1/comandos/rechazar_propuesta",
  "/v1/comandos/reconocer_alerta",
  "/v1/comandos/registrar_acreditacion_de_competencia",
  "/v1/comandos/registrar_estado_documento_operadora",
  "/v1/comandos/registrar_induccion",
  "/v1/comandos/resolver_archivo_drive",
  "/v1/comandos/revertir_lote",
  "/v1/comandos/revocar_paquete_entrega",
  "/v1/comandos/vincular_telegram"
] as const satisfies readonly (keyof paths)[];

type CommandPath = typeof idempotentPostPaths[number];
type CommandBody<P extends CommandPath> = paths[P]["post"] extends { requestBody: { content: { "application/json": infer B } } } ? B : never;
export function createCommandIntent<P extends CommandPath>(path: P, body: CommandBody<P>) {
  if (!(idempotentPostPaths as readonly string[]).includes(path)) throw new Error("Header not declared for this operation");
  const serializedBody = JSON.stringify(body);
  const key = crypto.randomUUID();
  return Object.freeze({ path, method: "POST" as const, key, serializedBody, headers: Object.freeze({ "Idempotency-Key": key, "Content-Type": "application/json" }) });
}

