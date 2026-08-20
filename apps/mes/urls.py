from django.urls import path

from . import views

app_name = 'mes'

urlpatterns = [
    # 主页面
    path('records/', views.record_list, name='record_list'),
    path('recipe-check/', views.recipe_check, name='recipe_check'),

    # API
    path('api/stats/', views.stats_api, name='stats_api'),
    path('api/racks/<int:rack_id>/refresh-recipe/', views.refresh_recipe_api, name='refresh_recipe_api'),
    path('api/recipe-verification/', views.recipe_verification_api, name='recipe_verification_api'),
    path('api/rack-measurement/debug/', views.rack_measurement_debug_api, name='rack_measurement_debug_api'),
    path('api/rack-measurement/profile/', views.rack_measurement_profile_api, name='rack_measurement_profile_api'),
    path('api/retry/<int:record_id>/', views.retry_api, name='retry_api'),
    path('api/test/', views.test_upload_api, name='test_upload_api'),
    path('api/binding/update/', views.binding_update_api, name='binding_update_api'),
    path('api/binding/add/', views.binding_add_api, name='binding_add_api'),
    path('api/rack-binding/save/', views.rack_binding_save_api, name='rack_binding_save_api'),
]
