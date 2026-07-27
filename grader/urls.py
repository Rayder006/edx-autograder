from django.urls import path
from django.conf import settings
from . import views

urlpatterns = [
    path('avaliacao/', views.lti_grade_endpoint, name='lti_grade_endpoint'),
]

# Mapeamento explícito das URLs antigas do EdX para as chaves internas do tests.json
MAPEAMENTO_EXERCICIOS = {
    "quadrado": "week_2_quadrado",
    "media": "week_2_medias",
    "paridade": "week_3_paridade",
    "fizz": "week_3_fizz",
    "buzz": "week_3_buzz",
    "fizzbuzz": "week_3_fizzbuzz",
    "ordenacao": "week_3_ordenacao",
    "pontos": "week_3_pontos",
    "bhaskara": "week_3_bhaskara",
    "fatorial": "week_4_fatorial",
    "n_impares": "week_4_n_impares",
    "soma_digitos": "week_4_soma_digitos",
    "primalidade": "week_4_primalidade",
    "digitos_adjacentes": "week_4_digitos_adjacentes",
    "maximo_2": "week_5_maximo_2",
    "maior_primo": "week_5_maior_primo",
    "vogais": "week_5_vogais",
    "fizzbuzz_funcao": "week_5_fizzbuzz_funcao",
    "maximo_3": "week_5_maximo_3",
    "jogo_nim": "week_6_jogo_nim",
    "imprime_retangulo_cheio": "week_7_retangulo_cheio",
    "imprime_retangulo_vazado": "week_7_retangulo_vazado",
    "conta_primos": "week_7_conta_primos",
    "soma_hipotenusas": "week_7_soma_hipotenusas",
    "remove_repetidos": "week_8_remove_repetidos",
    "soma_elementos": "week_8_soma_elementos",
    "maior_elemento": "week_8_maior_elemento",
    "inverte": "week_8_inverte",
    "coh_piah": "week_9_coh_piah",
}

for url_slug, internal_id in MAPEAMENTO_EXERCICIOS.items():
    # Mapeia a URL com e sem barra no final para evitar redirecionamento 301/307 do Django em POST LTI
    urlpatterns.append(path(f"introcomp2024/{url_slug}", views.lti_grade_endpoint, {"exercise_id": internal_id}, name=f"lti_{url_slug}_no_slash"))
    urlpatterns.append(path(f"introcomp2024/{url_slug}/", views.lti_grade_endpoint, {"exercise_id": internal_id}, name=f"lti_{url_slug}"))

# O simulador local de LTI só é registrado em ambiente de desenvolvimento (DEBUG = True)
if settings.DEBUG:
    urlpatterns.append(path('test-launcher/', views.test_launcher_view, name='test_launcher_view'))