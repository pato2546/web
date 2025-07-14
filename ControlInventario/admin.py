# ControlInventario/admin.py
from django.contrib import admin
from .models import Pedido, Producto
from django.utils.translation import gettext_lazy as _

# Cambiar el título del panel de administración
admin.site.site_header = _("Administración de Control Inventario")
admin.site.site_title = _("Control Inventario")
admin.site.index_title = _("Bienvenido al panel de control de inventario")

class PedidoAdmin(admin.ModelAdmin):
    list_display = ('id', 'usuario', 'producto', 'cantidad', 'autorizado', 'motivo_rechazo')  # Muestra estos campos en la lista de pedidos
    list_filter = ('autorizado',)  # Permite filtrar por autorizado
    search_fields = ('usuario__username', 'producto__nombre')  # Busca por nombre de usuario y producto

# Registro del modelo Pedido en el admin
admin.site.register(Pedido, PedidoAdmin)

class ProductoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'stock')  # Muestra el ID, nombre y stock en la lista de productos
    search_fields = ('nombre',)  # Permite buscar productos por nombre

# Registro del modelo Producto en el admin
admin.site.register(Producto, ProductoAdmin)