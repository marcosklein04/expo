# Expo Kiosk Vouchers (Django + MySQL)

Aplicacion de kiosco para emision de vouchers con control diario por persona/voucher, pools diarios de stock por comida y soporte para multiples totems con ticket termico.

## Flujo funcional

1. Pantalla inicial (`/`)
2. Ingreso DNI (`/kiosk/dni/`)
3. Consulta de cupos del dia
4. Canje de una o ambas comidas (desayuno/almuerzo) con invitados por comida
5. Emision e impresion del ticket (`/tickets/<ticket_numero>/`)

## API

- `POST /api/lookup`
- `POST /api/redeem`
- `POST /api/redeem-batch`
- `GET /api/reports/daily?dia=YYYY-MM-DD`
- `GET /api/reports/redeems?desde=YYYY-MM-DD&hasta=YYYY-MM-DD&dni=&totem_id=&limit=500`
- `GET /api/reports/redeems.csv?desde=YYYY-MM-DD&hasta=YYYY-MM-DD&dni=&totem_id=&limit=2000`
- `GET /api/healthz`
- `GET /healthz`

`POST /api/*` requiere CSRF (flujo kiosk same-origin).

Ejemplo `redeem-batch` (desde frontend):

```json
{
  "dni": "30111222",
  "totem_id": "TOTEM-01",
  "items": [
    {"comida": "DESAYUNO", "invitados": 2},
    {"comida": "ALMUERZO", "invitados": 1}
  ]
}
```

Reglas principales:

- `DESAYUNO` y `ALMUERZO`: maximo 1 fijo por persona por dia.
- `INVITADO_DESAYUNO` y `INVITADO_ALMUERZO`: maximo 5 por persona por comida y por dia.
- Pools diarios configurables por entorno (`POOL_STOCK_*`) para cortar stock global.
- Cada click en `Finalizar e imprimir` se guarda como `CanjeOperacion` con items por comida.
- Cada ticket queda asociado a su operacion de canje para trazabilidad completa.

Ejemplo `reportes`:

```bash
curl "http://localhost:8000/api/reports/daily?dia=2026-03-02"
```

## Setup local

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python manage.py makemigrations
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_vouchers
.venv/bin/python manage.py runserver
```

Editar `.env` y definir `DJANGO_ENV=dev` para local o `DJANGO_ENV=prod` para nube.

Tests:

```bash
DB_ENGINE=sqlite SQLITE_NAME=db_test.sqlite3 .venv/bin/python manage.py test
```

## Setup MySQL

Configurar variables de entorno:

```bash
export DB_ENGINE=mysql
export DJANGO_ENV=prod
export MYSQL_DATABASE=expo_kiosk
export MYSQL_USER=expo_kiosk_user
export MYSQL_PASSWORD=CHANGE_ME_STRONG_PASSWORD
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export POOL_STOCK_FIJOS_DESAYUNO=120
export POOL_STOCK_FIJOS_ALMUERZO=120
export POOL_STOCK_INVITADOS_DESAYUNO=120
export POOL_STOCK_INVITADOS_ALMUERZO=120
```

Aplicar esquema y datos base:

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_vouchers
```

## Importacion desde Excel

```bash
.venv/bin/python manage.py import_personas_excel /ruta/personas.xlsx --sheet Hoja1
```

Columnas requeridas:

- `DNI`
- `Nombre y Apellido`
- `Concesionario`
- `Credencial`

Ejemplo real para Expoagro:

```bash
.venv/bin/python manage.py import_personas_excel "/Users/marcosklein/Downloads/Listado comedor expoagro 2026.xlsx" --sheet Hoja1
```

El importador detecta automaticamente la fila de cabecera, aunque no sea la primera.

## Totems e impresion termica

- El flujo principal de impresion en totem Android usa **RawBT** via intent (`rawbt://`), igual que `turneraOnline`.
- `Finalizar e imprimir` genera tickets en backend y el frontend dispara automaticamente el intent con ESC/POS.
- En la pantalla inicial, la primera vez por sesion se envia `test` a RawBT para inicializar la conexion (mismo criterio que `turneraOnline`).
- Si el dispositivo no es Android (o para pruebas), cae a impresion de navegador (`window.print()`).
- Para forzar modo navegador manualmente usar: `/kiosk/vouchers/?dni=...&print_mode=browser`
- Cada totem debe ejecutar con su propio `DEFAULT_TOTEM_ID` para trazabilidad de auditoria.

## CSS

- Todos los estilos quedaron centralizados en `static/style/style.css`.

## Despliegue nube (resumen)

- Ejecutar con `gunicorn config.wsgi:application` detras de Nginx o LB cloud.
- Configurar `DB_ENGINE=mysql` + credenciales gestionadas (RDS/Cloud SQL/Aurora).
- Correr `manage.py migrate` y `manage.py seed_vouchers` en cada release.
- Definir `DEFAULT_TOTEM_ID` distinto por totem.
- Habilitar TLS, `SECURE_SSL_REDIRECT`, HSTS y cookies seguras en produccion.
- Monitorear errores y auditoria de emision (`kiosk.audit` logs + tabla `core_ticket`).
- Exponer `/healthz` para monitoreo del balanceador.
