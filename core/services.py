from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone

from core.models import CupoDiario, Persona, Ticket, VoucherTipo

audit_logger = logging.getLogger("kiosk.audit")


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


@dataclass(frozen=True)
class VoucherEstado:
    codigo: str
    etiqueta: str
    cupo_por_dia: int
    usados: int

    @property
    def disponibles(self) -> int:
        restante = self.cupo_por_dia - self.usados
        return restante if restante > 0 else 0

    @property
    def agotado(self) -> bool:
        return self.disponibles == 0


def _hoy() -> date:
    return timezone.localdate()


def normalizar_dni(raw_dni: str) -> str:
    if not raw_dni:
        return ""
    value = "".join(ch for ch in str(raw_dni).strip() if ch.isdigit())
    return value


def _get_persona(dni: str, lock: bool = False) -> Persona:
    query = Persona.objects.filter(dni=dni, activo=True)
    if lock:
        query = query.select_for_update()
    persona = query.first()
    if not persona:
        raise PersonaNoEncontradaError("No existe una persona activa con ese DNI.")
    return persona


def _get_voucher_tipo(codigo: str) -> VoucherTipo:
    voucher_tipo = VoucherTipo.objects.filter(codigo=codigo).first()
    if not voucher_tipo:
        raise VoucherInvalidoError("El tipo de voucher solicitado no existe.")
    return voucher_tipo


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


def _voucher_estados_para_dia(*, persona: Persona, dia: date) -> list[VoucherEstado]:
    vouchers = {v.codigo: v for v in VoucherTipo.objects.all()}
    cupos = {
        cupo.voucher_tipo.codigo: cupo.usados
        for cupo in CupoDiario.objects.filter(persona=persona, dia=dia).select_related(
            "voucher_tipo"
        )
    }

    estados: list[VoucherEstado] = []
    for codigo, etiqueta in VoucherTipo.CODIGOS:
        voucher = vouchers.get(codigo)
        if not voucher:
            continue
        estados.append(
            VoucherEstado(
                codigo=codigo,
                etiqueta=etiqueta,
                cupo_por_dia=voucher.cupo_por_dia,
                usados=cupos.get(codigo, 0),
            )
        )
    return estados


def lookup_persona_cupos(*, dni: str, dia: date | None = None) -> dict[str, Any]:
    normalized_dni = normalizar_dni(dni)
    if not normalized_dni:
        raise PersonaNoEncontradaError("Debe ingresar un DNI valido.")

    dia = dia or _hoy()
    persona = _get_persona(normalized_dni, lock=False)
    estados = _voucher_estados_para_dia(persona=persona, dia=dia)

    return {
        "dia": dia.isoformat(),
        "persona": {
            "dni": persona.dni,
            "nombre_apellido": persona.nombre_apellido,
            "concesionario": persona.concesionario,
            "credencial": persona.credencial,
        },
        "vouchers": [
            {
                "codigo": e.codigo,
                "etiqueta": e.etiqueta,
                "cupo_por_dia": e.cupo_por_dia,
                "usados": e.usados,
                "disponibles": e.disponibles,
                "agotado": e.agotado,
            }
            for e in estados
        ],
    }


def _build_ticket_number(*, dia: date, voucher_codigo: str, totem_id: str) -> str:
    random_suffix = uuid4().hex[:10].upper()
    voucher_short = voucher_codigo[:3]
    totem_short = "".join(ch for ch in totem_id.upper() if ch.isalnum())[:6] or "TOTEM"
    return f"{dia:%Y%m%d}-{voucher_short}-{totem_short}-{random_suffix}"


def _create_ticket_with_retries(
    *, persona: Persona, voucher_tipo: VoucherTipo, dia: date, totem_id: str
) -> Ticket:
    ticket: Ticket | None = None
    for _ in range(3):
        try:
            ticket = Ticket.objects.create(
                persona=persona,
                voucher_tipo=voucher_tipo,
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


def _redeem_locked(
    *,
    persona: Persona,
    voucher_tipo: VoucherTipo,
    totem_id: str,
    dia: date,
    cantidad: int,
) -> list[Ticket]:
    if cantidad < 1:
        raise CantidadInvalidaError("La cantidad debe ser mayor o igual a 1.")

    cupo = _get_or_create_cupo_diario_lock(
        persona=persona,
        voucher_tipo=voucher_tipo,
        dia=dia,
    )

    disponibles = voucher_tipo.cupo_por_dia - cupo.usados
    if disponibles < cantidad:
        raise CupoAgotadoError(
            f"Cupo diario agotado para {voucher_tipo.codigo}.",
            details={
                "codigo": voucher_tipo.codigo,
                "cupo_por_dia": voucher_tipo.cupo_por_dia,
                "usados": cupo.usados,
                "disponibles": max(disponibles, 0),
                "solicitados": cantidad,
            },
        )

    cupo.usados += cantidad
    cupo.save(update_fields=["usados", "actualizado_en"])

    return [
        _create_ticket_with_retries(
            persona=persona,
            voucher_tipo=voucher_tipo,
            dia=dia,
            totem_id=totem_id,
        )
        for _ in range(cantidad)
    ]


def redeem_voucher(
    *,
    dni: str,
    voucher_codigo: str,
    totem_id: str,
    dia: date | None = None,
) -> Ticket:
    normalized_dni = normalizar_dni(dni)
    if not normalized_dni:
        raise PersonaNoEncontradaError("Debe ingresar un DNI valido.")

    dia = dia or _hoy()
    voucher_codigo = voucher_codigo.upper().strip()

    with transaction.atomic():
        persona = _get_persona(normalized_dni, lock=True)
        voucher_tipo = _get_voucher_tipo(voucher_codigo)
        tickets = _redeem_locked(
            persona=persona,
            voucher_tipo=voucher_tipo,
            totem_id=totem_id,
            dia=dia,
            cantidad=1,
        )

    return tickets[0]


def _parse_positive_int(value: Any, *, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise CantidadInvalidaError(
            f"El campo {field_name} debe ser numerico y mayor a cero."
        )
    if parsed < 1:
        raise CantidadInvalidaError(
            f"El campo {field_name} debe ser numerico y mayor a cero."
        )
    return parsed


def normalizar_redeem_batch_items(items: list[dict[str, Any]]) -> list[tuple[str, int]]:
    if not items:
        raise CantidadInvalidaError("Debe enviar al menos un voucher para canjear.")

    acumulado: dict[str, int] = {}
    for raw in items:
        voucher_codigo = str(raw.get("voucher") or raw.get("codigo") or "").upper().strip()
        if not voucher_codigo:
            raise VoucherInvalidoError("Cada item debe incluir el codigo de voucher.")

        cantidad = _parse_positive_int(raw.get("cantidad", 1), field_name="cantidad")
        acumulado[voucher_codigo] = acumulado.get(voucher_codigo, 0) + cantidad

    ordered_codes = [codigo for codigo, _ in VoucherTipo.CODIGOS if codigo in acumulado]
    ordered_codes += [codigo for codigo in acumulado if codigo not in ordered_codes]
    return [(codigo, acumulado[codigo]) for codigo in ordered_codes]


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
    requested_codes = [codigo for codigo, _ in normalized_items]
    voucher_map = {
        voucher.codigo: voucher
        for voucher in VoucherTipo.objects.filter(codigo__in=requested_codes)
    }

    missing_codes = [code for code in requested_codes if code not in voucher_map]
    if missing_codes:
        raise VoucherInvalidoError(
            "Uno o mas vouchers no existen.",
            details={"codigos_invalidos": missing_codes},
        )

    with transaction.atomic():
        persona = _get_persona(normalized_dni, lock=True)
        tickets: list[Ticket] = []
        for codigo, cantidad in normalized_items:
            tickets.extend(
                _redeem_locked(
                    persona=persona,
                    voucher_tipo=voucher_map[codigo],
                    totem_id=totem_id,
                    dia=dia,
                    cantidad=cantidad,
                )
            )

    audit_logger.info(
        "batch_redeem_completed dni=%s dia=%s totem=%s cantidad_tickets=%s",
        normalized_dni,
        dia.isoformat(),
        totem_id,
        len(tickets),
    )
    return tickets


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
        base_qs.filter(voucher_tipo__codigo=VoucherTipo.INVITADO)
        .values("persona__dni", "persona__nombre_apellido")
        .annotate(total=Count("id"))
        .order_by("-total", "persona__dni")[:10]
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
        "generado_en": timezone.now().isoformat(),
    }

