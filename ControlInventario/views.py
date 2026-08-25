import logging
import pandas as pd
from datetime import datetime

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q, F
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags
from django.views.decorators.http import require_POST
from types import SimpleNamespace

from ControlInventarioColegio import settings
from .models import Pedido, Producto

logger = logging.getLogger(__name__)

# Helper para verificar si es staff/admin
def es_staff(user):
    return user.is_staff


# Vista para inicio de sesión
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
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
            return redirect('change_password')
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
    fecha_inicio = request.GET.get('fecha_inicio')
    hora_inicio = request.GET.get('hora_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    hora_fin = request.GET.get('hora_fin')
    usuario_id = request.GET.get('usuario')

    # Optimización N+1 con select_related
    pedidos = Pedido.objects.select_related('producto', 'usuario').all()

    if fecha_inicio and hora_inicio:
        fecha_hora_inicio = timezone.make_aware(
            datetime.strptime(f'{fecha_inicio} {hora_inicio}', '%Y-%m-%d %H:%M')
        )
        pedidos = pedidos.filter(fecha__gte=fecha_hora_inicio)

    if fecha_fin and hora_fin:
        fecha_hora_fin = timezone.make_aware(
            datetime.strptime(f'{fecha_fin} {hora_fin}', '%Y-%m-%d %H:%M')
        )
        pedidos = pedidos.filter(fecha__lte=fecha_hora_fin)

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
    if request.method == 'GET':
        q = request.GET.get('q', '').strip()
        productos_qs = Producto.objects.filter(stock__gt=0)
        if q:
            productos_qs = productos_qs.filter(
                Q(nombre__icontains=q) | Q(descripcion__icontains=q)
            )
        productos = productos_qs.order_by('nombre').values('id', 'nombre', 'descripcion', 'stock')
        return render(request, 'controlinventario/hacer_pedido.html', {
            'productos': productos,
            'query': q,
        })

    if request.method == 'POST':
        carrito = request.session.get('productos_seleccionados', [])

        for key, value in request.POST.items():
            if key.startswith('producto_') and value == 'on':
                prod_id = key.split('_', 1)[1]
                cantidad_str = request.POST.get(f'cantidad_{prod_id}', '1')
                try:
                    cantidad = int(cantidad_str)
                except ValueError:
                    cantidad = 1

                try:
                    producto = Producto.objects.get(id=prod_id)
                except Producto.DoesNotExist:
                    continue

                carrito.append({
                    'id': str(prod_id),
                    'nombre': producto.nombre,
                    'descripcion': producto.descripcion,
                    'cantidad': cantidad,
                    'motivo_pedido': motivo_pedido,
                })

        request.session['productos_seleccionados'] = carrito
        request.session.modified = True

        messages.success(request, 'Productos agregados al carrito.')
        return redirect('carro')


@login_required
def carro_view(request):
    productos_seleccionados = request.session.get('productos_seleccionados', [])

    items_obj = [
        SimpleNamespace(
            id=item.get('id'),
            nombre=item.get('nombre'),
            descripcion=item.get('descripcion'),
            cantidad=item.get('cantidad', 1),
            stock=item.get('stock', 0),
            stock_actual=item.get('stock_actual', item.get('stock', 0))
        )
        for item in productos_seleccionados
    ]

    return render(request, 'controlinventario/carrito.html', {
        'productos_seleccionados': items_obj
    })


@require_POST
@login_required
def eliminar_item_carro(request):
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


@login_required
def confirmar_pedido(request):
    if request.method != 'POST':
        return redirect('realizar_pedido')

    productos_seleccionados = request.session.get('productos_seleccionados', [])

    if not productos_seleccionados:
        messages.error(request, 'No se han seleccionado productos.')
        return redirect('realizar_pedido')

    lista_pedidos = []
    try:
        with transaction.atomic():
            for producto_info in productos_seleccionados:
                try:
                    producto = Producto.objects.get(id=producto_info['id'])
                except Producto.DoesNotExist:
                    continue

                pedido = Pedido(
                    usuario=request.user,
                    producto=producto,
                    cantidad=producto_info['cantidad'],
                    motivo_pedido=producto_info.get('motivo_pedido', ''),
                    autorizado=False
                )
                pedido.save()
                lista_pedidos.append(f'{producto.nombre} (Cantidad: {producto_info["cantidad"]})')
    except Exception:
        logger.exception("Error al crear pedidos en confirmar_pedido")
        messages.error(request, 'Error al procesar el pedido. Por favor, intenta nuevamente.')
        return redirect('carro')

    subject = 'Solicitud de Autorización de Pedido'
    message_admin = (
        f'Se requiere autorización para el siguiente pedido realizado por {request.user.username}.\n'
        f'Detalles del pedido:\n' + "\n".join(lista_pedidos)
    )

    try:
        send_mail(
            subject,
            message_admin,
            getattr(settings, 'DEFAULT_FROM_EMAIL', getattr(settings, 'EMAIL_HOST_USER', None)),
            ['pedidocolegio@gmail.com'],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Error al enviar correo de autorización")
        messages.error(request, 'Error al enviar el correo de autorización.')
        return redirect('carro')

    messages.success(request, 'Se ha enviado una solicitud para la autorización del pedido al administrador.')
    request.session['productos_seleccionados'] = []
    request.session.modified = True

    return redirect('carro')


@login_required
def exportar_a_excel(request):
    fecha_inicio = request.GET.get('fecha_inicio')
    hora_inicio = request.GET.get('hora_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    hora_fin = request.GET.get('hora_fin')
    usuario_id = request.GET.get('usuario')

    pedidos = Pedido.objects.select_related('producto', 'usuario').all()

    if fecha_inicio and fecha_fin:
        fecha_inicio_dtim = timezone.make_aware(datetime.strptime(f"{fecha_inicio} {hora_inicio}", "%Y-%m-%d %H:%M"))
        fecha_fin_dtim = timezone.make_aware(datetime.strptime(f"{fecha_fin} {hora_fin}", "%Y-%m-%d %H:%M"))
        pedidos = pedidos.filter(fecha__range=(fecha_inicio_dtim, fecha_fin_dtim))

    if usuario_id:
        pedidos = pedidos.filter(usuario_id=usuario_id)

    data = [
        {
            'ID': pedido.id,
            'Producto': pedido.producto.nombre,
            'Cantidad': pedido.cantidad,
            'Cargo': getattr(pedido, 'cargo', 'N/A'),
            'Usuario': pedido.usuario.username,
            'Fecha de Creación': timezone.localtime(pedido.fecha).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for pedido in pedidos
    ]

    df = pd.DataFrame(data)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=pedidos.xlsx'

    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Pedidos')

    return response


def logout_view(request):
    logout(request)
    messages.info(request, "Su cierre de sesión fue correcto.")
    return redirect('login')


# Vistas de Aprobación Protegidas por es_staff
@login_required
@user_passes_test(es_staff)
def autorizar_pedido(request):
    fecha_inicio = timezone.make_aware(datetime(2026, 8, 1))

    pedidos = Pedido.objects.select_related('producto', 'usuario').filter(
        autorizado=False,
        fecha__gte=fecha_inicio
    ).filter(
        Q(motivo_rechazo__isnull=True) | Q(motivo_rechazo='')
    ).order_by('-fecha')

    return render(request, 'controlinventario/autorizar_pedido.html', {'pedidos': pedidos})


@login_required
@user_passes_test(es_staff)
def procesar_aprobacion(request):
    if request.method == 'POST':
        pedidos_ids = request.POST.getlist('pedidos')

        if not pedidos_ids:
            messages.warning(request, "No se seleccionaron pedidos para procesar.")
            return redirect('autorizar_pedido')

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', getattr(settings, 'EMAIL_HOST_USER', None))

        for pedido_id in pedidos_ids:
            try:
                with transaction.atomic():
                    # Bloqueamos el registro del producto para prevenir condiciones de carrera
                    pedido = Pedido.objects.select_related('producto', 'usuario').get(id=pedido_id)
                    producto = Producto.objects.select_for_update().get(id=pedido.producto_id)

                    if producto.stock >= pedido.cantidad:
                        pedido.autorizado = True
                        pedido.save()

                        # Descuento atómico
                        Producto.objects.filter(id=producto.id).update(stock=F('stock') - pedido.cantidad)

                        messages.success(request, f"Pedido de {pedido.usuario.username} para {producto.nombre} autorizado.")

                        # Notificación por correo
                        subject = 'Tu Pedido ha Sido Aprobado'
                        html_message = render_to_string('controlinventario/aprobacion_pedido.html', {'pedido': pedido})
                        plain_message = strip_tags(html_message)
                        
                        send_mail(
                            subject,
                            plain_message,
                            from_email,
                            [pedido.usuario.email],
                            html_message=html_message,
                            fail_silently=True
                        )
                    else:
                        messages.error(request, f"No se puede aprobar el pedido de {producto.nombre} debido a stock insuficiente.")
            except Pedido.DoesNotExist:
                messages.error(request, f"El pedido con ID {pedido_id} no existe.")

        return redirect('autorizar_pedido')

    return redirect('autorizar_pedido')


@login_required
@user_passes_test(es_staff)
def procesar_rechazo(request):
    if request.method == 'POST':
        pedido_id = request.POST.get('pedido_id')
        motivo_rechazo = request.POST.get('motivo_rechazo')

        if not motivo_rechazo or len(motivo_rechazo.strip()) < 5:
            messages.warning(request, "Por favor, proporciona un motivo de rechazo adecuado (mínimo 5 caracteres).")
            return redirect('autorizar_pedido')

        try:
            pedido = Pedido.objects.select_related('usuario').get(id=pedido_id)
            pedido.autorizado = False
            pedido.motivo_rechazo = motivo_rechazo
            pedido.save()

            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', getattr(settings, 'EMAIL_HOST_USER', None))
            subject = 'Tu Pedido ha Sido Rechazado'
            html_message = render_to_string('controlinventario/rechazar_pedido.html', {'pedido': pedido, 'motivo': motivo_rechazo})
            plain_message = strip_tags(html_message)

            send_mail(
                subject,
                plain_message,
                from_email,
                [pedido.usuario.email],
                html_message=html_message,
                fail_silently=True
            )

            messages.info(request, f"Pedido de {pedido.usuario.username} rechazado.")

        except Pedido.DoesNotExist:
            messages.error(request, f"El pedido con ID {pedido_id} no existe.")

    return redirect('autorizar_pedido')