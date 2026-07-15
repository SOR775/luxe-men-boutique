import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Wallet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wallet',
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=3, default='KES')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Wallet')
        verbose_name_plural = _('Wallets')

    def __str__(self):
        return f'{self.user} - {self.balance} {self.currency}'

    def credit(self, amount, description='', reference='', actor=None, order=None):
        if amount <= 0:
            raise ValueError('Credit amount must be positive')
        amount = Decimal(str(amount))
        from django.db import transaction
        from django.db.models import F

        # Use select_for_update to avoid race conditions and ensure atomicity
        with transaction.atomic():
            locked = Wallet.objects.select_for_update().get(pk=self.pk)
            locked.balance = locked.balance + amount
            locked.save(update_fields=['balance', 'updated_at'])
            # Create transaction record referencing the locked wallet instance
            return WalletTransaction.objects.create(
                wallet=locked,
                amount=amount,
                transaction_type='credit',
                description=description,
                reference=reference,
                actor=actor,
                order=order,
            )

    def debit(self, amount, description='', reference='', actor=None, order=None):
        if amount <= 0:
            raise ValueError('Debit amount must be positive')
        amount = Decimal(str(amount))
        from django.db import transaction

        # Use select_for_update to prevent races and ensure balance check is reliable
        with transaction.atomic():
            locked = Wallet.objects.select_for_update().get(pk=self.pk)
            if locked.balance < amount:
                raise ValueError('Insufficient funds')
            locked.balance = locked.balance - amount
            locked.save(update_fields=['balance', 'updated_at'])
            return WalletTransaction.objects.create(
                wallet=locked,
                amount=amount,
                transaction_type='debit',
                description=description,
                reference=reference,
                actor=actor,
                order=order,
            )

    def reconcile(self):
        """
        Return a tuple (expected_balance, actual_balance, discrepancy)
        where expected_balance is the net sum of transactions (credits - debits),
        actual_balance is the Wallet.balance, and discrepancy = actual - expected.
        """
        from django.db.models import Sum, Q
        credits = self.transactions.filter(transaction_type=WalletTransaction.TransactionType.CREDIT).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        debits = self.transactions.filter(transaction_type=WalletTransaction.TransactionType.DEBIT).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        expected = credits - debits
        actual = self.balance
        return (expected, actual, actual - expected)


class WalletTransaction(models.Model):
    class TransactionType(models.TextChoices):
        CREDIT = 'credit', _('Credit')
        DEBIT = 'debit', _('Debit')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    order = models.ForeignKey('orders.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='wallet_transactions')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TransactionType.choices)
    description = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='wallet_transactions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Wallet Transaction')
        verbose_name_plural = _('Wallet Transactions')

    def __str__(self):
        return f'{self.get_transaction_type_display()} {self.amount} for {self.wallet.user}'


class WalletSystemLedger(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='ledger_entries')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    entry_type = models.CharField(max_length=20, default='system')
    description = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.entry_type} {self.amount} for {self.wallet.user}'


class WalletTopUp(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        COMPLETED = 'completed', _('Completed')
        FAILED = 'failed', _('Failed')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet_top_ups')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='KES')
    payment_method = models.CharField(max_length=20, default='mpesa')
    payment_reference = models.CharField(max_length=100, blank=True, db_index=True)
    checkout_request_id = models.CharField(max_length=100, blank=True, db_index=True)
    phone_number = models.CharField(max_length=15, blank=True)
    description = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Topup {self.amount} for {self.user}'

    def mark_completed(self, actor=None):
        if self.status == self.Status.COMPLETED:
            return self
        self.status = self.Status.COMPLETED
        self.save(update_fields=['status', 'updated_at'])
        wallet, _ = Wallet.objects.get_or_create(user=self.user)
        wallet.credit(
            self.amount,
            description=self.description or 'Wallet top-up',
            reference=self.payment_reference or f'topup-{self.id}',
            actor=actor,
        )
        return self


class WalletReward(models.Model):
    class RewardType(models.TextChoices):
        REFERRAL = 'referral', _('Referral Bonus')
        REWARD = 'reward', _('Reward')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet_rewards')
    reward_type = models.CharField(max_length=20, choices=RewardType.choices, default=RewardType.REWARD)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_reward_type_display()} for {self.user}'


def award_wallet_credit(user, amount, description='', reference='', actor=None):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    # Allow callers to pass an order via reference parsing or explicit parameter if extended
    wallet.credit(amount, description=description, reference=reference, actor=actor)
    return wallet


# Monkey-patch helpers onto the user model for convenience.
if not hasattr(settings.AUTH_USER_MODEL, 'award_referral_bonus'):
    pass


from django.contrib.auth import get_user_model

User = get_user_model()


def _award_referral_bonus(self, amount, reference='', actor=None):
    return award_wallet_credit(self, amount, description='Referral bonus', reference=reference or f'referral-{self.id}', actor=actor)


User.add_to_class('award_referral_bonus', _award_referral_bonus)
