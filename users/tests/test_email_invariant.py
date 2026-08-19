"""
Emails must be stored lowercase, and that has to hold for every write path.

The rider_email filter matches exactly against a lowercased input, because
iexact cannot use the index on email. That performance decision only works if
the stored value is genuinely canonical -- so the invariant is enforced by the
database rather than by remembering to go through save().
"""

import pytest
from django.db import IntegrityError, transaction

from users.models import User


def unsaved(email):
    return User(
        email=email,
        role=User.Role.RIDER,
        first_name="Test",
        last_name="Rider",
        phone_number="+639170000123",
        password="unusable",
    )


@pytest.mark.django_db
def test_create_user_lowercases_the_email():
    user = User.objects.create_user(
        email="Mixed.Case@Example.COM",
        password="test-pass-123",
        role=User.Role.RIDER,
        first_name="Mixed",
        last_name="Case",
        phone_number="+639170000123",
    )
    assert user.email == "mixed.case@example.com"


@pytest.mark.django_db
def test_bulk_create_cannot_smuggle_in_a_mixed_case_email():
    """
    bulk_create bypasses save(), so the normalisation never runs. Before the
    check constraint this stored 'Mixed.Case@Example.COM' silently, and that
    rider's rides became unreachable through the email filter.
    """
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.bulk_create([unsaved("Mixed.Case@Example.COM")])


@pytest.mark.django_db
def test_queryset_update_cannot_smuggle_one_in_either(rider):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.filter(pk=rider.pk).update(email="SHOUTING@EXAMPLE.COM")


@pytest.mark.django_db
def test_bulk_create_still_works_for_a_canonical_email():
    User.objects.bulk_create([unsaved("already.lower@example.com")])
    assert User.objects.filter(email="already.lower@example.com").exists()
