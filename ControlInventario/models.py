# models.py
from django.db import models
from django.contrib.auth.models import User

class Producto(models.Model):
    nombre = models.CharField(max_length=50)
    descripcion = models.TextField(max_length=30)
    stock = models.PositiveIntegerField()
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nombre

class Pedido(models.Model):
    CARGOS_OPCIONES = [
        ('rector', 'Rector'),
        ('administrativo', 'Administrativo'),
        ('profesor', 'Profesor'),
        ('auxiliar', 'Auxiliar'),
        ('otro', 'Otro'),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cargo = models.CharField(max_length=20, choices=CARGOS_OPCIONES, default='otro')
    cantidad = models.PositiveIntegerField()
    fecha = models.DateTimeField(auto_now_add=True)
    autorizado = models.BooleanField(default=False)  # Campo agregado para autorización
    motivo_rechazo = models.TextField(null=True, blank=True)  # Campo para almacenar el motivo de rechazo

    def __str__(self):
        return f"{self.usuario.username} - {self.producto.nombre} - {self.cargo} - {self.cantidad}"