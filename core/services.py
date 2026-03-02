from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import CupoDiario, Persona, Ticket, VoucherTipo


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

    with transaction.atomic():
        persona = _get_persona(normalized_dni, lock=True)
        voucher_tipo = _get_voucher_tipo(voucher_codigo)
        cupo = _get_or_create_cupo_diario_lock(
            persona=persona,
            voucher_tipo=voucher_tipo,
            dia=dia,
        )

        if cupo.usados >= voucher_tipo.cupo_por_dia:
            raise CupoAgotadoError(
                f"Cupo diario agotado para {voucher_tipo.codigo}.",
                details={
                    "codigo": voucher_tipo.codigo,
                    "cupo_por_dia": voucher_tipo.cupo_por_dia,
                    "usados": cupo.usados,
                },
            )

        cupo.usados += 1
        cupo.save(update_fields=["usados", "actualizado_en"])

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

    return ticket
