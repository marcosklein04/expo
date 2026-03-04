import csv
from datetime import date

from django.contrib import admin
from django.db.models import Count, Q
from django.http import HttpResponse
from django.template.response import TemplateResponse
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
    list_display = (
        "empresa",
        "dni",
        "nombre_apellido",
        "concesionario",
        "credencial",
        "tipo_vianda",
        "puede_invitar",
        "activo",
    )
    list_filter = ("empresa", "tipo_vianda", "puede_invitar", "activo", "concesionario")
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

    @admin.display(description="Empresa")
    def persona_empresa(self, obj):
        return obj.persona.empresa

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "resumen-dia/",
                self.admin_site.admin_view(self.ver_resumen_dia),
                name="core_ticket_resumen_dia",
            ),
            path(
                "export/resumen-dia/",
                self.admin_site.admin_view(self.descargar_resumen_dia),
                name="core_ticket_export_resumen_dia",
            ),
        ]
        return custom_urls + urls

    def _resolver_dia_exportacion(self, request):
        raw_dia = str(request.GET.get("dia") or request.GET.get("dia__exact") or "").strip()
        if raw_dia:
            try:
                return date.fromisoformat(raw_dia)
            except ValueError:
                pass
        return timezone.localdate()

    def _build_resumen_queryset_dia(self, request):
        dia = self._resolver_dia_exportacion(request)

        resumen = (
            Ticket.objects.filter(dia=dia)
            .values(
                "persona__dni",
                "persona__nombre_apellido",
            )
            .annotate(
                voucher_desayuno=Count(
                    "id",
                    filter=Q(voucher_tipo__codigo=VoucherTipo.DESAYUNO),
                ),
                voucher_almuerzo=Count(
                    "id",
                    filter=Q(voucher_tipo__codigo=VoucherTipo.ALMUERZO),
                ),
                invitado_desayuno=Count(
                    "id",
                    filter=Q(voucher_tipo__codigo=VoucherTipo.INVITADO_DESAYUNO),
                ),
                invitado_almuerzo=Count(
                    "id",
                    filter=Q(voucher_tipo__codigo=VoucherTipo.INVITADO_ALMUERZO),
                ),
            )
            .order_by("persona__nombre_apellido", "persona__dni")
        )
        return dia, resumen

    def _build_resumen_response_dia(self, request):
        dia, resumen = self._build_resumen_queryset_dia(request)
        dia_csv = dia.strftime("%d/%m/%y")

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="tickets_resumen_{dia}.csv"'
        )
        response.write("\ufeff")

        writer = csv.writer(response, delimiter=";")
        writer.writerow(
            [
                "Fecha",
                "DNI/Pasaporte",
                "Nombre y apellido",
                "Voucher Desayuno",
                "Voucher almuerzo",
                "invitado desayuno",
                "invitado almuerzo",
            ]
        )

        for row in resumen.iterator():
            writer.writerow(
                [
                    dia_csv,
                    row["persona__dni"],
                    row["persona__nombre_apellido"],
                    row["voucher_desayuno"],
                    row["voucher_almuerzo"],
                    row["invitado_desayuno"],
                    row["invitado_almuerzo"],
                ]
            )

        return response

    def ver_resumen_dia(self, request):
        dia, resumen = self._build_resumen_queryset_dia(request)
        filas = list(resumen)

        totales = {
            "personas": len(filas),
            "voucher_desayuno": sum(int(f["voucher_desayuno"]) for f in filas),
            "voucher_almuerzo": sum(int(f["voucher_almuerzo"]) for f in filas),
            "invitado_desayuno": sum(int(f["invitado_desayuno"]) for f in filas),
            "invitado_almuerzo": sum(int(f["invitado_almuerzo"]) for f in filas),
        }
        totales["total_vouchers"] = (
            totales["voucher_desayuno"]
            + totales["voucher_almuerzo"]
            + totales["invitado_desayuno"]
            + totales["invitado_almuerzo"]
        )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Resumen del dia",
            "dia_iso": dia.isoformat(),
            "dia_label": dia.strftime("%d/%m/%y"),
            "rows": filas,
            "totales": totales,
        }
        return TemplateResponse(request, "admin/core/ticket/resumen_dia.html", context)

    def descargar_resumen_dia(self, request):
        return self._build_resumen_response_dia(request)

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
