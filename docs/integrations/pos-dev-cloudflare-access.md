# Integracion POS DEV Con Cloudflare Access

Documentacion tecnica interna para la conexion Ecommerce DEV -> POS DEV. Este documento describe la configuracion validada durante la etapa de integracion y no implica cambios en endpoints productivos.

## Contexto

- Ecommerce DEV: `https://yakero-backend-ecommerce-dev.onrender.com`
- POS DEV: `https://posdev.tehagolaweb.cl`
- Endpoint POS consumido por Ecommerce DEV: `https://posdev.tehagolaweb.cl/api/external/catalog/summary`
- Endpoint de diagnostico en Ecommerce DEV: `GET /api/v1/debug/pos/raw-summary`

La prueba validada desde Render confirmo que Ecommerce DEV puede llamar al POS DEV a traves de Cloudflare y recibir productos reales del POS.

## Arquitectura

Flujo esperado:

```text
Ecommerce DEV (Render)
  -> Cloudflare DNS/WAF/Access para posdev.tehagolaweb.cl
  -> POS DEV
  -> Django
  -> /api/external/catalog/summary
```

La proteccion perimetral de Cloudflare filtra el trafico antes de llegar al POS. Para las rutas externas necesarias del POS, Cloudflare Access debe permitir el paso del trafico tecnico desde Render. La autenticacion final de la API sigue ocurriendo en Django mediante el header `X-Internal-Token`.

## Variables

### `POS_API_BASE_URL`

Base URL del POS que consume el ecommerce.

Valor esperado en Ecommerce DEV:

```text
https://posdev.tehagolaweb.cl
```

### `POS_INTERNAL_TOKEN`

Token interno que Ecommerce DEV usa para autenticarse contra POS DEV.

Se envia desde Ecommerce DEV hacia POS DEV como:

```text
X-Internal-Token: <POS_INTERNAL_TOKEN>
```

No debe exponerse en logs, documentacion, commits ni respuestas de debug.

### `INTERNAL_BOOTSTRAP_TOKEN`

Token interno del ecommerce usado para proteger endpoints internos o de diagnostico del propio backend ecommerce.

Para ejecutar el diagnostico desde fuera del ecommerce se envia como:

```text
X-Internal-Token: <INTERNAL_BOOTSTRAP_TOKEN>
```

## Diferencia Entre Tokens

`INTERNAL_BOOTSTRAP_TOKEN` pertenece al backend ecommerce. Sirve para autorizar llamadas internas o de diagnostico contra Ecommerce DEV, por ejemplo `GET /api/v1/debug/pos/raw-summary`.

`POS_INTERNAL_TOKEN` pertenece al POS. Ecommerce DEV lo usa como credencial de salida cuando llama a POS DEV, por ejemplo al endpoint `/api/external/catalog/summary`.

Resumen:

- Cliente tecnico -> Ecommerce DEV: usa `INTERNAL_BOOTSTRAP_TOKEN`.
- Ecommerce DEV -> POS DEV: usa `POS_INTERNAL_TOKEN`.

No intercambiar estos valores ni reutilizarlos entre servicios.

## Endpoint De Diagnostico

Endpoint usado para validar conectividad desde Render hacia POS DEV:

```text
GET /api/v1/debug/pos/raw-summary
```

Este endpoint debe llamarse contra Ecommerce DEV y, desde ahi, el backend ecommerce realiza la llamada real al POS:

```text
GET https://posdev.tehagolaweb.cl/api/external/catalog/summary
```

## Comando De Prueba

PowerShell:

```powershell
curl.exe -i -H "X-Internal-Token: <INTERNAL_BOOTSTRAP_TOKEN>" "https://yakero-backend-ecommerce-dev.onrender.com/api/v1/debug/pos/raw-summary"
```

No usar tokens reales completos en tickets, commits, capturas ni documentacion.

## Resultado Esperado

Respuesta exitosa del endpoint de diagnostico:

- `status_code: 200`
- `request_url: https://posdev.tehagolaweb.cl/api/external/catalog/summary`
- `token_length: 27`
- `response_text_preview` contiene `products` reales del POS.

## Sintomas Detectados

Durante el diagnostico se observaron estos sintomas:

- `403` con HTML generico.
- `403 Error - Cloudflare Access`.
- Django POS sin logs de la solicitud.

La ausencia de logs en Django indicaba que la solicitud era bloqueada antes de llegar a la aplicacion POS.

## Causa Raiz

Habia dos controles en Cloudflare que bloqueaban el trafico desde Render/AWS:

1. Regla WAF `BLOCK_NOT_CL`:

```text
(ip.src.country ne "CL")
```

Esta regla bloqueaba trafico que no viniera desde Chile. Render/AWS no necesariamente sale desde IPs geolocalizadas en Chile.

2. Cloudflare Access tenia una app:

```text
PosDev External API
Destino: posdev.tehagolaweb.cl/api/*
Politica: Bypass External API
```

La politica `Bypass External API` estaba limitada a:

```text
Include: Country = Chile
```

Eso impedia que Ecommerce DEV en Render pudiera pasar por Cloudflare Access, aunque el POS tuviera autenticacion propia en Django.

## Configuracion Final Esperada En Cloudflare

### WAF

Configurar una regla de allow o una excepcion para integraciones POS, por ejemplo:

```text
ALLOW_POS_INTEGRATIONS
```

La regla `BLOCK_NOT_CL` puede mantenerse, pero no debe bloquear el host:

```text
posdev.tehagolaweb.cl
```

Objetivo:

- Mantener bloqueo general para trafico fuera de Chile cuando aplique.
- Permitir las rutas/API necesarias para integracion Ecommerce DEV -> POS DEV.
- Evitar que Render/AWS quede bloqueado solo por geolocalizacion.

### Access

Aplicacion:

```text
PosDev External API
```

Destino:

```text
posdev.tehagolaweb.cl/api/*
```

Politica:

```text
Bypass External API
```

La politica debe ser apta para trafico desde Render. No debe depender exclusivamente de `Country = Chile` si Ecommerce DEV corre en Render/AWS.

## Seguridad

- No exponer `POS_INTERNAL_TOKEN` en logs, respuestas, capturas, tickets ni commits.
- No incluir tokens reales completos en la documentacion; usar `<INTERNAL_BOOTSTRAP_TOKEN>` y `<POS_INTERNAL_TOKEN>`.
- El bypass de Cloudflare Access debe aplicar solo a las rutas API externas necesarias, no a todo el dominio si no es requerido.
- La autenticacion final sigue en Django con el header `X-Internal-Token`.
- El endpoint POS debe validar `X-Internal-Token: <POS_INTERNAL_TOKEN>`.
- El endpoint debug del ecommerce debe validar `X-Internal-Token: <INTERNAL_BOOTSTRAP_TOKEN>`.
- Eliminar endpoints debug cuando termine la etapa de integracion.

## Estado Validado

La integracion Ecommerce DEV -> POS DEV quedo validada desde Render con:

- `status_code: 200`
- `token_length: 27`
- `response_text_preview` con `products` reales del POS.

