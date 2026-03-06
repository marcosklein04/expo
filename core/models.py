from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint
from django.utils import timezone


class Empresa(models.Model):
    codigo = models.CharField(max_length=30, unique=True, db_index=True)
    nombre = models.CharField(max_length=120)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["codigo"]

    def __str__(self) -> str:
        return f"{self.codigo} - {self.nombre}"


class Totem(models.Model):
    codigo = models.CharField(max_length=50, unique=True, db_index=True)
    nombre = models.CharField(max_length=120, blank=True, default="")
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="totems",
    )
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["codigo"]

    def __str__(self) -> str:
        return f"{self.codigo} ({self.empresa.codigo})"


class Persona(models.Model):
    VIANDA_CLASICO = "CLASICO"
    VIANDA_VEGETARIANO = "VEGETARIANO"
    VIANDA_CELIACO = "CELIACO"
    VIANDA_CHOICES = [
        (VIANDA_CLASICO, "Clasico"),
        (VIANDA_VEGETARIANO, "Vegetariano"),
        (VIANDA_CELIACO, "Celiaco"),
    ]

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="personas",
    )
    dni = models.CharField(max_length=12, db_index=True)
    nombre_apellido = models.CharField(max_length=120)
    concesionario = models.CharField(max_length=120, blank=True, default="")
    credencial = models.CharField(max_length=50, blank=True, default="")
    tipo_vianda = models.CharField(
        max_length=12,
        choices=VIANDA_CHOICES,
        default=VIANDA_CLASICO,
    )
    puede_invitar = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["empresa_id", "dni"]
        constraints = [
            UniqueConstraint(fields=["empresa", "dni"], name="uq_persona_empresa_dni"),
        ]
        indexes = [
            models.Index(fields=["empresa", "dni"], name="idx_persona_empresa_dni"),
        ]

    def __str__(self) -> str:
        return f"{self.empresa.codigo} {self.dni} - {self.nombre_apellido}"


class VoucherTipo(models.Model):
    DESAYUNO = "DESAYUNO"
    ALMUERZO = "ALMUERZO"
    INVITADO = "INVITADO"
    INVITADO_DESAYUNO = "INVITADO_DESAYUNO"
    INVITADO_ALMUERZO = "INVITADO_ALMUERZO"

    CODIGOS = [
        (DESAYUNO, "Desayuno"),
        (ALMUERZO, "Almuerzo"),
        (INVITADO, "Invitado"),
        (INVITADO_DESAYUNO, "Invitado desayuno"),
        (INVITADO_ALMUERZO, "Invitado almuerzo"),
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


class CanjeOperacion(models.Model):
    persona = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name="operaciones_canje",
    )
    dia = models.DateField()
    totem_id = models.CharField(max_length=50)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["dia", "totem_id"], name="idx_canje_dia_totem"),
            models.Index(fields=["persona", "creado_en"], name="idx_canje_persona_fecha"),
        ]

    def __str__(self) -> str:
        return f"Canje #{self.id} {self.persona.dni} {self.dia} {self.totem_id}"


class CanjeOperacionItem(models.Model):
    COMIDAS = [
        (VoucherTipo.DESAYUNO, "Desayuno"),
        (VoucherTipo.ALMUERZO, "Almuerzo"),
    ]

    operacion = models.ForeignKey(
        CanjeOperacion,
        on_delete=models.CASCADE,
        related_name="items",
    )
    comida_codigo = models.CharField(max_length=20, choices=COMIDAS)
    canjear_propio = models.BooleanField(default=False)
    cantidad_invitados = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["id"]
        constraints = [
            UniqueConstraint(
                fields=["operacion", "comida_codigo"],
                name="uq_canje_item_operacion_comida",
            ),
            CheckConstraint(
                condition=Q(cantidad_invitados__gte=0),
                name="ck_canje_item_invitados_gte_0",
            ),
            CheckConstraint(
                condition=Q(canjear_propio=True) | Q(cantidad_invitados__gte=1),
                name="ck_canje_item_propio_o_invitado",
            ),
        ]
        indexes = [
            models.Index(fields=["comida_codigo"], name="idx_canje_item_comida"),
        ]

    def __str__(self) -> str:
        return (
            f"CanjeItem op={self.operacion_id} comida={self.comida_codigo} "
            f"propio={self.canjear_propio} invitados={self.cantidad_invitados}"
        )


class Ticket(models.Model):
    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name="tickets")
    voucher_tipo = models.ForeignKey(
        VoucherTipo, on_delete=models.PROTECT, related_name="tickets"
    )
    operacion = models.ForeignKey(
        CanjeOperacion,
        on_delete=models.PROTECT,
        related_name="tickets",
        null=True,
        blank=True,
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


class PoolDiario(models.Model):
    CODIGOS = [
        (VoucherTipo.DESAYUNO, "Pool fijos desayuno"),
        (VoucherTipo.ALMUERZO, "Pool fijos almuerzo"),
        (VoucherTipo.INVITADO_DESAYUNO, "Pool invitados desayuno"),
        (VoucherTipo.INVITADO_ALMUERZO, "Pool invitados almuerzo"),
    ]

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="pools_diarios",
    )
    codigo = models.CharField(max_length=24, choices=CODIGOS)
    dia = models.DateField()
    stock_total = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    usados = models.PositiveIntegerField(default=0)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-dia", "empresa_id", "codigo"]
        constraints = [
            UniqueConstraint(
                fields=["empresa", "dia", "codigo"],
                name="uq_pool_diario_empresa_dia_codigo",
            ),
            CheckConstraint(condition=Q(stock_total__gte=1), name="ck_pool_diario_stock_gte_1"),
            CheckConstraint(condition=Q(usados__gte=0), name="ck_pool_diario_usados_gte_0"),
        ]
        indexes = [
            models.Index(fields=["empresa", "dia", "codigo"], name="idx_pool_diario_emp_dia_codigo"),
        ]

    def __str__(self) -> str:
        return f"{self.empresa.codigo} {self.codigo} {self.dia} {self.usados}/{self.stock_total}"
