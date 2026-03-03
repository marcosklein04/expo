from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone

from core.models import (
    CanjeOperacion,
    CanjeOperacionItem,
    CupoDiario,
    Persona,
    PoolDiario,
    Ticket,
    VoucherTipo,
)

audit_logger = logging.getLogger("kiosk.audit")

COMIDAS = (VoucherTipo.DESAYUNO, VoucherTipo.ALMUERZO)
INVITADO_POR_COMIDA = {
    VoucherTipo.DESAYUNO: VoucherTipo.INVITADO_DESAYUNO,
    VoucherTipo.ALMUERZO: VoucherTipo.INVITADO_ALMUERZO,
}


class DomainError(Exception):
    code = "domain_error"
    http_status = 400

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class PersonaNoEncontradaError(DomainError):
    code = "persona_not_found"
    http_status = 404


class VoucherInvalidoError(DomainError):
    code = "invalid_voucher"
    http_status = 400


class CantidadInvalidaError(DomainError):
    code = "invalid_quantity"
    http_status = 400


class CupoAgotadoError(DomainError):
    code = "quota_exhausted"
    http_status = 409


class StockAgotadoError(DomainError):
    code = "stock_exhausted"
    http_status = 409


@dataclass(frozen=True)
class ComidaEstado:
    codigo: str
    etiqueta: str
    cupo_fijos_persona: int
    usados_fijos_persona: int
    cupo_invitados_persona: int
    usados_invitados_persona: int
    stock_fijos_total: int
    stock_fijos_usados: int
    stock_invitados_total: int
    stock_invitados_usados: int

    @property
    def disponibles_fijos_persona(self) -> int:
        return max(self.cupo_fijos_persona - self.usados_fijos_persona, 0)

    @property
    def disponibles_invitados_persona(self) -> int:
        return max(self.cupo_invitados_persona - self.usados_invitados_persona, 0)

    @property
    def stock_fijos_disponible(self) -> int:
        return max(self.stock_fijos_total - self.stock_fijos_usados, 0)

    @property
    def stock_invitados_disponible(self) -> int:
        return max(self.stock_invitados_total - self.stock_invitados_usados, 0)


def _hoy() -> date:
    return timezone.localdate()


def normalizar_dni(raw_dni: str) -> str:
    if not raw_dni:
        return ""
    return "".join(ch for ch in str(raw_dni).strip() if ch.isdigit())


def _pool_default_stock(codigo: str) -> int:
    default_by_codigo = {
        VoucherTipo.DESAYUNO: settings.POOL_STOCK_FIJOS_DESAYUNO,
        VoucherTipo.ALMUERZO: settings.POOL_STOCK_FIJOS_ALMUERZO,
        VoucherTipo.INVITADO_DESAYUNO: settings.POOL_STOCK_INVITADOS_DESAYUNO,
        VoucherTipo.INVITADO_ALMUERZO: settings.POOL_STOCK_INVITADOS_ALMUERZO,
    }
    if codigo not in default_by_codigo:
        raise VoucherInvalidoError("No existe configuracion de pool para ese codigo.")
    return int(default_by_codigo[codigo])


def _parse_non_negative_int(value: Any, *, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise CantidadInvalidaError(
            f"El campo {field_name} debe ser numerico y mayor o igual a cero."
        )
    if parsed < 0:
        raise CantidadInvalidaError(
            f"El campo {field_name} debe ser numerico y mayor o igual a cero."
        )
    return parsed


def _parse_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        raise CantidadInvalidaError(
            f"El campo {field_name} debe ser booleano (true/false)."
        )
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "si", "sí", "yes", "on"}:
            return True
        if normalized in {"0", "false", "f", "no", "off"}:
            return False
    raise CantidadInvalidaError(
        f"El campo {field_name} debe ser booleano (true/false)."
    )


def _get_persona(dni: str, lock: bool = False) -> Persona:
    query = Persona.objects.filter(dni=dni, activo=True)
    if lock:
        query = query.select_for_update()
    persona = query.first()
    if not persona:
        raise PersonaNoEncontradaError("No existe una persona activa con ese DNI.")
    return persona


def _required_voucher_codes() -> list[str]:
    return [
        VoucherTipo.DESAYUNO,
        VoucherTipo.ALMUERZO,
        VoucherTipo.INVITADO_DESAYUNO,
        VoucherTipo.INVITADO_ALMUERZO,
    ]


def _load_required_vouchers() -> dict[str, VoucherTipo]:
    required_codes = _required_voucher_codes()
    voucher_map = {
        voucher.codigo: voucher
        for voucher in VoucherTipo.objects.filter(codigo__in=required_codes)
    }
    missing = [codigo for codigo in required_codes if codigo not in voucher_map]
    if missing:
        raise VoucherInvalidoError(
            "Faltan vouchers configurados. Ejecutar seed_vouchers.",
            details={"faltantes": missing},
        )
    return voucher_map


def _get_or_create_cupo_diario_lock(
    *, persona: Persona, voucher_tipo: VoucherTipo, dia: date
) -> CupoDiario:
    try:
        return CupoDiario.objects.select_for_update().get(
            persona=persona,
            voucher_tipo=voucher_tipo,
            dia=dia,
        )
    except CupoDiario.DoesNotExist:
        try:
            CupoDiario.objects.create(
                persona=persona,
                voucher_tipo=voucher_tipo,
                dia=dia,
                usados=0,
            )
        except IntegrityError:
            # Another concurrent transaction created the row first.
            pass
        return CupoDiario.objects.select_for_update().get(
            persona=persona,
            voucher_tipo=voucher_tipo,
            dia=dia,
        )


def _get_or_create_pool_diario_lock(*, codigo: str, dia: date) -> PoolDiario:
    try:
        return PoolDiario.objects.select_for_update().get(
            codigo=codigo,
            dia=dia,
        )
    except PoolDiario.DoesNotExist:
        try:
            PoolDiario.objects.create(
                codigo=codigo,
                dia=dia,
                stock_total=_pool_default_stock(codigo),
                usados=0,
            )
        except IntegrityError:
            pass
        return PoolDiario.objects.select_for_update().get(
            codigo=codigo,
            dia=dia,
        )


def _build_ticket_number(*, dia: date, voucher_codigo: str, totem_id: str) -> str:
    random_suffix = uuid4().hex[:10].upper()
    voucher_short = voucher_codigo[:3]
    totem_short = "".join(ch for ch in totem_id.upper() if ch.isalnum())[:6] or "TOTEM"
    return f"{dia:%Y%m%d}-{voucher_short}-{totem_short}-{random_suffix}"


def _create_ticket_with_retries(
    *,
    persona: Persona,
    voucher_tipo: VoucherTipo,
    operacion: CanjeOperacion | None,
    dia: date,
    totem_id: str,
) -> Ticket:
    ticket: Ticket | None = None
    for _ in range(3):
        try:
            ticket = Ticket.objects.create(
                persona=persona,
                voucher_tipo=voucher_tipo,
                operacion=operacion,
                dia=dia,
                totem_id=totem_id,
                ticket_numero=_build_ticket_number(
                    dia=dia,
                    voucher_codigo=voucher_tipo.codigo,
                    totem_id=totem_id,
                ),
            )
            break
        except IntegrityError:
            continue

    if ticket is None:
        raise DomainError("No se pudo generar un ticket unico. Reintente.")

    audit_logger.info(
        "ticket_created ticket=%s dni=%s voucher=%s dia=%s totem=%s",
        ticket.ticket_numero,
        persona.dni,
        voucher_tipo.codigo,
        dia.isoformat(),
        totem_id,
    )
    return ticket


def _build_comidas_estado(*, persona: Persona, dia: date) -> list[ComidaEstado]:
    vouchers = _load_required_vouchers()
    cupos = {
        cupo.voucher_tipo.codigo: cupo.usados
        for cupo in CupoDiario.objects.filter(
            persona=persona,
            dia=dia,
            voucher_tipo__codigo__in=_required_voucher_codes(),
        ).select_related("voucher_tipo")
    }
    pools = {
        pool.codigo: pool
        for pool in PoolDiario.objects.filter(
            dia=dia,
            codigo__in=_required_voucher_codes(),
        )
    }
    labels = dict(VoucherTipo.CODIGOS)

    estados: list[ComidaEstado] = []
    for comida_codigo in COMIDAS:
        invitado_codigo = INVITADO_POR_COMIDA[comida_codigo]
        comida_pool = pools.get(comida_codigo)
        invitados_pool = pools.get(invitado_codigo)

        estados.append(
            ComidaEstado(
                codigo=comida_codigo,
                etiqueta=labels.get(comida_codigo, comida_codigo.title()),
                cupo_fijos_persona=vouchers[comida_codigo].cupo_por_dia,
                usados_fijos_persona=cupos.get(comida_codigo, 0),
                cupo_invitados_persona=vouchers[invitado_codigo].cupo_por_dia,
                usados_invitados_persona=cupos.get(invitado_codigo, 0),
                stock_fijos_total=(
                    comida_pool.stock_total
                    if comida_pool
                    else _pool_default_stock(comida_codigo)
                ),
                stock_fijos_usados=comida_pool.usados if comida_pool else 0,
                stock_invitados_total=(
                    invitados_pool.stock_total
                    if invitados_pool
                    else _pool_default_stock(invitado_codigo)
                ),
                stock_invitados_usados=invitados_pool.usados if invitados_pool else 0,
            )
        )
    return estados


def lookup_persona_cupos(*, dni: str, dia: date | None = None) -> dict[str, Any]:
    normalized_dni = normalizar_dni(dni)
    if not normalized_dni:
        raise PersonaNoEncontradaError("Debe ingresar un DNI valido.")

    dia = dia or _hoy()
    persona = _get_persona(normalized_dni, lock=False)
    comidas = _build_comidas_estado(persona=persona, dia=dia)

    comidas_payload = [
        {
            "codigo": comida.codigo,
            "etiqueta": comida.etiqueta,
            "fijos": {
                "cupo_persona": comida.cupo_fijos_persona,
                "usados_persona": comida.usados_fijos_persona,
                "disponibles_persona": comida.disponibles_fijos_persona,
                "agotado_persona": comida.disponibles_fijos_persona == 0,
                "stock_total": comida.stock_fijos_total,
                "stock_usados": comida.stock_fijos_usados,
                "stock_disponible": comida.stock_fijos_disponible,
                "stock_agotado": comida.stock_fijos_disponible == 0,
            },
            "invitados": {
                "cupo_persona": comida.cupo_invitados_persona,
                "usados_persona": comida.usados_invitados_persona,
                "disponibles_persona": comida.disponibles_invitados_persona,
                "agotado_persona": comida.disponibles_invitados_persona == 0,
                "stock_total": comida.stock_invitados_total,
                "stock_usados": comida.stock_invitados_usados,
                "stock_disponible": comida.stock_invitados_disponible,
                "stock_agotado": comida.stock_invitados_disponible == 0,
            },
        }
        for comida in comidas
    ]

    # Compatibilidad hacia atras para clientes que consumen el campo `vouchers`.
    vouchers_legacy = [
        {
            "codigo": comida.codigo,
            "etiqueta": comida.etiqueta,
            "cupo_por_dia": comida.cupo_fijos_persona,
            "usados": comida.usados_fijos_persona,
            "disponibles": comida.disponibles_fijos_persona,
            "agotado": comida.disponibles_fijos_persona == 0,
        }
        for comida in comidas
    ]

    return {
        "dia": dia.isoformat(),
        "persona": {
            "dni": persona.dni,
            "nombre_apellido": persona.nombre_apellido,
            "concesionario": persona.concesionario,
            "credencial": persona.credencial,
        },
        "comidas": comidas_payload,
        "vouchers": vouchers_legacy,
    }


def normalizar_redeem_batch_items(
    items: list[dict[str, Any]],
) -> list[tuple[str, bool, int]]:
    if not items:
        raise CantidadInvalidaError("Debe enviar al menos una comida para canjear.")

    acumulado: dict[str, dict[str, Any]] = {}
    for raw in items:
        comida_codigo = str(
            raw.get("comida") or raw.get("voucher") or raw.get("codigo") or ""
        ).upper().strip()
        if comida_codigo not in COMIDAS:
            raise VoucherInvalidoError(
                "Solo se permiten DESAYUNO y ALMUERZO en este flujo.",
                details={"codigo": comida_codigo},
            )

        if "canjear_propio" in raw:
            canjear_propio = _parse_bool(
                raw.get("canjear_propio"),
                field_name="canjear_propio",
            )
            if "cantidad" in raw:
                cantidad = _parse_non_negative_int(
                    raw.get("cantidad"), field_name="cantidad"
                )
                if cantidad not in (0, 1):
                    raise CantidadInvalidaError(
                        "Para cada comida, la cantidad fija debe ser 0 o 1."
                    )
                if bool(cantidad) != canjear_propio:
                    raise CantidadInvalidaError(
                        "cantidad y canjear_propio no son consistentes."
                    )
        else:
            cantidad = _parse_non_negative_int(
                raw.get("cantidad", 1), field_name="cantidad"
            )
            if cantidad not in (0, 1):
                raise CantidadInvalidaError(
                    "Para cada comida, la cantidad fija debe ser 0 o 1."
                )
            canjear_propio = cantidad == 1

        invitados = _parse_non_negative_int(
            raw.get("invitados", 0), field_name="invitados"
        )
        if not canjear_propio and invitados == 0:
            raise CantidadInvalidaError(
                "Para cada comida debe canjear el voucher propio o sumar invitados."
            )

        if comida_codigo not in acumulado:
            acumulado[comida_codigo] = {
                "canjear_propio": False,
                "invitados": 0,
            }
        acumulado[comida_codigo]["canjear_propio"] = (
            acumulado[comida_codigo]["canjear_propio"] or canjear_propio
        )
        acumulado[comida_codigo]["invitados"] += invitados

    normalized = [
        (
            codigo,
            bool(acumulado[codigo]["canjear_propio"]),
            int(acumulado[codigo]["invitados"]),
        )
        for codigo in COMIDAS
        if codigo in acumulado
    ]
    if not normalized:
        raise CantidadInvalidaError("Debe seleccionar al menos una comida o invitado.")

    return normalized


def _redeem_comida_locked(
    *,
    persona: Persona,
    comida_codigo: str,
    canjear_propio: bool,
    invitados: int,
    voucher_map: dict[str, VoucherTipo],
    operacion: CanjeOperacion,
    totem_id: str,
    dia: date,
) -> list[Ticket]:
    invitado_codigo = INVITADO_POR_COMIDA[comida_codigo]
    voucher_fijo = voucher_map[comida_codigo]
    voucher_invitado = voucher_map[invitado_codigo]

    if not canjear_propio and invitados == 0:
        raise CantidadInvalidaError(
            "Debe canjear el voucher propio o emitir al menos un invitado."
        )

    cupo_fijo: CupoDiario | None = None
    pool_fijo: PoolDiario | None = None
    if canjear_propio:
        cupo_fijo = _get_or_create_cupo_diario_lock(
            persona=persona,
            voucher_tipo=voucher_fijo,
            dia=dia,
        )
        if cupo_fijo.usados >= voucher_fijo.cupo_por_dia:
            raise CupoAgotadoError(
                f"Cupo diario agotado para {comida_codigo}.",
                details={
                    "tipo": "fijos_persona",
                    "codigo": comida_codigo,
                    "cupo_por_dia": voucher_fijo.cupo_por_dia,
                    "usados": cupo_fijo.usados,
                },
            )

        pool_fijo = _get_or_create_pool_diario_lock(codigo=comida_codigo, dia=dia)
        if pool_fijo.usados + 1 > pool_fijo.stock_total:
            raise StockAgotadoError(
                f"Stock agotado para {comida_codigo}.",
                details={
                    "tipo": "pool_fijos",
                    "codigo": comida_codigo,
                    "stock_total": pool_fijo.stock_total,
                    "usados": pool_fijo.usados,
                    "solicitados": 1,
                },
            )

    cupo_invitado: CupoDiario | None = None
    pool_invitado: PoolDiario | None = None
    if invitados > 0:
        cupo_invitado = _get_or_create_cupo_diario_lock(
            persona=persona,
            voucher_tipo=voucher_invitado,
            dia=dia,
        )
        invitados_persona_disponibles = voucher_invitado.cupo_por_dia - cupo_invitado.usados
        if invitados > invitados_persona_disponibles:
            raise CupoAgotadoError(
                f"Cupo de invitados agotado para {comida_codigo}.",
                details={
                    "tipo": "invitados_persona",
                    "codigo": comida_codigo,
                    "cupo_por_dia": voucher_invitado.cupo_por_dia,
                    "usados": cupo_invitado.usados,
                    "solicitados": invitados,
                    "disponibles": max(invitados_persona_disponibles, 0),
                },
            )

        pool_invitado = _get_or_create_pool_diario_lock(codigo=invitado_codigo, dia=dia)
        if pool_invitado.usados + invitados > pool_invitado.stock_total:
            raise StockAgotadoError(
                f"Stock de invitados agotado para {comida_codigo}.",
                details={
                    "tipo": "pool_invitados",
                    "codigo": comida_codigo,
                    "stock_total": pool_invitado.stock_total,
                    "usados": pool_invitado.usados,
                    "solicitados": invitados,
                    "disponibles": max(pool_invitado.stock_total - pool_invitado.usados, 0),
                },
            )

    tickets: list[Ticket] = []
    if canjear_propio and cupo_fijo and pool_fijo:
        cupo_fijo.usados += 1
        cupo_fijo.save(update_fields=["usados", "actualizado_en"])

        pool_fijo.usados += 1
        pool_fijo.save(update_fields=["usados", "actualizado_en"])

        tickets.append(
            _create_ticket_with_retries(
                persona=persona,
                voucher_tipo=voucher_fijo,
                operacion=operacion,
                dia=dia,
                totem_id=totem_id,
            )
        )

    if invitados > 0 and cupo_invitado and pool_invitado:
        cupo_invitado.usados += invitados
        cupo_invitado.save(update_fields=["usados", "actualizado_en"])

        pool_invitado.usados += invitados
        pool_invitado.save(update_fields=["usados", "actualizado_en"])

        for _ in range(invitados):
            tickets.append(
                _create_ticket_with_retries(
                    persona=persona,
                    voucher_tipo=voucher_invitado,
                    operacion=operacion,
                    dia=dia,
                    totem_id=totem_id,
                )
            )

    return tickets


def redeem_vouchers_batch(
    *,
    dni: str,
    items: list[dict[str, Any]],
    totem_id: str,
    dia: date | None = None,
) -> list[Ticket]:
    normalized_dni = normalizar_dni(dni)
    if not normalized_dni:
        raise PersonaNoEncontradaError("Debe ingresar un DNI valido.")

    dia = dia or _hoy()
    normalized_items = normalizar_redeem_batch_items(items)
    if not normalized_items:
        raise CantidadInvalidaError("Debe seleccionar al menos una comida.")

    voucher_map = _load_required_vouchers()

    with transaction.atomic():
        persona = _get_persona(normalized_dni, lock=True)
        operacion = CanjeOperacion.objects.create(
            persona=persona,
            dia=dia,
            totem_id=totem_id,
        )
        tickets: list[Ticket] = []
        for comida_codigo, canjear_propio, invitados in normalized_items:
            CanjeOperacionItem.objects.create(
                operacion=operacion,
                comida_codigo=comida_codigo,
                canjear_propio=canjear_propio,
                cantidad_invitados=invitados,
            )
            tickets.extend(
                _redeem_comida_locked(
                    persona=persona,
                    comida_codigo=comida_codigo,
                    canjear_propio=canjear_propio,
                    invitados=invitados,
                    voucher_map=voucher_map,
                    operacion=operacion,
                    totem_id=totem_id,
                    dia=dia,
                )
            )

    audit_logger.info(
        "batch_redeem_completed operacion_id=%s dni=%s dia=%s totem=%s cantidad_tickets=%s",
        operacion.id,
        normalized_dni,
        dia.isoformat(),
        totem_id,
        len(tickets),
    )
    return tickets


def redeem_voucher(
    *,
    dni: str,
    voucher_codigo: str,
    totem_id: str,
    dia: date | None = None,
) -> Ticket:
    voucher_codigo = str(voucher_codigo).upper().strip()
    if voucher_codigo not in COMIDAS:
        raise VoucherInvalidoError(
            "En este flujo solo se permite canjear DESAYUNO o ALMUERZO."
        )

    tickets = redeem_vouchers_batch(
        dni=dni,
        items=[{"comida": voucher_codigo, "canjear_propio": True, "invitados": 0}],
        totem_id=totem_id,
        dia=dia,
    )
    return tickets[0]


def reporte_tickets_diario(*, dia: date | None = None) -> dict[str, Any]:
    dia = dia or _hoy()
    base_qs = Ticket.objects.filter(dia=dia)

    by_voucher = list(
        base_qs.values("voucher_tipo__codigo")
        .annotate(total=Count("id"))
        .order_by("voucher_tipo__codigo")
    )
    by_totem = list(
        base_qs.values("totem_id")
        .annotate(total=Count("id"))
        .order_by("totem_id")
    )
    top_invitados = list(
        base_qs.filter(
            voucher_tipo__codigo__in=[
                VoucherTipo.INVITADO,
                VoucherTipo.INVITADO_DESAYUNO,
                VoucherTipo.INVITADO_ALMUERZO,
            ]
        )
        .values("persona__dni", "persona__nombre_apellido")
        .annotate(total=Count("id"))
        .order_by("-total", "persona__dni")[:10]
    )
    pools = list(
        PoolDiario.objects.filter(dia=dia)
        .values("codigo", "stock_total", "usados")
        .order_by("codigo")
    )

    return {
        "dia": dia.isoformat(),
        "total_tickets": base_qs.count(),
        "por_voucher": [
            {"voucher": row["voucher_tipo__codigo"], "total": row["total"]}
            for row in by_voucher
        ],
        "por_totem": [{"totem_id": row["totem_id"], "total": row["total"]} for row in by_totem],
        "top_invitados": [
            {
                "dni": row["persona__dni"],
                "nombre_apellido": row["persona__nombre_apellido"],
                "total": row["total"],
            }
            for row in top_invitados
        ],
        "pools": [
            {
                "codigo": row["codigo"],
                "stock_total": row["stock_total"],
                "usados": row["usados"],
                "disponible": max(row["stock_total"] - row["usados"], 0),
            }
            for row in pools
        ],
        "generado_en": timezone.now().isoformat(),
    }


def reporte_operaciones_canje(
    *,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    dni: str | None = None,
    totem_id: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    fecha_desde = fecha_desde or _hoy()
    fecha_hasta = fecha_hasta or fecha_desde

    if fecha_desde > fecha_hasta:
        raise DomainError("La fecha_desde no puede ser mayor a fecha_hasta.")
    if limit < 1 or limit > 5000:
        raise DomainError("El parametro limit debe estar entre 1 y 5000.")

    qs = (
        CanjeOperacion.objects.select_related("persona")
        .prefetch_related("items", "tickets__voucher_tipo")
        .filter(dia__gte=fecha_desde, dia__lte=fecha_hasta)
        .order_by("-creado_en", "-id")
    )

    normalized_dni = normalizar_dni(dni or "")
    if dni and not normalized_dni:
        raise DomainError("El filtro DNI es invalido.")
    if normalized_dni:
        qs = qs.filter(persona__dni=normalized_dni)

    cleaned_totem_id = str(totem_id or "").strip()
    if cleaned_totem_id:
        qs = qs.filter(totem_id=cleaned_totem_id)

    operaciones = list(qs[:limit])
    invitado_codes = {
        VoucherTipo.INVITADO,
        VoucherTipo.INVITADO_DESAYUNO,
        VoucherTipo.INVITADO_ALMUERZO,
    }

    payload_operaciones: list[dict[str, Any]] = []
    total_tickets = 0
    total_tickets_propios = 0
    total_tickets_invitados = 0

    for operacion in operaciones:
        items_payload = [
            {
                "comida": item.comida_codigo,
                "canjear_propio": item.canjear_propio,
                "cantidad_invitados": item.cantidad_invitados,
            }
            for item in operacion.items.all()
        ]

        by_voucher: dict[str, int] = {}
        tickets_propios = 0
        tickets_invitados = 0
        for ticket in operacion.tickets.all():
            codigo = ticket.voucher_tipo.codigo
            by_voucher[codigo] = by_voucher.get(codigo, 0) + 1
            if codigo in invitado_codes:
                tickets_invitados += 1
            else:
                tickets_propios += 1

        tickets_total = tickets_propios + tickets_invitados
        total_tickets += tickets_total
        total_tickets_propios += tickets_propios
        total_tickets_invitados += tickets_invitados

        payload_operaciones.append(
            {
                "operacion_id": operacion.id,
                "dia": operacion.dia.isoformat(),
                "creado_en": operacion.creado_en.isoformat(),
                "totem_id": operacion.totem_id,
                "persona": {
                    "dni": operacion.persona.dni,
                    "nombre_apellido": operacion.persona.nombre_apellido,
                    "concesionario": operacion.persona.concesionario,
                    "credencial": operacion.persona.credencial,
                },
                "items": items_payload,
                "tickets": {
                    "total": tickets_total,
                    "propios": tickets_propios,
                    "invitados": tickets_invitados,
                    "por_voucher": [
                        {"voucher": codigo, "total": by_voucher[codigo]}
                        for codigo in sorted(by_voucher.keys())
                    ],
                },
            }
        )

    return {
        "fecha_desde": fecha_desde.isoformat(),
        "fecha_hasta": fecha_hasta.isoformat(),
        "filtros": {
            "dni": normalized_dni or None,
            "totem_id": cleaned_totem_id or None,
            "limit": limit,
        },
        "total_operaciones": len(payload_operaciones),
        "total_tickets": total_tickets,
        "total_tickets_propios": total_tickets_propios,
        "total_tickets_invitados": total_tickets_invitados,
        "operaciones": payload_operaciones,
        "generado_en": timezone.now().isoformat(),
    }
