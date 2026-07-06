#!/usr/bin/env python
"""
Setup script for ISI Backend.
Run this after initial migration to create default data.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth.models import User
from core.models import InstituteInfo, BureauEtudeInfo, FormationInfo


def create_default_institute_info():
    """Create default institute information if not exists."""
    if not InstituteInfo.objects.exists():
        InstituteInfo.objects.create(
            name="Institut de Sécurité Industrielle",
            abbreviation="ISI",
            address="Adresse de l'institut",
            city="Alger",
            phone="+213 XX XX XX XX",
            email="contact@isi.dz",
            tva_rate=0.19,
        )
        print("✓ InstituteInfo created")
    else:
        print("✓ InstituteInfo already exists")


def create_default_bureau_etude_info():
    """Create default bureau d'étude info if not exists."""
    if not BureauEtudeInfo.objects.exists():
        BureauEtudeInfo.objects.create(
            name="Bureau d'Étude",
            invoice_prefix="E",
            tva_applicable=True,
            tva_rate=0.19,
        )
        print("✓ BureauEtudeInfo created")
    else:
        print("✓ BureauEtudeInfo already exists")


def create_default_formation_info():
    """Create default formation info if not exists."""
    if not FormationInfo.objects.exists():
        FormationInfo.objects.create(
            name="Centre de Formation",
            invoice_prefix="F",
            tva_applicable=True,
            tva_rate=0.19,
            attestation_validity_years=5,
        )
        print("✓ FormationInfo created")
    else:
        print("✓ FormationInfo already exists")


def create_default_admin():
    """Create default admin user if no users exist."""
    if not User.objects.exists():
        user = User.objects.create_superuser(
            username="admin",
            email="admin@isi.dz",
            password="admin123",
            first_name="Administrateur",
            last_name="ISI",
        )
        user.profile.role = "admin"
        user.profile.save()
        print("✓ Default admin user created (username: admin, password: admin123)")
        print("  ⚠️  Please change the default password after first login!")
    else:
        print("✓ Users already exist")


if __name__ == "__main__":
    print("Setting up ISI Backend...")
    print("-" * 40)

    create_default_institute_info()
    create_default_bureau_etude_info()
    create_default_formation_info()
    create_default_admin()

    print("-" * 40)
    print("Setup complete!")
