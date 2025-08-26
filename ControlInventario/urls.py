# ControlInventario/urls.py
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView

urlpatterns = [
    path('', RedirectView.as_view(url='/login/', permanent=False)),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('change-password/', views.change_password, name='change_password'),

    # Crear y manejar pedidos
    path('crear/', views.crear_pedido, name='crear_pedido'),  # Esta línea debe mantenerse si aún se necesita
    path('pedidos/', views.pedidos_view, name='pedidos'),  # Vista de todos los pedidos
    path('hacer_pedido/', views.realizar_pedido, name='hacer_pedido'),  # Realizar un pedido
    path('carro/', views.carro_view, name='carro'),  # Carro de compras
    path('productos/', views.productos_view, name='productos_view'),  # Vista de productos
    path('home/', views.home_view, name='home'),  # Página principal
    path('confirmar_pedido/', views.confirmar_pedido, name='confirmar_pedido'),
    path('exportar_a_excel/', views.exportar_a_excel, name='exportar_a_excel'),

    # Autorizar pedidos
    path('autorizar-pedido/', views.autorizar_pedido, name='autorizar_pedido'),
    # Actualiza las rutas de autorización
    path('procesar-aprobacion/', views.procesar_aprobacion, name='procesar_aprobacion'),
    path('procesar-rechazo/', views.procesar_rechazo, name='procesar_rechazo'),

    # Manejo de restablecimiento de contraseña
    path('password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
]