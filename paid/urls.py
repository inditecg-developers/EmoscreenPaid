from django.urls import path

from . import views

app_name = "paid"

urlpatterns = [
    path("clinic/<str:doctor_code>/paid/prescribe/", views.prescribe_order, name="prescribe"),
    path("clinic/<str:doctor_code>/paid/orders/", views.orders_list, name="orders_list"),
    path("clinic/<str:doctor_code>/paid/orders/<str:order_code>/", views.order_detail, name="order_detail"),
    path("p/<str:order_code>/<str:doctor_code>/<str:form_code>/<int:final_amount_paise>/<str:token>/", views.patient_entry, name="patient_entry"),
    path("p/<str:order_code>/payment/", views.patient_payment, name="patient_payment"),
    path("p/<str:order_code>/form/", views.patient_form, name="patient_form"),
    path("p/<str:order_code>/review/", views.patient_review, name="patient_review"),
    path("p/<str:order_code>/submit/", views.patient_submit_final, name="patient_submit_final"),
    path("p/<str:order_code>/thank-you/", views.patient_thank_you, name="patient_thank_you"),
    path("p/<str:order_code>/report/<str:kind>/", views.download_report, name="download_report"),
]
