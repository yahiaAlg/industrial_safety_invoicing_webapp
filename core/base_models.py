"""
Abstract base model — shared by all apps to DRY up repeated timestamp fields.
"""

from django.db import models


class TimeStampedModel(models.Model):
    """
    Abstract base model providing self-updating created_at / updated_at fields.
    All concrete models that need these fields should inherit from this.
    """

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")

    class Meta:
        abstract = True
