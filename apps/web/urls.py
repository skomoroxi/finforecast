from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("crypto/", views.class_hub, {"code": "crypto"}, name="hub_crypto"),
    path("stocks/", views.class_hub, {"code": "stock"}, name="hub_stock"),
    path("stocks/<slug:country>/", views.country_hub, name="hub_country"),
    path("metals/", views.class_hub, {"code": "metal"}, name="hub_metal"),
    path("energy/", views.class_hub, {"code": "energy"}, name="hub_energy"),
    path("indices-etf/", views.class_hub, {"code": "etf_index"}, name="hub_etf_index"),
    path("currencies/", views.class_hub, {"code": "fx"}, name="hub_fx"),
    path("accuracy/", views.accuracy, name="accuracy"),
    path("compare/", views.comparisons, name="comparisons"),
    path("compare/<slug:slug>/", views.comparison, name="comparison"),
    path("guides/", views.guides, name="guides"),
    path("guides/<slug:slug>/", views.guide, name="guide"),
    path("blog/", views.blog, name="blog"),
    path("blog/<slug:slug>/", views.post, name="post"),
    path("authors/<slug:slug>/", views.author, name="author"),
    path("api/chart/<str:code>.json", views.chart_json, name="chart_json"),
    path("api/live/", views.live_quotes, name="live_quotes"),
    path("methodology/", views.static_page, {"slug": "methodology"}, name="methodology"),
    path("about/", views.static_page, {"slug": "about"}, name="about"),
    path("contact/", views.static_page, {"slug": "contact"}, name="contact"),
    path("disclaimer/", views.static_page, {"slug": "disclaimer"}, name="disclaimer"),
    path("privacy/", views.static_page, {"slug": "privacy"}, name="privacy"),
    path("<slug:slug>/", views.asset_page, name="asset"),
]
