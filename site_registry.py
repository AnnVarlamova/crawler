from adapters.analysis_sites import CuttingClassAdapter, PatternVaultAdapter
from adapters.product_sites import VikisewsAdapter, GrasserAdapter, SimpleProductAdapter, KorfiatiAdapter
from adapters.generator_sites import SewistAdapter, BootstrapFashionAdapter
from adapters.generic import GenericAdapter


ADAPTERS = [
    CuttingClassAdapter(),
    PatternVaultAdapter(),
    VikisewsAdapter(),
    GrasserAdapter(),
    KorfiatiAdapter(),
    SewistAdapter(),
    BootstrapFashionAdapter(),

    SimpleProductAdapter("moodfabrics.com", "moodfabrics"),
    SimpleProductAdapter("thefoldline.com", "thefoldline"),
    SimpleProductAdapter("www.thefoldline.com", "thefoldline"),
    SimpleProductAdapter("simplicity.com", "simplicity"),
    SimpleProductAdapter("www.simplicity.com", "simplicity"),
    SimpleProductAdapter("tessuti-shop.com", "tessuti"),
    SimpleProductAdapter("stylearc.com", "stylearc"),
    SimpleProductAdapter("marfy.it", "marfy"),
    SimpleProductAdapter("lekala.co", "lekala"),
    SimpleProductAdapter("tianascloset.com", "tiana"),
    SimpleProductAdapter("burdastyle.ru", "burda"),
    SimpleProductAdapter("shkatulka-sew.ru", "shkatulka"),
    SimpleProductAdapter("etsy.com", "etsy"),
    SimpleProductAdapter("www.etsy.com", "etsy"),

    GenericAdapter(),
]


def get_adapter(domain: str):
    for adapter in ADAPTERS:
        if adapter.match(domain):
            return adapter
    return GenericAdapter()
