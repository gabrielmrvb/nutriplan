"""Popula o catálogo com alimentos, tags e receitas iniciais.

Idempotente: pode rodar quantas vezes quiser sem duplicar nada.

    python manage.py seed_catalog
    python manage.py seed_catalog --reset-templates
"""
import json
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import (
    DietaryTag,
    Food,
    FoodPortion,
    MealTemplate,
    MealTemplateItem,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _load(filename):
    with open(DATA_DIR / filename, encoding="utf-8") as fp:
        return json.load(fp)


class Command(BaseCommand):
    help = "Carrega alimentos, medidas caseiras, tags e receitas iniciais."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-templates",
            action="store_true",
            help="Recria os ingredientes das receitas a partir do JSON.",
        )


    def _log(self, mensagem):
        """Só fala quando pedem. `verbosity=0` é o padrão dentro dos testes."""
        if self.verbosity:
            self.stdout.write(mensagem)

    @transaction.atomic
    def handle(self, *args, **options):
        self.verbosity = options.get("verbosity", 1)
        tags = self._seed_tags()
        foods = self._seed_foods()
        self._seed_templates(foods, tags, reset=options["reset_templates"])
        self._log(self.style.SUCCESS("Catálogo carregado."))

    def _seed_tags(self):
        tags = {}
        for row in _load("dietary_tags.json"):
            tag, _ = DietaryTag.objects.update_or_create(
                slug=row["slug"], defaults={"name": row["name"], "kind": row["kind"]}
            )
            tags[row["slug"]] = tag
        self._log(f"  {len(tags)} tags")
        return tags

    def _seed_foods(self):
        foods = {}
        for row in _load("foods.json"):
            food, _ = Food.objects.update_or_create(
                name=row["name"],
                brand=row.get("brand", ""),
                defaults={
                    "base_unit": row.get("base_unit", "g"),
                    "kcal": Decimal(str(row["kcal"])),
                    "protein_g": Decimal(str(row["protein_g"])),
                    "carb_g": Decimal(str(row["carb_g"])),
                    "fat_g": Decimal(str(row["fat_g"])),
                    "fiber_g": Decimal(str(row.get("fiber_g", 0))),
                    "source": "manual",
                    "aisle": row.get("aisle", "grocery"),
                    # Alimento caro ou difícil de achar sai do ar com "active":
                    # false no JSON, em vez de ser apagado — quem já comeu
                    # aquilo continua com o histórico legível.
                    "is_active": row.get("active", True),
                },
            )
            for portion in row.get("portions", []):
                FoodPortion.objects.update_or_create(
                    food=food,
                    label=portion["label"],
                    defaults={
                        "grams": Decimal(str(portion["grams"])),
                        "is_default": portion.get("default", False),
                    },
                )
            foods[row["name"]] = food

        ativos = sum(1 for food in foods.values() if food.is_active)
        self._log(f"  {len(foods)} alimentos ({ativos} ativos)")
        return foods

    def _seed_templates(self, foods, tags, reset=False):
        count = 0
        no_json = set()
        for row in _load("meal_templates.json"):
            no_json.add(row["name"])
            template, created = MealTemplate.objects.update_or_create(
                name=row["name"],
                defaults={
                    "category": row["category"],
                    "prep_minutes": row.get("prep_minutes", 10),
                    "instructions": row.get("instructions", ""),
                    "everyday": row.get("everyday", True),
                    "is_active": True,
                },
            )
            template.tags.set([tags[slug] for slug in row.get("tags", []) if slug in tags])

            if created or reset:
                template.items.all().delete()
                for order, (food_name, quantity, scalable) in enumerate(row["items"]):
                    MealTemplateItem.objects.create(
                        template=template,
                        food=foods[food_name],
                        quantity_g=Decimal(str(quantity)),
                        scalable=scalable,
                        order=order,
                    )
            template.refresh_macros()
            count += 1

        # Receita que saiu do JSON é desativada, não apagada: planos antigos
        # apontam para ela (MealOption usa PROTECT) e o histórico de quem já
        # comeu precisa continuar de pé.
        aposentadas = (
            MealTemplate.objects.exclude(name__in=no_json)
            .filter(is_active=True)
            .update(is_active=False)
        )
        self._log(f"  {count} receitas ({aposentadas} aposentadas)")
