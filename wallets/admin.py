from django.contrib import admin

from .models import Wallet, WalletTransaction, WalletSystemLedger, WalletTopUp, WalletReward


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'currency', 'is_active', 'updated_at')
    search_fields = ('user__email', 'user__username')


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ('wallet', 'transaction_type', 'amount', 'description', 'reference', 'created_at')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('reference', 'description', 'wallet__user__email')


@admin.register(WalletSystemLedger)
class WalletSystemLedgerAdmin(admin.ModelAdmin):
    list_display = ('wallet', 'entry_type', 'amount', 'reference', 'created_at')
    search_fields = ('reference', 'description', 'wallet__user__email')


@admin.register(WalletTopUp)
class WalletTopUpAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'currency', 'payment_method', 'status', 'created_at')
    list_filter = ('status', 'payment_method')
    search_fields = ('user__email', 'payment_reference')


@admin.register(WalletReward)
class WalletRewardAdmin(admin.ModelAdmin):
    list_display = ('user', 'reward_type', 'amount', 'reference', 'created_at')
    list_filter = ('reward_type',)
    search_fields = ('user__email', 'reference')
