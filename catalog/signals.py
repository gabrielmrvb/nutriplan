"""Mantém o cache de macros das receitas sempre coerente com os ingredientes.

Sem isto, editar um alimento no admin deixaria as receitas que o usam com
valores antigos — e todo plano gerado depois sairia errado sem nenhum sintoma
visível.
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Food, MealTemplate, MealTemplateItem


@receiver([post_save, post_delete], sender=MealTemplateItem)
def refresh_template_on_item_change(sender, instance, **kwargs):
    template = instance.template
    if MealTemplate.objects.filter(pk=template.pk).exists():
        template.refresh_macros()


@receiver(post_save, sender=Food)
def refresh_templates_on_food_change(sender, instance, created, **kwargs):
    if created:
        return
    templates = MealTemplate.objects.filter(items__food=instance).distinct()
    for template in templates:
        template.refresh_macros()
