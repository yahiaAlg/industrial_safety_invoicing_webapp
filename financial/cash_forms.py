from django import forms

from core.form_mixins import ISIFormMixin
from financial.cash_utils import MONTHS_FR
from financial.models import CashJournal, CashVoucher


class CashJournalForm(ISIFormMixin, forms.ModelForm):
    class Meta:
        model = CashJournal
        fields = ["name", "initial_balance", "period_start", "period_end", "is_active", "notes"]
        widgets = {
            "initial_balance": forms.NumberInput(attrs={"step": "0.01"}),
            "period_start": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "period_end": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["notes"].required = False

    def clean(self):
        data = super().clean()
        d_from, d_to = data.get("period_start"), data.get("period_end")
        if d_from and d_to and d_from > d_to:
            self.add_error("period_end", "La date de fin doit être après la date de début.")
        return data


class CashVoucherForm(ISIFormMixin, forms.ModelForm):
    class Meta:
        model = CashVoucher
        fields = ["date", "amount", "label", "counterparty", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, kind=None, **kwargs):
        super().__init__(*args, **kwargs)
        kind = kind or (self.instance.kind if self.instance.pk else CashVoucher.Kind.IN)
        self.fields["counterparty"].label = (
            "Versé par" if kind == CashVoucher.Kind.IN else "Bénéficiaire"
        )
        self.fields["notes"].required = False

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount is None or amount <= 0:
            raise forms.ValidationError("Le montant doit être positif.")
        return amount


class CashPeriodForm(ISIFormMixin, forms.Form):
    """GET filter for the journal statement / print (month+year or custom range)."""

    month = forms.TypedChoiceField(
        label="Mois",
        required=False,
        coerce=int,
        empty_value=None,
        choices=[("", "Tous")] + [(i, MONTHS_FR[i]) for i in range(1, 13)],
    )
    year = forms.IntegerField(label="Année", required=False, min_value=1900, max_value=2200)
    date_from = forms.DateField(
        label="Du", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    date_to = forms.DateField(
        label="Au", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    q = forms.CharField(
        label="Recherche",
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "Désignation, bénéficiaire, n° bon, montant…"}
        ),
    )
