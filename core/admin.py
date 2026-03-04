import csv
from datetime import timedelta

from django.contrib import admin
from django.db.models import Count
from django.http import HttpResponse
from django.urls import path
from django.utils import timezone

from core.models import (
    CanjeOperacion,
    CanjeOperacionItem,
    CupoDiario,
    Empresa,
    Persona,
    PoolDiario,
    Ticket,
    Totem,
    VoucherTipo,
)


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "activo", "actualizado_en")
    list_filter = ("activo",)
    search_fields = ("codigo", "nombre")


@admin.register(Totem)
class TotemAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "empresa", "activo", "actualizado_en")
    list_filter = ("activo", "empresa")
    search_fields = ("codigo", "nombre", "empresa__codigo", "empresa__nombre")


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    list_display = ("empresa", "dni", "nombre_apellido", "concesionario", "credencial", "activo")
    list_filter = ("empresa", "activo", "concesionario")
    search_fields = ("empresa__codigo", "dni", "nombre_apellido", "credencial")


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
        "persona_empresa",
        "voucher_tipo",
        "operacion",
        "totem_id",
        "creado_en",
    )
    list_filter = ("dia", "voucher_tipo", "totem_id", "persona__empresa")
    search_fields = (
        "ticket_numero",
        "persona__dni",
        "persona__nombre_apellido",
        "persona__empresa__codigo",
    )
    change_list_template = "admin/core/ticket/change_list.html"
    actions = ["exportar_detalle_ultimos_3_dias_csv", "exportar_resumen_ultimos_3_dias_csv"]

    @admin.display(description="Empresa")
    def persona_empresa(self, obj):
        return obj.persona.empresa

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "export/detalle-3-dias/",
                self.admin_site.admin_view(self.descargar_detalle_ultimos_3_dias),
                name="core_ticket_export_detalle_3_dias",
            ),
            path(
                "export/resumen-3-dias/",
                self.admin_site.admin_view(self.descargar_resumen_ultimos_3_dias),
                name="core_ticket_export_resumen_3_dias",
            ),
        ]
        return custom_urls + urls

    def _ultimos_tres_dias(self):
        hoy = timezone.localdate()
        desde = hoy - timedelta(days=2)
        return desde, hoy

    def _build_detalle_response_ultimos_3_dias(self):
        desde, hoy = self._ultimos_tres_dias()

        qs = (
            Ticket.objects.select_related("persona__empresa", "voucher_tipo")
            .filter(dia__gte=desde, dia__lte=hoy)
            .order_by("dia", "persona__empresa__codigo", "persona__dni", "creado_en", "id")
        )

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="tickets_detalle_{desde}_{hoy}.csv"'
        )
        response.write("\ufeff")

        writer = csv.writer(response)
        writer.writerow(
            [
                "dia",
                "fecha_hora",
                "empresa_codigo",
                "empresa_nombre",
                "totem_id",
                "documento",
                "nombre_apellido",
                "concesionario",
                "credencial",
                "voucher_tipo",
                "ticket_numero",
            ]
        )

        for ticket in qs.iterator():
            writer.writerow(
                [
                    ticket.dia.isoformat(),
                    timezone.localtime(ticket.creado_en).isoformat(timespec="seconds"),
                    ticket.persona.empresa.codigo,
                    ticket.persona.empresa.nombre,
                    ticket.totem_id,
                    ticket.persona.dni,
                    ticket.persona.nombre_apellido,
                    ticket.persona.concesionario,
                    ticket.persona.credencial,
                    ticket.voucher_tipo.codigo,
                    ticket.ticket_numero,
                ]
            )

        return response

    def _build_resumen_response_ultimos_3_dias(self):
        desde, hoy = self._ultimos_tres_dias()

        resumen = (
            Ticket.objects.filter(dia__gte=desde, dia__lte=hoy)
            .values(
                "dia",
                "persona__empresa__codigo",
                "persona__empresa__nombre",
                "persona__dni",
                "persona__nombre_apellido",
                "persona__concesionario",
                "persona__credencial",
                "voucher_tipo__codigo",
            )
            .annotate(cantidad=Count("id"))
            .order_by(
                "dia",
                "persona__empresa__codigo",
                "persona__dni",
                "voucher_tipo__codigo",
            )
        )

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="tickets_resumen_{desde}_{hoy}.csv"'
        )
        response.write("\ufeff")

        writer = csv.writer(response)
        writer.writerow(
            [
                "dia",
                "empresa_codigo",
                "empresa_nombre",
                "documento",
                "nombre_apellido",
                "concesionario",
                "credencial",
                "voucher_tipo",
                "cantidad",
            ]
        )

        for row in resumen.iterator():
            writer.writerow(
                [
                    row["dia"].isoformat(),
                    row["persona__empresa__codigo"],
                    row["persona__empresa__nombre"],
                    row["persona__dni"],
                    row["persona__nombre_apellido"],
                    row["persona__concesionario"],
                    row["persona__credencial"],
                    row["voucher_tipo__codigo"],
                    row["cantidad"],
                ]
            )

        return response

    def descargar_detalle_ultimos_3_dias(self, request):
        return self._build_detalle_response_ultimos_3_dias()

    def descargar_resumen_ultimos_3_dias(self, request):
        return self._build_resumen_response_ultimos_3_dias()

    @admin.action(description="Exportar detalle CSV (ultimos 3 dias)")
    def exportar_detalle_ultimos_3_dias_csv(self, request, queryset):
        del queryset
        return self._build_detalle_response_ultimos_3_dias()

    @admin.action(description="Exportar resumen CSV (ultimos 3 dias)")
    def exportar_resumen_ultimos_3_dias_csv(self, request, queryset):
        del queryset
        return self._build_resumen_response_ultimos_3_dias()


@admin.register(PoolDiario)
class PoolDiarioAdmin(admin.ModelAdmin):
    list_display = ("empresa", "dia", "codigo", "stock_total", "usados", "actualizado_en")
    list_filter = ("empresa", "dia", "codigo")
    search_fields = ("empresa__codigo", "codigo")


class CanjeOperacionItemInline(admin.TabularInline):
    model = CanjeOperacionItem
    extra = 0
    readonly_fields = ("comida_codigo", "canjear_propio", "cantidad_invitados")
    can_delete = False


@admin.register(CanjeOperacion)
class CanjeOperacionAdmin(admin.ModelAdmin):
    list_display = ("id", "dia", "persona", "persona_empresa", "totem_id", "creado_en")
    list_filter = ("dia", "totem_id", "persona__empresa")
    search_fields = ("persona__dni", "persona__nombre_apellido", "persona__empresa__codigo")
    inlines = [CanjeOperacionItemInline]

    @admin.display(description="Empresa")
    def persona_empresa(self, obj):
        return obj.persona.empresa
