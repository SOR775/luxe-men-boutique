import uuid
from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subcategories')
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.parent.name} > {self.name}" if self.parent else self.name


class Brand(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to='brands/', null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Collection(models.Model):
    """E.g., Autumn 2026, Summer Essentials"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='collections/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(models.Model):
    class Visibility(models.TextChoices):
        PUBLISHED = 'published', _('Published')
        DRAFT = 'draft', _('Draft')
        HIDDEN = 'hidden', _('Hidden')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=250, unique=True, blank=True)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    collection = models.ForeignKey(Collection, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.DRAFT)
    is_featured = models.BooleanField(default=False)
    is_trending = models.BooleanField(default=False)
    
    # SEO
    meta_title = models.CharField(max_length=150, blank=True)
    meta_description = models.TextField(blank=True)

    # Apparel-specific product details
    size_chart = models.TextField(blank=True, help_text="Size chart notes or measurements")
    fabric_info = models.TextField(blank=True, help_text="Fabric composition and feel")
    care_instructions = models.TextField(blank=True, help_text="Care instructions")
    model_height = models.CharField(max_length=50, blank=True, help_text="Model height, e.g. 6'1\"")
    model_size_worn = models.CharField(max_length=20, blank=True, help_text="Model size worn, e.g. M")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        old_base_price = None
        if not is_new:
            old = Product.objects.filter(pk=self.pk).first()
            if old is not None:
                old_base_price = old.base_price

        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

        if old_base_price is not None and self.base_price < old_base_price:
            from notifications.models import Notification
            from .models import WishlistItem

            wishlists = WishlistItem.objects.filter(product=self).select_related('user')
            for item in wishlists:
                user = item.user
                if not user.is_active:
                    continue
                try:
                    Notification.create(
                        user=user,
                        title=f'Price drop: {self.name}',
                        message=f'The price for {self.name} has just dropped. Revisit the product page to shop before it sells out.',
                        target_url=self.get_absolute_url(),
                        level=Notification.Level.SUCCESS,
                        send_sms=True,
                    )
                except Exception:
                    pass

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('products:detail', kwargs={'slug': self.slug})


class ProductVariant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    sku = models.CharField(max_length=50, unique=True)
    barcode = models.CharField(max_length=50, blank=True, null=True)
    
    size = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=50, blank=True)
    material = models.CharField(max_length=100, blank=True)
    
    price_adjustment = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Amount to add/subtract from base price")
    
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text="Weight in kg")
    length = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text="Length in cm")
    width = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text="Width in cm")
    height = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text="Height in cm")

    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('product', 'size', 'color', 'material')

    def __str__(self):
        details = []
        if self.color: details.append(self.color)
        if self.size: details.append(self.size)
        if self.material: details.append(self.material)
        variant_desc = " - ".join(details) if details else "Default"
        return f"{self.product.name} ({variant_desc})"

    @property
    def final_price(self):
        return self.product.base_price + self.price_adjustment

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        old_price = None
        if not is_new:
            old = ProductVariant.objects.filter(pk=self.pk).select_related('product').first()
            if old is not None:
                old_price = old.final_price

        super().save(*args, **kwargs)

        if old_price is not None and self.final_price < old_price:
            from .models import WishlistItem
            from notifications.models import Notification

            wishlists = WishlistItem.objects.filter(product=self.product).select_related('user')
            for item in wishlists:
                user = item.user
                if not user.is_active:
                    continue
                try:
                    Notification.create(
                        user=user,
                        title=f'Price drop: {self.product.name}',
                        message=f'The price for {self.product.name} has just dropped. Revisit the product page before it sells out.',
                        target_url=self.product.get_absolute_url(),
                        level=Notification.Level.SUCCESS,
                        send_sms=True,
                    )
                except Exception:
                    pass


class ProductImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name='variant_images')
    image = models.ImageField(upload_to='products/images/')
    image_360 = models.ImageField(upload_to='products/360/', null=True, blank=True)
    video = models.FileField(upload_to='products/videos/', null=True, blank=True)
    alt_text = models.CharField(max_length=150, blank=True)
    is_primary = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', '-is_primary']

    def save(self, *args, **kwargs):
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.product.name}"


class WishlistItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wishlist_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='wishlisted_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.product.name}"


class ProductReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveSmallIntegerField(choices=[(i, str(i)) for i in range(1, 6)])
    comment = models.TextField(blank=True)
    fit_feedback = models.CharField(max_length=20, blank=True, choices=[('true_to_size', 'True to size'), ('runs_small', 'Runs small'), ('runs_large', 'Runs large')])
    is_verified_purchase = models.BooleanField(default=False)
    helpful_votes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'product')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.rating} star review for {self.product.name} by {self.user}"
