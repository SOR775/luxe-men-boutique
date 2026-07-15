from django.contrib import admin
from .models import Warehouse, Stock, StockMovement


class StockMovementInline(admin.TabularInline):
    model = StockMovement
    extra = 0
    readonly_fields = ('created_at', 'created_by')


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'address')
    search_fields = ('name',)


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ('variant', 'warehouse', 'quantity', 'low_stock_threshold', 'is_low_stock', 'is_out_of_stock')
    list_filter = ('warehouse',)
    search_fields = ('variant__sku', 'variant__product__name')
    inlines = [StockMovementInline]

    def is_low_stock(self, obj):
        return obj.is_low_stock
    is_low_stock.boolean = True

    def is_out_of_stock(self, obj):
        return obj.is_out_of_stock
    is_out_of_stock.boolean = True


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('stock', 'movement_type', 'quantity', 'reference', 'created_by', 'created_at')
    list_filter = ('movement_type',)
    readonly_fields = ('created_at',)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
