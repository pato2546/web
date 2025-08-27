from django.contrib.auth.models import User
from django.utils import timezone
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.core.mail import send_mail
from flask import app, render_template
import pandas as pd
from django.db import transaction
from django.contrib.auth import logout, authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from ControlInventarioColegio import settings
from .models import Pedido, Producto
from django.views.decorators.http import require_POST
from types import SimpleNamespace


# Vista para inicio de sesión
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')  # Redirige a la vista 'home' después del login
        else:
            messages.error(request, 'Nombre de usuario o contraseña incorrectos.')
    return render(request, 'controlinventario/index.html')

# Vista para cambiar contraseña
@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Tu contraseña ha sido actualizada con éxito.')
            return redirect('change_password')  # Redirige a la vista de cambio de contraseña
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'controlinventario/change_password.html', {'form': form})

# Vista principal
@login_required
def home_view(request):
    return render(request, 'controlinventario/home.html')

# Vista para mostrar y buscar productos
@login_required
def productos_view(request):
    query = request.GET.get('q')
    if query:
        productos = Producto.objects.filter(nombre__icontains=query)
    else:
        productos = Producto.objects.all()
    return render(request, 'controlinventario/productos.html', {'productos': productos, 'query': query})

# Vista para mostrar pedidos
@login_required
def pedidos_view(request):
    # Obtener los filtros del GET
    fecha_inicio = request.GET.get('fecha_inicio')
    hora_inicio = request.GET.get('hora_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    hora_fin = request.GET.get('hora_fin')
    usuario_id = request.GET.get('usuario')  # Obtener el filtro de usuario

    # Inicializar pedidos
    pedidos = Pedido.objects.all()

    # Filtrar por fecha y hora
    if fecha_inicio and hora_inicio:
        fecha_hora_inicio = timezone.datetime.strptime(f'{fecha_inicio} {hora_inicio}', '%Y-%m-%d %H:%M')
        pedidos = pedidos.filter(fecha__gte=fecha_hora_inicio)

    if fecha_fin and hora_fin:
        fecha_hora_fin = timezone.datetime.strptime(f'{fecha_fin} {hora_fin}', '%Y-%m-%d %H:%M')
        pedidos = pedidos.filter(fecha__lte=fecha_hora_fin)

    # Filtrar por usuario
    if usuario_id:
        pedidos = pedidos.filter(usuario_id=usuario_id)

    usuarios = User.objects.all()

    context = {
        'pedidos': pedidos,
        'usuarios': usuarios,
        'request': request,
    }
    return render(request, 'controlinventario/pedidos.html', context)

@login_required
def realizar_pedido(request):
    # GET: mostrar listado de productos ordenados alfabéticamente por nombre
    if request.method == 'GET':
        # Ordenamos por nombre ascendente
        productos = Producto.objects.filter(stock__gt=0).order_by('nombre').values(
            'id', 'nombre', 'descripcion', 'stock'
        )
        # Si prefieres obtener objetos para usar en plantillas:
        # productos = Producto.objects.all().order_by('nombre')
        return render(request, 'controlinventario/hacer_pedido.html', {
            'productos': productos
        })

    # POST: procesar selección y guardarlo en la sesión para carro_view
    if request.method == 'POST':
        carrito = request.session.get('productos_seleccionados', [])

        # Recorremos los campos POST para encontrar productos seleccionados
        for key, value in request.POST.items():
            if key.startswith('producto_') and value == 'on':
                prod_id = key.split('_', 1)[1]

                # Leer cantidad; si no está, usar 1
                cantidad_str = request.POST.get(f'cantidad_{prod_id}', '1')
                try:
                    cantidad = int(cantidad_str)
                except ValueError:
                    cantidad = 1

                # Cargar el producto desde DB
                try:
                    producto = Producto.objects.get(id=prod_id)
                except Producto.DoesNotExist:
                    continue  # si no existe, saltar

                carrito.append({
                    'id': str(prod_id),
                    'nombre': producto.nombre,
                    'descripcion': producto.descripcion,
                    'cantidad': cantidad,
                })

        # Guardar de nuevo en sesión
        request.session['productos_seleccionados'] = carrito
        request.session.modified = True

        messages.success(request, 'Productos agregados al carrito.')
        return redirect('carro')  # Asegúrate de que la URL con name 'carro' apunta a carro_view

# Carrito de pedidos
@login_required
def carro_view(request):
    """
    Muestra el carrito almacenado en sesión.
    Evita tocar la BD al eliminar/actualizar cantidades.
    """
    productos_seleccionados = request.session.get('productos_seleccionados', [])

    items_obj = []
    for item in productos_seleccionados:
        stock = item.get('stock', 0)
        stock_actual = item.get('stock_actual', stock)

        items_obj.append(SimpleNamespace(
            id=item.get('id'),
            nombre=item.get('nombre'),
            descripcion=item.get('descripcion'),
            cantidad=item.get('cantidad', 1),
            stock=stock,
            stock_actual=stock_actual
        ))

    return render(request, 'controlinventario/carrito.html', {
        'productos_seleccionados': items_obj
    })


@require_POST
@login_required
def stock_db_actualizar(request):
    item_id = request.POST.get('id')
    stock_nuevo = request.POST.get('stock', '0')
    try:
        stock_nuevo = int(stock_nuevo)
    except (TypeError, ValueError):
        stock_nuevo = 0
    stock_nuevo = max(0, stock_nuevo)

    try:
        with transaction.atomic():
            producto = Producto.objects.select_for_update().get(id=item_id)
            producto.stock = stock_nuevo
            producto.save()

        messages.success(request, f'Stock de "{producto.nombre}" actualizado a {stock_nuevo} en DB.')

        # Sincroniza stock en sesión si el item está cargado
        items = request.session.get('productos_seleccionados', [])
        for p in items:
            if str(p.get('id')) == str(item_id):
                p['stock_actual'] = stock_nuevo
        request.session['productos_seleccionados'] = items

    except Producto.DoesNotExist:
        messages.error(request, 'Producto no encontrado.')
    except Exception as e:
        messages.error(request, f'Error al actualizar stock: {e}')

    return redirect('carro')


@require_POST
@login_required
def eliminar_item_carro(request):
    """
    Elimina un ítem del carrito sin tocar la BD.
    Solo remueve el item de la lista en sesión 'productos_seleccionados'.
    """
    item_id = request.POST.get('id')
    if item_id is None:
        messages.error(request, 'ID de producto no proporcionado.')
        return redirect('carro')

    items = request.session.get('productos_seleccionados', [])
    nueva_lista = [it for it in items if str(it.get('id')) != str(item_id)]
    request.session['productos_seleccionados'] = nueva_lista
    request.session.modified = True

    messages.success(request, 'Producto eliminado del carro.')
    return redirect('carro')


@require_POST
@login_required
def actualizar_cantidad_carro(request):
    item_id = request.POST.get('id')
    try:
        nueva_cantidad = int(request.POST.get('cantidad', 1))
    except (TypeError, ValueError):
        nueva_cantidad = 1
    nueva_cantidad = max(1, nueva_cantidad)

    items = request.session.get('productos_seleccionados', [])
    for p in items:
        if str(p.get('id')) == str(item_id):
            p['cantidad'] = nueva_cantidad
            break
    request.session['productos_seleccionados'] = items
    request.session.modified = True
    messages.success(request, 'Cantidad actualizada en el carro.')
    return redirect('carro')


# Vista para crear un nuevo pedido
@login_required
def crear_pedido(request):
    if request.method == 'POST':
        usuario = request.user
        producto_id = request.POST.get('producto')
        cantidad = int(request.POST.get('cantidad'))

        producto = Producto.objects.get(id=producto_id)

        if cantidad > producto.stock:
            messages.error(request, f"No hay suficiente stock para el producto {producto.nombre}. Stock disponible: {producto.stock}.")
            return redirect('crear_pedido')

        # Crear el pedido
        pedido = Pedido(usuario=usuario, producto=producto, cantidad=cantidad, autorizado=False)
        pedido.save()

        # Enviar correo al administrador
        subject = 'Nuevo Pedido Creado'
        html_message = render_to_string('controlinventario/nuevo_pedido.html', {'pedido': pedido})
        plain_message = strip_tags(html_message)  # Alternativa de texto plano para el correo
        send_mail(
            subject,
            plain_message,
            'tu_email@gmail.com',  # tu dirección de correo electrónico
            ['admin@example.com'],  # dirección de correo del administrador
            html_message=html_message
        )

        messages.success(request, "Pedido creado exitosamente.")
        return redirect('pedidos')  # Redirige a ver los pedidos

    productos = Producto.objects.all()
    return render(request, 'controlinventario/crear_pedido.html', {'productos': productos})

# 2) Vista para confirmar el pedido
@login_required
def confirmar_pedido(request):
    if request.method != 'POST':
        return redirect('hacer_pedido')  # o la ruta que uses para hacer_pedido

    productos_seleccionados = request.session.get('productos_seleccionados', [])
    motivo = request.POST.get('motivo_pedido', '').strip()

    if not productos_seleccionados:
        messages.error(request, 'No se han seleccionado productos.')
        return redirect('hacer_pedido')

    # Opción A: Crear un Pedido por ítem
    lista_pedidos = []
    for producto_info in productos_seleccionados:
        try:
            producto = Producto.objects.get(id=producto_info['id'])
        except Producto.DoesNotExist:
            continue

        pedido = Pedido(
            usuario=request.user,
            producto=producto,
            cantidad=producto_info['cantidad'],
            autorizado=False
        )
        pedido.save()
        lista_pedidos.append(f'{producto.nombre} (Cantidad: {producto_info["cantidad"]})')

    # Opción B (si tu modelo es Pedido con items)
    # from .models import Pedido, PedidoItem
    # pedido = Pedido.objects.create(usuario=request.user, motivo=motivo, autorizado=False)
    # for producto_info in productos_seleccionados:
    #     producto = Producto.objects.get(id=producto_info['id'])
    #     PedidoItem.objects.create(pedido=pedido, producto=producto, cantidad=producto_info['cantidad'])
    # lista_pedidos = [f'{p["nombre"]} (Cantidad: {p["cantidad"]})' for p in productos_seleccionados]

    subject = 'Solicitud de Autorización de Pedido'
    message_admin = (
        f'Se requiere autorización para el siguiente pedido realizado por {request.user.username}.\n'
        f'Detalles del pedido:\n' + "\n".join(lista_pedidos)
    )
    if motivo:
        message_admin += f"\nMotivo de la solicitud:\n{motivo}"

    send_mail(
        subject,
        message_admin,
        settings.EMAIL_HOST_USER,
        ['pedidocolegio@gmail.com'],  # ajusta destinatario
        fail_silently=False,
    )

    messages.success(request, 'Se ha enviado una solicitud para la autorización del pedido al administrador.')
    # Limpiar el carrito tras confirmar
    request.session['productos_seleccionados'] = []
    return redirect('pedidos')

# Vista para exportar pedidos a Excel
@login_required
def exportar_a_excel(request):
    fecha_inicio = request.GET.get('fecha_inicio')
    hora_inicio = request.GET.get('hora_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    hora_fin = request.GET.get('hora_fin')
    usuario_id = request.GET.get('usuario')

    pedidos = Pedido.objects.all()

    if fecha_inicio and fecha_fin:
        fecha_inicio_dtim = timezone.datetime.strptime(f"{fecha_inicio} {hora_inicio}", "%Y-%m-%d %H:%M").replace(tzinfo=None)
        fecha_fin_dtim = timezone.datetime.strptime(f"{fecha_fin} {hora_fin}", "%Y-%m-%d %H:%M").replace(tzinfo=None)
        pedidos = pedidos.filter(fecha__range=(fecha_inicio_dtim, fecha_fin_dtim))

    if usuario_id:
        pedidos = pedidos.filter(usuario_id=usuario_id)

    data = [
        {
            'ID': pedido.id,
            'Producto': pedido.producto.nombre,
            'Cantidad': pedido.cantidad,
            'Cargo': pedido.cargo,
            'Usuario': pedido.usuario.username,
            'Fecha de Creación': pedido.fecha.replace(tzinfo=None),
        }
        for pedido in pedidos
    ]
    
    df = pd.DataFrame(data)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=pedidos.xlsx'

    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Pedidos')

    return response  # Mantiene el archivo siendo descargado

def logout_view(request):
    logout(request)
    messages.info(request, "Su cierre de sesión fue correcto.")
    return redirect('login')



@login_required
def autorizar_pedido(request):
    # Filtramos los pedidos que no han sido aprobados ni rechazados
    pedidos = Pedido.objects.filter(autorizado=False)  # Asegúrate que ‘autorizado’ esté como None para los pendientes

    return render(request, 'controlinventario/autorizar_pedido.html', {'pedidos': pedidos})

@login_required
def procesar_aprobacion(request):
    if request.method == 'POST':
        pedidos_ids = request.POST.getlist('pedidos')
        
        if not pedidos_ids:
            messages.warning(request, "No se seleccionaron pedidos para procesar.")
            return redirect('autorizar_pedido')

        for pedido_id in pedidos_ids:
            try:
                pedido = Pedido.objects.get(id=pedido_id)
                producto = pedido.producto

                if producto.stock >= pedido.cantidad:
                    producto.stock -= pedido.cantidad
                    producto.save()
                    pedido.autorizado = True
                    pedido.save()
                    messages.success(request, f"Pedido de {pedido.usuario.username} para {pedido.producto.nombre} autorizado.")

                    # Enviar correo al usuario
                    subject = 'Tu Pedido ha Sido Aprobado'
                    html_message = render_to_string('controlinventario/aprobacion_pedido.html', {'pedido': pedido})
                    plain_message = strip_tags(html_message)  # Alternativa de texto plano para el correo
                    send_mail(subject, plain_message, 'tu_email@gmail.com', [pedido.usuario.email], html_message=html_message)
                else:
                    messages.error(request, f"No se puede aprobar el pedido de {pedido.producto.nombre} debido a stock insuficiente.")
            except Pedido.DoesNotExist:
                messages.error(request, f"El pedido con ID {pedido_id} no existe.")
        
        messages.success(request, 'Pedidos procesados con éxito.')
        return redirect('autorizar_pedido')

    return redirect('autorizar_pedido')

@login_required
def procesar_rechazo(request):
    if request.method == 'POST':
        pedido_id = request.POST.get('pedido_id')
        motivo_rechazo = request.POST.get('motivo_rechazo')

        if not motivo_rechazo or len(motivo_rechazo) < 5:
            messages.warning(request, "Por favor, proporciona un motivo de rechazo adecuado.")
            return redirect('autorizar_pedido')

        try:
            pedido = Pedido.objects.get(id=pedido_id)
            pedido.autorizado = False
            pedido.motivo_rechazo = motivo_rechazo
            pedido.save()
            messages.info(request, f"Pedido de {pedido.usuario.username} rechazado con motivo: {motivo_rechazo}.")

            # Enviar correo al usuario
            subject = 'Tu Pedido ha Sido Rechazado'
            html_message = render_to_string('controlinventario/rechazar_pedido.html', {'pedido': pedido, 'motivo': motivo_rechazo})
            plain_message = strip_tags(html_message)  # Alternativa de texto plano para el correo
            send_mail(subject, plain_message, 'tu_email@gmail.com', [pedido.usuario.email], html_message=html_message)
        except Pedido.DoesNotExist:
            messages.error(request, f"El pedido con ID {pedido_id} no existe.")
        
        return redirect('autorizar_pedido')

    return redirect('autorizar_pedido')