from django.shortcuts import render

from .models import Product, ProductionBatch, Rack, RackRecipe


def product_list(request):
    products = (
        Product.objects.select_related('batch', 'rack').order_by('-created_at')[:200]
    )
    return render(request, 'production/product_list.html', {'products': products})


def rack_list(request):
    racks = Rack.objects.select_related('current_recipe').order_by('-updated_at')
    return render(request, 'production/rack_list.html', {'racks': racks})


def recipe_list(request):
    recipes = RackRecipe.objects.order_by('-updated_at')
    return render(request, 'production/recipe_list.html', {'recipes': recipes})
