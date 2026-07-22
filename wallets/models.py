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
        from django.db import transaction, OperationalError
        import time

        for attempt in range(5):
            try:
                with transaction.atomic():
                    locked = Wallet.objects.select_for_update().get(pk=self.pk)
                    locked.balance = locked.balance + amount
                    locked.save(update_fields=['balance', 'updated_at'])
                    self.balance = locked.balance
                    tx = WalletTransaction.objects.create(
                        wallet=locked,
                        amount=amount,
                        transaction_type='credit',
                        description=description,
                        reference=reference,
                        actor=actor,
                        order=order,
                    )
                    WalletSystemLedger.objects.create(
                        wallet=locked,
                        amount=amount,
                        entry_type='credit',
                        description=description or 'Wallet credit',
                        reference=reference,
                    )
                    return tx
            except OperationalError:
                if attempt == 4:
                    raise
                time.sleep(0.05)

    def debit(self, amount, description='', reference='', actor=None, order=None):
        if amount <= 0:
            raise ValueError('Debit amount must be positive')
        amount = Decimal(str(amount))
        from django.db import transaction, OperationalError
        import time

        for attempt in range(5):
            try:
                with transaction.atomic():
                    locked = Wallet.objects.select_for_update().get(pk=self.pk)
                    if locked.balance < amount:
                        raise ValueError('Insufficient funds')
                    locked.balance = locked.balance - amount
                    locked.save(update_fields=['balance', 'updated_at'])
                    self.balance = locked.balance
                    tx = WalletTransaction.objects.create(
                        wallet=locked,
                        amount=amount,
                        transaction_type='debit',
                        description=description,
                        reference=reference,
                        actor=actor,
                        order=order,
                    )
                    WalletSystemLedger.objects.create(
                        wallet=locked,
                        amount=-amount,
                        entry_type='debit',
                        description=description or 'Wallet debit',
                        reference=reference,
                    )
                    return tx
            except OperationalError:
                if attempt == 4:
                    raise
                time.sleep(0.05)

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
        from django.db import transaction

        with transaction.atomic():
            topup = WalletTopUp.objects.select_for_update().get(pk=self.pk)
            if topup.status == self.Status.COMPLETED:
                return topup
            topup.status = self.Status.COMPLETED
            topup.save(update_fields=['status', 'updated_at'])
            self.status = topup.status
            wallet, _ = Wallet.objects.get_or_create(user=topup.user)
            wallet.credit(
                topup.amount,
                description=topup.description or 'Wallet top-up',
                reference=topup.payment_reference or f'topup-{topup.id}',
                actor=actor,
            )
            return topup


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


def award_wallet_credit(user, amount, description='', reference='', actor=None, order=None):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    # Allow callers to pass an order via reference parsing or explicit parameter if extended
    wallet.credit(amount, description=description, reference=reference, actor=actor, order=order)
    return wallet


def award_reward(user, amount, description='', reference='', actor=None):
    WalletReward.objects.create(
        user=user,
        reward_type=WalletReward.RewardType.REWARD,
        amount=amount,
        description=description or 'Loyalty reward',
        reference=reference or f'reward-{user.id}',
    )
    return award_wallet_credit(user, amount, description=description or 'Loyalty reward', reference=reference or f'reward-{user.id}', actor=actor)


# Monkey-patch helpers onto the user model for convenience.
from django.contrib.auth import get_user_model

User = get_user_model()


def _award_referral_bonus(self, amount, reference='', actor=None):
    WalletReward.objects.create(
        user=self,
        reward_type=WalletReward.RewardType.REFERRAL,
        amount=amount,
        description='Referral bonus',
        reference=reference or f'referral-{self.id}',
    )
    return award_wallet_credit(self, amount, description='Referral bonus', reference=reference or f'referral-{self.id}', actor=actor)


def _award_loyalty_reward(self, amount, description='', reference='', actor=None):
    return award_reward(self, amount, description=description, reference=reference, actor=actor)


if not hasattr(User, 'award_referral_bonus'):
    User.add_to_class('award_referral_bonus', _award_referral_bonus)

if not hasattr(User, 'award_loyalty_reward'):
    User.add_to_class('award_loyalty_reward', _award_loyalty_reward)
