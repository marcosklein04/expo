# Expo Kiosk Vouchers (Django + MySQL)

Aplicacion de kiosco para emision de vouchers con control diario por persona/voucher, soporte para multiples totems y tickets termicos.

## Flujo funcional

1. Pantalla inicial (`/`)
2. Ingreso DNI (`/kiosk/dni/`)
3. Consulta de cupos del dia
4. Canje de voucher
5. Emision e impresion del ticket (`/tickets/<ticket_numero>/`)

## API minima

- `POST /api/lookup`
- `POST /api/redeem`

Ejemplo `lookup`:

```bash
curl -X POST http://localhost:8000/api/lookup \
  -H 'Content-Type: application/json' \
  -d '{"dni":"30111222"}'
```

Ejemplo `redeem`:

```bash
curl -X POST http://localhost:8000/api/redeem \
  -H 'Content-Type: application/json' \
  -d '{"dni":"30111222","voucher":"DESAYUNO","totem_id":"TOTEM-01"}'
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

## Setup MySQL

Configurar variables de entorno:

```bash
export DB_ENGINE=mysql
export MYSQL_DATABASE=expo
export MYSQL_USER=expo
export MYSQL_PASSWORD=expo
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
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

- El template de ticket usa formato 80mm y dispara `window.print()` automaticamente.
- Para impresion sin dialogo en totem, configurar navegador en modo kiosco + politica de silent printing.
- Cada totem debe ejecutar con su propio `DEFAULT_TOTEM_ID` para trazabilidad de auditoria.

## CSS

- Todos los estilos quedaron centralizados en `static/style/style.css`.

## Despliegue nube (resumen)

- Ejecutar con `gunicorn config.wsgi:application` detras de Nginx o LB cloud.
- Configurar `DB_ENGINE=mysql` + credenciales gestionadas (RDS/Cloud SQL/Aurora).
- Correr `manage.py migrate` y `manage.py seed_vouchers` en cada release.
- Definir `DEFAULT_TOTEM_ID` distinto por totem.
- Habilitar TLS, HSTS y cookies seguras en produccion.
- Monitorear errores y auditoria en tabla `core_ticket`.
