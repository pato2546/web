import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ControlInventarioColegio.settings')
django.setup()

from django.core.mail import send_mail

try:
    send_mail(
        'Correo de prueba',
        'Este es un correo de prueba para verificar la configuración SMTP de Django.',
        'pedidocolegio@gmail.com',
        ['pedidocolegio@gmail.com'],
        fail_silently=False,
    )
    print("✅ ¡Correo enviado exitosamente!")
except Exception as e:
    print(f"❌ Error: {e}")