# kalitron-telegram-bot

MVP de Telegram preparado para evolucionar a una arquitectura multi-canal sin rediseñar la aplicación.

## Contrato fuente inspeccionado

La integración toma como contrato real el repositorio `ai-gateway`:

- `POST /api/v1/validate/receipt`
- `POST /api/v1/validate/identity`
- autenticación por `X-API-Key`
- `multipart/form-data`
- archivos permitidos: `image/jpeg`, `image/png`, `image/webp`

Para recibos, el gateway solo acepta estos valores de `source`:

- `whatsapp`
- `crm`
- `web`
- `manual`

Gap actual del contrato:

- `telegram` no está soportado como `source` por `ai-gateway`
- por eso el dominio interno del bot usa `channel=telegram`, pero una capa adaptadora lo traduce a un `source` válido del gateway
- `identity` no usa `source`, así que no requiere mapping de canal

## Arquitectura

El diseño separa canal, aplicación, adaptación de contrato y transporte:

- `TelegramChannelAdapter` registra comandos y filtros de Telegram
- `TelegramBotHandlers` convierten mensajes de Telegram a comandos neutrales al canal
- `ValidationUseCases` trabaja con `IncomingDocument`, `InputChannel` y comandos de validación
- `GatewayValidationAdapter` traduce desde el dominio interno al contrato actual de `ai-gateway`
- `GatewayHttpClient` solo ejecuta requests HTTP y parsea respuestas

Esto deja lista la entrada de WhatsApp después:

- un futuro `WhatsAppChannelAdapter` podría construir el mismo `IncomingDocument`
- reutilizaría `ValidationUseCases`, `CsvClientResolver`, `GatewayValidationAdapter`, `GatewayHttpClient` y el modelo de dominio
- solo cambiaría el adapter de entrada del canal y su wiring

## Qué es reutilizable

- [application.py](/home/desarrollo/dev/proyectos/telegram-bot/src/kalitron_telegram_bot/application.py)
- [domain.py](/home/desarrollo/dev/proyectos/telegram-bot/src/kalitron_telegram_bot/domain.py)
- [gateway_adapter.py](/home/desarrollo/dev/proyectos/telegram-bot/src/kalitron_telegram_bot/gateway_adapter.py)
- [gateway_http_client.py](/home/desarrollo/dev/proyectos/telegram-bot/src/kalitron_telegram_bot/gateway_http_client.py)
- [client_registry.py](/home/desarrollo/dev/proyectos/telegram-bot/src/kalitron_telegram_bot/client_registry.py)
- [errors.py](/home/desarrollo/dev/proyectos/telegram-bot/src/kalitron_telegram_bot/errors.py)

## Qué es específico de Telegram

- [telegram_adapter.py](/home/desarrollo/dev/proyectos/telegram-bot/src/kalitron_telegram_bot/telegram_adapter.py)
- [handlers.py](/home/desarrollo/dev/proyectos/telegram-bot/src/kalitron_telegram_bot/handlers.py)
- `TELEGRAM_BOT_TOKEN`
- el mapping `TELEGRAM_GATEWAY_RECEIPT_SOURCE`

## Configuración

- `TELEGRAM_BOT_TOKEN`
- `GATEWAY_BASE_URL`
- `GATEWAY_API_KEY`
- `GATEWAY_TIMEOUT_SECONDS`
- `CLIENT_REGISTRY_CSV_PATH=config/client_registry.csv`
- `ACCESS_CODE_CSV_PATH=config/access_codes.csv`
- `TELEGRAM_GATEWAY_RECEIPT_SOURCE=manual`
- `WHATSAPP_GATEWAY_RECEIPT_SOURCE=whatsapp`

Notas:

- no se fuerza configuración para `identity` porque el contrato del gateway no usa `source` en ese endpoint
- `WHATSAPP_GATEWAY_RECEIPT_SOURCE` queda explícito para mostrar cómo entraría un segundo canal, aunque este MVP todavía no implementa WhatsApp
- el bot ya no usa `telegram_user_id` como `client_id` del gateway; primero resuelve un `client_id` interno mediante CSV

## Registro de clientes

El MVP resuelve clientes desde un CSV configurable en `CLIENT_REGISTRY_CSV_PATH`.

Formato esperado:

```csv
client_id,channel,user_id,chat_id,username,phone_number
client-telegram-demo,telegram,123456789,123456789,demo_telegram_user,
client-whatsapp-demo,whatsapp,,,,5215555555555
```

Reglas:

- `client_id` es el identificador interno que se manda al gateway
- `channel` hoy admite `telegram` y `whatsapp`
- para Telegram el resolver intenta en este orden: `user_id`, `chat_id`, `username`
- para WhatsApp queda listo el campo `phone_number`, aunque el adapter de WhatsApp aún no existe
- si no hay match en el CSV, el bot rechaza la solicitud y no llama al gateway

## Alta Por Codigo

El onboarding inicial ya soporta mensajes tipo:

```text
ALTA ABC123XYZ
```

Flujo:

1. cargas codigos en [config/access_codes.csv](/home/desarrollo/dev/proyectos/telegram-bot/config/access_codes.csv)
2. el usuario manda `ALTA <codigo>` al bot
3. el bot valida que el codigo exista para el canal `telegram` y que no este usado
   y que no este expirado
4. si es valido, agrega la identidad de Telegram al [config/client_registry.csv](/home/desarrollo/dev/proyectos/telegram-bot/config/client_registry.csv)
5. marca el codigo como `used=true`
   y registra `used_at`
6. desde ese momento el usuario ya puede usar `/receipt` y `/identity`

Formato de `access_codes.csv`:

```csv
access_code,client_id,channel,used,expires_at,used_at
ABC123XYZ,client-telegram-demo,telegram,false,2027-12-31T23:59:59+00:00,
```

Notas:

- el `client_id` del gateway sale del codigo, no del `telegram_user_id`
- un codigo solo puede usarse una vez
- `expires_at` usa formato ISO 8601 con zona horaria
- si quieres regenerar un codigo, agrega una nueva fila con otro `access_code`, `used=false` y una expiracion nueva
- si el usuario ya estaba registrado, el alta devuelve su `client_id` actual y no duplica el enlace
- esto deja listo un onboarding similar para WhatsApp con `channel=whatsapp`

## Uso

1. Configura variables de entorno a partir de `.env.example`.
2. Instala dependencias:

```bash
pip install -e .[dev]
```

3. Ejecuta el bot:

```bash
kalitron-telegram-bot
```

## Comandos del MVP

- `/start`
- `/receipt`
- `/identity INE`
- `/identity PASAPORTE`
- `/identity LICENCIA`

Después del comando, envía una imagen como foto o documento.

## Estructura

- [config.py](/home/desarrollo/dev/proyectos/telegram-bot/src/kalitron_telegram_bot/config.py): configuración
- [telegram_adapter.py](/home/desarrollo/dev/proyectos/telegram-bot/src/kalitron_telegram_bot/telegram_adapter.py): adapter de entrada para Telegram
- [handlers.py](/home/desarrollo/dev/proyectos/telegram-bot/src/kalitron_telegram_bot/handlers.py): traducción desde Telegram al caso de uso
- [application.py](/home/desarrollo/dev/proyectos/telegram-bot/src/kalitron_telegram_bot/application.py): capa de aplicación neutral al canal
- [client_registry.py](/home/desarrollo/dev/proyectos/telegram-bot/src/kalitron_telegram_bot/client_registry.py): resolución de `client_id` interno desde identidades de canal
- [gateway_adapter.py](/home/desarrollo/dev/proyectos/telegram-bot/src/kalitron_telegram_bot/gateway_adapter.py): mapping del dominio al contrato del gateway
- [gateway_http_client.py](/home/desarrollo/dev/proyectos/telegram-bot/src/kalitron_telegram_bot/gateway_http_client.py): transporte HTTP
- [config/client_registry.csv](/home/desarrollo/dev/proyectos/telegram-bot/config/client_registry.csv): ejemplo versionado del registro CSV
- [config/access_codes.csv](/home/desarrollo/dev/proyectos/telegram-bot/config/access_codes.csv): codigos de alta por canal
- [tests/test_gateway_client.py](/home/desarrollo/dev/proyectos/telegram-bot/tests/test_gateway_client.py): pruebas del adaptador y del cliente HTTP
