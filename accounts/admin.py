from django.contrib import admin
from .models import User, AuditLog, Permission, Role, Administrator, SuperAdministrator


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'actor', 'target_user', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('actor__email', 'target_user__email', 'message')
    readonly_fields = ('actor', 'target_user', 'action', 'message', 'metadata', 'ip_address', 'created_at')
    ordering = ('-created_at',)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('module', 'codename', 'name')
    list_filter = ('module',)
    search_fields = ('codename', 'name', 'description')


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'role_type', 'is_active', 'created_at')
    list_filter = ('role_type', 'is_active')
    search_fields = ('name', 'description')
    filter_horizontal = ('permissions',)


@admin.register(Administrator)
class AdministratorAdmin(admin.ModelAdmin):
    list_display = ('user', 'department', 'is_active', 'created_at')
    list_filter = ('is_active', 'department')
    search_fields = ('user__email', 'user__username', 'employee_id', 'department')
    filter_horizontal = ('roles', 'extra_permissions')


@admin.register(SuperAdministrator)
class SuperAdministratorAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at')
    search_fields = ('user__email', 'user__username')


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'username', 'is_active', 'is_staff', 'is_email_verified')
    search_fields = ('email', 'username', 'first_name', 'last_name')
    list_filter = ('is_active', 'is_staff', 'is_email_verified')
