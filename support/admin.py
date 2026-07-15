from django.contrib import admin
from .models import FAQCategory, FAQ, ContactMessage, SupportTicket, CallbackRequest


@admin.register(FAQCategory)
class FAQCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'sort_order')
    prepopulated_fields = {'slug': ('name',)}
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'category', 'is_active', 'sort_order')
    list_filter = ('category', 'is_active')
    search_fields = ('question', 'answer')


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'is_resolved', 'created_at')
    list_filter = ('is_resolved', 'created_at')
    search_fields = ('name', 'email', 'subject', 'message')
    readonly_fields = ('name', 'email', 'subject', 'message', 'created_at', 'updated_at')


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('subject', 'email', 'status', 'priority', 'assigned_to', 'last_response_at', 'created_at')
    list_filter = ('status', 'priority', 'created_at')
    search_fields = ('subject', 'description', 'email')
    raw_id_fields = ('user', 'assigned_to')


@admin.register(CallbackRequest)
class CallbackRequestAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone_number', 'email', 'is_completed', 'requested_at')
    list_filter = ('is_completed', 'requested_at')
    search_fields = ('name', 'phone_number', 'email', 'message')
