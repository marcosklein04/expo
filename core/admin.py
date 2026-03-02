from django.contrib import admin

from core.models import CupoDiario, Persona, Ticket, VoucherTipo


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    list_display = ("dni", "nombre_apellido", "concesionario", "credencial", "activo")
    list_filter = ("activo", "concesionario")
    search_fields = ("dni", "nombre_apellido", "credencial")


@admin.register(VoucherTipo)
class VoucherTipoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "cupo_por_dia", "actualizado_en")
    search_fields = ("codigo",)


@admin.register(CupoDiario)
class CupoDiarioAdmin(admin.ModelAdmin):
    list_display = ("dia", "persona", "voucher_tipo", "usados", "actualizado_en")
    list_filter = ("dia", "voucher_tipo")
    search_fields = ("persona__dni", "persona__nombre_apellido")


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = (
        "ticket_numero",
        "dia",
        "persona",
        "voucher_tipo",
        "totem_id",
        "creado_en",
    )
    list_filter = ("dia", "voucher_tipo", "totem_id")
    search_fields = ("ticket_numero", "persona__dni", "persona__nombre_apellido")
