# Expo Kiosk Vouchers (Django + MySQL)

Aplicacion de kiosco para emision de vouchers con control diario por persona/voucher, pools diarios de stock por comida y soporte para multiples empresas y multiples totems con ticket termico.

## Flujo funcional

1. Pantalla inicial por marca:
   - `/totem/fendt/`
   - `/totem/valtra/`
   - `/totem/massey/`
2. Ingreso de documento (`.../dni/`) con selector `DNI / PASAPORTE` y teclado nativo Android
3. Consulta de cupos del dia
4. Canje de una o ambas comidas (desayuno/almuerzo) con invitados por comida
5. Emision e impresion del ticket (`/tickets/<ticket_numero>/`)

## API

- `POST /api/lookup`
- `POST /api/redeem`
- `POST /api/redeem-batch`
- `POST /api/reprint-last` (reimpresion de ultima operacion del dia con PIN de soporte)
- `GET /api/reports/daily?dia=YYYY-MM-DD&empresa_codigo=`
- `GET /api/reports/redeems?desde=YYYY-MM-DD&hasta=YYYY-MM-DD&dni=&totem_id=&empresa_codigo=&limit=500`
- `GET /api/reports/redeems.csv?desde=YYYY-MM-DD&hasta=YYYY-MM-DD&dni=&totem_id=&empresa_codigo=&limit=2000`
- `GET /api/healthz`
- `GET /healthz`

`POST /api/*` requiere CSRF (flujo kiosk same-origin).

Ejemplo `redeem-batch` (desde frontend):

```json
{
  "dni": "30111222",
  "totem_id": "TOTEM-01",
  "empresa_codigo": "VALTRA_FENDT",
  "items": [
    {"comida": "DESAYUNO", "invitados": 2},
    {"comida": "ALMUERZO", "invitados": 1}
  ]
}
```

Reglas principales:

- `DESAYUNO` y `ALMUERZO`: maximo 1 fijo por persona por dia.
- Los invitados usan el mismo pool diario de la comida (`DESAYUNO` / `ALMUERZO`) del tótem.
- Invitados en desayuno/almuerzo se habilitan si `Persona.puede_invitar=true` o si el nombre está en `KIOSK_SPECIAL_GUEST_NAMES`.
- Pools diarios configurables por entorno por marca/tótem:
  `VALTRA` 100/100, `FENDT` 20/20, `MASSEY` 120/120 por defecto.
- Aislamiento multiempresa: `MASSEY` usa padrón propio; `VALTRA_FENDT` comparte padrón entre ambos tótems.
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
DJANGO_ENV=dev SECURE_SSL_REDIRECT=False DEFAULT_EMPRESA_CODE=DEFAULT DB_ENGINE=sqlite SQLITE_NAME=db_test.sqlite3 .venv/bin/python manage.py test
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
export MYSQL_PORT=3307
export DEFAULT_EMPRESA_CODE=DEFAULT
export SUPPORT_REPRINT_PIN=4832
export KIOSK_SPECIAL_GUEST_NAMES="Facundo Guzman,Gesica Pieditorti"
export POOL_STOCK_TOTEM_VALTRA_DESAYUNO=100
export POOL_STOCK_TOTEM_VALTRA_ALMUERZO=100
export POOL_STOCK_TOTEM_FENDT_DESAYUNO=20
export POOL_STOCK_TOTEM_FENDT_ALMUERZO=20
export POOL_STOCK_TOTEM_MASSEY_DESAYUNO=120
export POOL_STOCK_TOTEM_MASSEY_ALMUERZO=120
```

Aplicar esquema y datos base:

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_vouchers
```

## Importacion desde Excel

Layout con DNI (alta/actualizacion directa, por ejemplo Massey):

```bash
.venv/bin/python manage.py import_personas_excel /ruta/massey.xlsx --empresa-code MASSEY --empresa-name "Massey Ferguson"
```

Columnas requeridas:
- `DNI`
- `Nombre y Apellido`

Columnas opcionales:

- `Concesionario`
- `Credencial`
- `Tipo de vianda` (`Clasico`, `Vegetariano` o `Celiaco`)
- `Puede invitar` (`si/no`, `true/false`, `1/0`, `x`)

Layout Valtra/Fendt sin DNI en el Excel:

```bash
.venv/bin/python manage.py import_personas_excel "/Users/marcosklein/Downloads/Viandas Expoagro 2026 Valtra - Fendt.xlsx" --empresa-code VALTRA_FENDT --empresa-name "Valtra Fendt" --layout valtra_fendt
```

Ese layout actualiza por nombre sobre un padrón ya existente porque no trae DNI. Si una fila no encuentra coincidencia única, se omite y queda reportada.

Registro de empresas/totems:

```bash
.venv/bin/python manage.py upsert_empresa --codigo VALTRA_FENDT --nombre "Valtra Fendt"
.venv/bin/python manage.py upsert_empresa --codigo MASSEY --nombre "Massey Ferguson"
.venv/bin/python manage.py upsert_totem --codigo TOTEM_VALTRA --empresa-code VALTRA_FENDT --nombre "Totem Valtra"
.venv/bin/python manage.py upsert_totem --codigo TOTEM_FENDT --empresa-code VALTRA_FENDT --nombre "Totem Fendt"
.venv/bin/python manage.py upsert_totem --codigo TOTEM_MASSEY --empresa-code MASSEY --nombre "Totem Massey"
```

## URLs operativas

- Totem FENDT: `/totem/fendt/`
- Totem VALTRA: `/totem/valtra/`
- Totem MASSEY: `/totem/massey/`
- Alta admin de invitados/personas: `/registro/personas/` con selector de padrón `Massey` o `Valtra/Fendt`

## Totems e impresion termica

- El flujo principal de impresion en totem Android usa **RawBT** via intent (`rawbt://`), igual que `turneraOnline`.
- `Finalizar e imprimir` genera tickets en backend y el frontend dispara automaticamente el intent con ESC/POS.
- En la pantalla de vouchers hay flujo de soporte para reimpresion de la ultima operacion del dia (misma persona + mismo totem), protegido por PIN (`SUPPORT_REPRINT_PIN`).
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
