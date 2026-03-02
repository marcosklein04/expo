from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint
from django.utils import timezone


class Persona(models.Model):
    dni = models.CharField(max_length=12, unique=True, db_index=True)
    nombre_apellido = models.CharField(max_length=120)
    concesionario = models.CharField(max_length=120, blank=True, default="")
    credencial = models.CharField(max_length=50, blank=True, default="")
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["dni"]

    def __str__(self) -> str:
        return f"{self.dni} - {self.nombre_apellido}"


class VoucherTipo(models.Model):
    DESAYUNO = "DESAYUNO"
    ALMUERZO = "ALMUERZO"
    INVITADO = "INVITADO"

    CODIGOS = [
        (DESAYUNO, "Desayuno"),
        (ALMUERZO, "Almuerzo"),
        (INVITADO, "Invitado"),
    ]

    codigo = models.CharField(max_length=20, choices=CODIGOS, unique=True)
    cupo_por_dia = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["codigo"]
        constraints = [
            CheckConstraint(
                condition=Q(cupo_por_dia__gte=1),
                name="ck_voucher_tipo_cupo_por_dia_gte_1",
            )
        ]

    def __str__(self) -> str:
        return f"{self.codigo} ({self.cupo_por_dia}/dia)"


class CupoDiario(models.Model):
    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name="cupos")
    voucher_tipo = models.ForeignKey(
        VoucherTipo, on_delete=models.PROTECT, related_name="cupos"
    )
    dia = models.DateField()
    usados = models.PositiveSmallIntegerField(default=0)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-dia", "persona_id", "voucher_tipo_id"]
        constraints = [
            UniqueConstraint(
                fields=["persona", "voucher_tipo", "dia"], name="uq_cupo_por_dia"
            ),
            CheckConstraint(condition=Q(usados__gte=0), name="ck_cupo_diario_usados_gte_0"),
        ]
        indexes = [
            models.Index(fields=["dia", "voucher_tipo"], name="idx_cupo_dia_voucher"),
        ]

    def __str__(self) -> str:
        return f"{self.persona.dni} {self.voucher_tipo.codigo} {self.dia} {self.usados}"


class Ticket(models.Model):
    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name="tickets")
    voucher_tipo = models.ForeignKey(
        VoucherTipo, on_delete=models.PROTECT, related_name="tickets"
    )
    dia = models.DateField()
    creado_en = models.DateTimeField(default=timezone.now)
    totem_id = models.CharField(max_length=50)
    ticket_numero = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["dia", "voucher_tipo"], name="idx_ticket_dia_voucher"),
            models.Index(fields=["totem_id", "creado_en"], name="idx_ticket_totem_fecha"),
        ]

    def __str__(self) -> str:
        return self.ticket_numero
