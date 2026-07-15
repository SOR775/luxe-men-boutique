from django.core.management.base import BaseCommand
from accounts.models import Permission, Role


class Command(BaseCommand):
    help = 'Seed the default RBAC roles for the shop admin.'

    def handle(self, *args, **options):
        permission_seed = [
            ('access_admin_dashboard', 'Access admin dashboard', 'admin', 'View the main admin dashboard.'),
            ('manage_staff_roles', 'Manage staff roles', 'admin', 'Create, edit, and assign staff roles.'),
            ('access_orders', 'Access orders', 'orders', 'View and manage order operations.'),
            ('access_products', 'Access products', 'products', 'View and manage catalog products.'),
            ('access_inventory_dashboard', 'Access inventory dashboard', 'inventory', 'View inventory operations.'),
            ('access_inventory_sku', 'Access SKU management', 'inventory', 'Manage SKU records and stockkeeper workflows.'),
            ('access_inventory_stock_history', 'Access stock history', 'inventory', 'Review stock history and adjustments.'),
            ('access_coupons', 'Access coupons', 'orders', 'Manage promotions and coupons.'),
            ('access_bulk_order_actions', 'Access bulk order actions', 'orders', 'Run bulk operations against orders.'),
            ('access_rma', 'Access RMA requests', 'orders', 'Approve returns and review RMA workflows.'),
            ('access_support_queue', 'Access support queue', 'support', 'Review customer support tickets and cases.'),
            ('access_user_management', 'Access user management', 'admin', 'Manage staff and customer account records.'),
            ('access_audit_log', 'Access audit logs', 'admin', 'Review admin audit trails.'),
            ('access_system_health', 'Access system health', 'admin', 'Review environment and health monitoring.'),
            ('access_dispute_resolution', 'Access dispute resolution', 'support', 'Resolve disputes and review escrow outcomes.'),
            ('access_content_moderation', 'Access content moderation', 'marketing', 'Review content moderation measures.'),
            ('access_settings', 'Access system settings', 'admin', 'Manage platform configuration.'),
            ('access_wallets', 'Access wallets', 'wallets', 'Review wallet records and cash movement.'),
            ('access_wallet_transactions', 'Access wallet transactions', 'wallets', 'Review wallet transactions and payment logs.'),
            ('access_finance', 'Access finance', 'finance', 'Review payment and refund workflows.'),
            ('access_payment_review', 'Access payment review', 'payments', 'Review payment and refund workflows.'),
            ('access_reconciliation', 'Access reconciliation', 'finance', 'Manage reconciliation and refund oversight.'),
        ]

        permissions = {}
        for codename, name, module, description in permission_seed:
            permission, _ = Permission.objects.get_or_create(
                codename=codename,
                defaults={'name': name, 'module': module, 'description': description},
            )
            permissions[codename] = permission

        defaults = {
            'super_owner': {
                'label': 'Super Owner',
                'role_type': Role.RoleType.CUSTOM,
                'description': 'Full system ownership and staff permission management.',
                'permissions': permissions,
            },
            'store_manager': {
                'label': 'Store Manager',
                'role_type': Role.RoleType.STORE_MANAGER,
                'description': 'Orders, coupons, and order operations.',
                'permissions': {
                    'access_admin_dashboard': permissions['access_admin_dashboard'],
                    'access_orders': permissions['access_orders'],
                    'access_products': permissions['access_products'],
                    'access_coupons': permissions['access_coupons'],
                    'access_bulk_order_actions': permissions['access_bulk_order_actions'],
                    'access_rma': permissions['access_rma'],
                },
            },
            'inventory_manager': {
                'label': 'Inventory Manager',
                'role_type': Role.RoleType.INVENTORY_MANAGER,
                'description': 'Inventory, stock history, and SKU workflows.',
                'permissions': {
                    'access_admin_dashboard': permissions['access_admin_dashboard'],
                    'access_inventory_dashboard': permissions['access_inventory_dashboard'],
                    'access_inventory_sku': permissions['access_inventory_sku'],
                    'access_inventory_stock_history': permissions['access_inventory_stock_history'],
                },
            },
            'support_agent': {
                'label': 'Support Agent',
                'role_type': Role.RoleType.CUSTOMER_SUPPORT,
                'description': 'Customer support, ticket resolution, and RMA support.',
                'permissions': {
                    'access_admin_dashboard': permissions['access_admin_dashboard'],
                    'access_support_queue': permissions['access_support_queue'],
                    'access_dispute_resolution': permissions['access_dispute_resolution'],
                    'access_content_moderation': permissions['access_content_moderation'],
                    'access_rma': permissions['access_rma'],
                },
            },
            'finance_admin': {
                'label': 'Finance Admin',
                'role_type': Role.RoleType.FINANCE_MANAGER,
                'description': 'Wallet, payment review, and financial reconciliation.',
                'permissions': {
                    'access_admin_dashboard': permissions['access_admin_dashboard'],
                    'access_wallets': permissions['access_wallets'],
                    'access_wallet_transactions': permissions['access_wallet_transactions'],
                    'access_finance': permissions['access_finance'],
                    'access_payment_review': permissions['access_payment_review'],
                    'access_reconciliation': permissions['access_reconciliation'],
                },
            },
        }

        for data in defaults.values():
            role, created = Role.objects.get_or_create(
                name=data['label'],
                defaults={
                    'role_type': data['role_type'],
                    'description': data['description'],
                    'is_active': True,
                },
            )
            role.permissions.set(list(data['permissions'].values()))
            self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Exists'} role: {role.name}"))

        self.stdout.write(self.style.SUCCESS('Default RBAC roles seeded successfully.'))
