"""Reference data: suppliers, products, customers, and the hidden truth behind them.

Everything here is fictional. Names come from Faker plus stone-trade suffixes; costs, prices,
lead times and demand weights are drawn from distributions in config.yaml. The "truth"
columns (true lead-time distribution, demand weights, churn dates, duplicate mappings) are
written to data/_truth/ and never to the raw ERP tables.

Arrays are aligned by position: product i is row i of `products`, customer c is row c of
`customers`. The simulation works on these integer positions for speed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from faker import Faker

from generator.config import Config, Show, load_shows
from generator.randomness import reference_rng

# --- Catalog definitions -------------------------------------------------------------------

# material -> (SKU code, plausible origin countries)
MATERIALS: dict[str, tuple[str, list[str]]] = {
    "amethyst": ("AMT", ["Brazil", "Madagascar", "Morocco"]),
    "rose quartz": ("RSQ", ["Madagascar", "Brazil", "India"]),
    "clear quartz": ("CLQ", ["Brazil", "Madagascar", "China", "USA"]),
    "agate": ("AGT", ["Brazil", "India", "Mexico"]),
    "jasper": ("JSP", ["India", "Madagascar", "USA"]),
    "labradorite": ("LAB", ["Madagascar", "India"]),
    "lapis lazuli": ("LAP", ["India", "China"]),
    "malachite": ("MAL", ["Morocco", "China"]),
    "tiger eye": ("TGE", ["India", "China"]),
    "obsidian": ("OBS", ["Mexico", "USA"]),
    "selenite": ("SEL", ["Morocco", "Mexico"]),
    "citrine": ("CIT", ["Brazil", "Madagascar"]),
    "fluorite": ("FLU", ["China", "Mexico", "Morocco"]),
    "pyrite": ("PYR", ["China", "Morocco", "USA"]),
    "jade": ("JAD", ["China", "USA"]),
    "turquoise": ("TRQ", ["USA", "China", "Mexico"]),
    "onyx": ("ONX", ["Mexico", "Morocco", "India"]),
    "marble": ("MRB", ["India", "Mexico", "USA"]),
    "calcite": ("CAL", ["Mexico", "Madagascar", "Morocco"]),
    "aventurine": ("AVN", ["India", "Brazil"]),
    "carnelian": ("CRN", ["India", "Madagascar"]),
    "moonstone": ("MNS", ["India"]),
    "hematite": ("HEM", ["China", "Brazil"]),
    "rhodonite": ("RHD", ["Brazil", "Madagascar"]),
    "sodalite": ("SOD", ["Brazil", "Madagascar"]),
    "smoky quartz": ("SMQ", ["Brazil", "Madagascar"]),
    "garnet": ("GRN", ["India", "Madagascar"]),
    "tourmaline": ("TRM", ["Brazil", "Madagascar"]),
    "petrified wood": ("PWD", ["Madagascar", "USA", "Morocco"]),
    "river rock": ("RVR", ["Mexico", "USA"]),
}

_GEMS = [m for m in MATERIALS if m not in ("marble", "river rock", "petrified wood")]


@dataclass(frozen=True)
class CategorySpec:
    code: str
    uom: str
    mix_weight: float  # share of SKUs in this category
    cost_median_usd: float
    cost_sigma: float
    markup_range: tuple[float, float]
    case_packs: tuple[int, ...]
    case_pack_weights: tuple[float, ...]
    units_per_line: float  # typical ordered quantity per order line, in UoM
    forms: tuple[str, ...]
    materials: tuple[str, ...]
    is_show_category: bool = True


CATEGORIES: dict[str, CategorySpec] = {
    "Polished Stones": CategorySpec(
        code="PLS", uom="each", mix_weight=0.25,
        cost_median_usd=8.0, cost_sigma=0.7, markup_range=(2.2, 3.0),
        case_packs=(1, 6, 12), case_pack_weights=(0.5, 0.3, 0.2), units_per_line=8,
        forms=("Polished Point", "Sphere", "Palm Stone", "Heart", "Tower", "Pyramid"),
        materials=tuple(_GEMS),
    ),
    "Rough Minerals": CategorySpec(
        code="RGH", uom="lb", mix_weight=0.12,
        cost_median_usd=4.0, cost_sigma=0.6, markup_range=(1.8, 2.4),
        case_packs=(1, 50), case_pack_weights=(0.6, 0.4), units_per_line=30,
        forms=("Rough Chunks", "Raw Specimen", "Rough Slab"),
        materials=tuple(MATERIALS),
    ),
    "Crystal Clusters": CategorySpec(
        code="CLU", uom="each", mix_weight=0.15,
        cost_median_usd=25.0, cost_sigma=0.8, markup_range=(2.0, 2.8),
        case_packs=(1, 6), case_pack_weights=(0.7, 0.3), units_per_line=4,
        forms=("Cluster", "Geode", "Druzy Cluster"),
        materials=("amethyst", "clear quartz", "citrine", "fluorite", "pyrite", "calcite", "smoky quartz"),
    ),
    "Tumbled Stones": CategorySpec(
        code="TMB", uom="lb", mix_weight=0.15,
        cost_median_usd=6.0, cost_sigma=0.5, markup_range=(2.0, 3.0),
        case_packs=(1, 50), case_pack_weights=(0.6, 0.4), units_per_line=25,
        forms=("Tumbled Stones", "Tumbled Chips"),
        materials=tuple(_GEMS),
    ),
    "Jewelry Components": CategorySpec(
        code="JWL", uom="each", mix_weight=0.20,
        cost_median_usd=1.5, cost_sigma=0.7, markup_range=(2.5, 3.5),
        case_packs=(12, 24, 50), case_pack_weights=(0.4, 0.35, 0.25), units_per_line=72,
        forms=("Round Beads 6mm", "Round Beads 8mm", "Chip Beads", "Pendant Blank", "Cabochon"),
        materials=tuple(_GEMS),
    ),
    "Decor & Landscape": CategorySpec(
        code="DEC", uom="lb", mix_weight=0.13,
        cost_median_usd=0.8, cost_sigma=0.6, markup_range=(1.8, 2.5),
        case_packs=(50,), case_pack_weights=(1.0,), units_per_line=400,
        forms=("Landscape Pebbles", "Garden Boulders", "Decorative Slab", "Bookends"),
        materials=("marble", "river rock", "petrified wood", "onyx", "selenite", "calcite", "jasper", "agate"),
        is_show_category=False,  # bulky landscape stone isn't taken to gem shows
    ),
}  # fmt: skip
CATEGORY_NAMES = list(CATEGORIES)

PRODUCT_SETUP_DAYS_BEFORE_LAUNCH = 180

SIZES = ("Small", "Medium", "Large", "Grade A", "Grade AA")

COUNTRY_CURRENCY = {
    "India": "INR",
    "Brazil": "BRL",
    "China": "CNY",
    "Madagascar": "MGA",
    "Mexico": "MXN",
    "Morocco": "MAD",
    "USA": "USD",
}
SUPPLIER_SUFFIXES = {
    "India": ["Gems Export", "Crystal Exports Pvt Ltd", "Agate Industries"],
    "Brazil": ["Minerals Ltda", "Pedras Ltda", "Gemas do Brasil Ltda"],
    "China": ["Stone Craft Co.", "Crystal Trading Co.", "Mineral Arts Co."],
    "Madagascar": ["Mineraux SARL", "Pierres SARL"],
    "Mexico": ["Minerales S.A.", "Piedras S.A. de C.V."],
    "Morocco": ["Fossils & Minerals SARL", "Atlas Stones SARL"],
    "USA": ["Stone Supply", "Rock & Mineral Co.", "Lapidary Supply"],
}

# Customer types: order-frequency multiplier, quantity multiplier, extra lines multiplier,
# show attendance propensity, and category affinity (same order as CATEGORY_NAMES).
CUSTOMER_TYPES = {
    # type:               freq, qty,  lines, show, affinity PLS RGH  CLU  TMB  JWL  DEC
    "retail_shop":        (1.0, 1.0, 1.0, 1.0, (1.2, 0.8, 1.2, 1.3, 0.6, 0.4)),
    "jewelry_maker":      (1.1, 1.0, 0.8, 1.2, (0.5, 0.3, 0.3, 0.4, 3.0, 0.1)),
    "online_reseller":    (1.3, 1.0, 1.0, 0.8, (1.2, 0.8, 1.0, 1.2, 1.0, 0.3)),
    "interior_designer":  (0.6, 0.8, 0.7, 0.4, (0.8, 0.4, 1.2, 0.3, 0.1, 2.5)),
    "landscaper":         (0.7, 1.5, 0.6, 0.1, (0.1, 0.4, 0.1, 0.3, 0.05, 4.0)),
    "wholesaler":         (0.8, 2.5, 1.5, 1.0, (1.0, 1.0, 1.0, 1.0, 1.0, 1.0)),
    "metaphysical_store": (1.0, 0.8, 1.0, 1.5, (1.5, 0.8, 1.4, 1.4, 0.6, 0.1)),
}  # fmt: skip
CUSTOMER_TYPE_NAMES = list(CUSTOMER_TYPES)
CUSTOMER_SUFFIXES = {
    "retail_shop": ["Rock & Gem Shop", "Rock Shop", "Gem Gallery", "Stone Emporium"],
    "jewelry_maker": ["Jewelry Studio", "Designs", "Beadworks", "Metalsmiths"],
    "online_reseller": ["Crystals Online", "Gem Co.", "Stone Shop", "Treasures"],
    "interior_designer": ["Interiors", "Design Studio", "Home & Living"],
    "landscaper": ["Landscaping", "Hardscapes", "Garden Design"],
    "wholesaler": ["Wholesale", "Distributors", "Trading Co."],
    "metaphysical_store": ["Crystal Healing", "Metaphysical Shop", "Spirit Stones", "Moon Shop"],
}
STATE_WEIGHTS = {"CA": 0.22, "AZ": 0.08, "TX": 0.09, "CO": 0.06, "FL": 0.07, "NY": 0.07, "OR": 0.05, "WA": 0.05}  # fmt: skip
OTHER_STATES = ["NV", "UT", "NM", "IL", "MA", "GA", "NC", "PA", "OH", "MI", "MN", "VA", "NJ", "TN", "MO", "WI", "HI", "MT", "ID", "MD"]  # fmt: skip
CREDIT_TERMS = ["PREPAID", "NET30", "NET60"]
SALES_REPS = ["REP-01", "REP-02", "REP-03", "REP-04"]


@dataclass
class Reference:
    """All reference data. Row position doubles as the integer ID used by the simulation."""

    warehouses: pd.DataFrame
    suppliers: pd.DataFrame  # includes truth columns (dropped before writing raw)
    products: pd.DataFrame  # includes truth columns
    customers: pd.DataFrame  # includes truth columns and duplicate records
    shows: list[Show]
    show_multipliers: np.ndarray  # demand multiplier per show (truth)
    product_created_ts: np.ndarray  # when each product was set up in the ERP


# --- Helpers -------------------------------------------------------------------------------


def _random_dates(rng: np.random.Generator, start: date, end: date, n: int) -> list[date]:
    span = (end - start).days
    offsets = rng.integers(0, max(span, 1) + 1, n)
    return [start + timedelta(days=int(o)) for o in offsets]


def _steady_dates(rng: np.random.Generator, start: date, end: date, n: int) -> list[date]:
    """n dates that arrive steadily: one per equal slice of [start, end], jittered within it.
    (Pure random draws can leave long gaps by chance, e.g. no new customers for months.)"""
    span = (end - start).days
    offsets = ((np.arange(n) + rng.random(n)) * span / max(n, 1)).astype(int)
    return [start + timedelta(days=int(o)) for o in offsets]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def solve_zipf_exponent(n: int, top_share: float) -> float:
    """Find s so that the top 20% of ranks under weights r**-s hold `top_share` of the total."""
    ranks = np.arange(1, n + 1, dtype=float)
    top_n = max(1, round(0.2 * n))
    lo, hi = 0.0, 5.0
    for _ in range(60):
        mid = (lo + hi) / 2
        w = ranks**-mid
        share = w[:top_n].sum() / w.sum()
        if share < top_share:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# --- Builders ------------------------------------------------------------------------------


def build_suppliers(cfg: Config, rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    n = cfg.scale.n_suppliers
    countries = list(cfg.reference["supplier_country_weights"])
    weights = np.array(list(cfg.reference["supplier_country_weights"].values()))
    country = rng.choice(countries, n, p=weights / weights.sum())

    rows = []
    for i in range(n):
        c = str(country[i])
        if c == "USA":
            lt_mean = rng.uniform(10, 20)
        elif c == "Mexico":
            lt_mean = rng.uniform(20, 35)
        else:
            lt_mean = rng.uniform(45, 110)
        unreliable = rng.random() < cfg.reference["unreliable_supplier_share"]
        if unreliable:
            lt_sigma = rng.uniform(0.35, 0.55)
            quoted = lt_mean * rng.uniform(0.65, 0.90)
            short_prob = rng.uniform(0.05, 0.15)
        else:
            lt_sigma = rng.uniform(0.10, 0.22)
            quoted = lt_mean * rng.uniform(0.80, 0.97)
            short_prob = rng.uniform(0.0, 0.05)
        suffix = SUPPLIER_SUFFIXES[c][int(rng.integers(len(SUPPLIER_SUFFIXES[c])))]
        rows.append(
            {
                "supplier_id": f"SUP-{i + 1:04d}",
                "supplier_name": f"{fake.last_name()} {suffix}",
                "country": c,
                "currency": COUNTRY_CURRENCY[c],
                "payment_terms": str(rng.choice(["PREPAID", "NET30", "NET60", "50_50"])),
                "min_order_value_usd": float(round(rng.uniform(500, 10_000), -1)),
                "created_at": cfg.scale.start_date - timedelta(days=int(rng.integers(200, 3000))),
                # truth
                "true_lead_time_mean_days": round(lt_mean, 2),
                "true_lead_time_sigma": round(lt_sigma, 4),
                "quoted_lead_time_days": max(3, round(quoted)),
                "short_ship_prob": round(short_prob, 4),
                "is_unreliable": bool(unreliable),
            }
        )
    return pd.DataFrame(rows)


def build_products(cfg: Config, rng: np.random.Generator, suppliers: pd.DataFrame) -> pd.DataFrame:
    n = cfg.scale.n_skus
    start = cfg.scale.start_date
    n_days = cfg.scale.n_days
    mix = np.array([CATEGORIES[c].mix_weight for c in CATEGORY_NAMES])
    cat_idx = rng.choice(len(CATEGORY_NAMES), n, p=mix / mix.sum())

    rows = []
    for i in range(n):
        cat_name = CATEGORY_NAMES[cat_idx[i]]
        spec = CATEGORIES[cat_name]
        material = str(rng.choice(spec.materials))
        mat_code, origins = MATERIALS[material]
        candidates = suppliers.index[suppliers["country"].isin(origins)].to_numpy()
        if len(candidates) == 0:
            candidates = suppliers.index.to_numpy()
        supplier_pos = int(rng.choice(candidates))
        cost = max(0.05, float(np.exp(rng.normal(np.log(spec.cost_median_usd), spec.cost_sigma))))
        markup = rng.uniform(*spec.markup_range)
        case_pack = int(rng.choice(spec.case_packs, p=np.array(spec.case_pack_weights)))
        rows.append(
            {
                "sku": f"{mat_code}-{spec.code}-{i + 1:04d}",
                "product_name": f"{material.title()} {rng.choice(spec.forms)}, {rng.choice(SIZES)}",
                "category": cat_name,
                "material": material,
                "supplier_pos": supplier_pos,
                "primary_supplier_id": suppliers.at[supplier_pos, "supplier_id"],
                "unit_of_measure": spec.uom,
                "unit_cost_usd": round(cost, 2),
                "markup": round(markup, 4),
                "list_price_usd": round(cost * markup, 2),
                "case_pack_qty": case_pack,
                "category_pos": int(cat_idx[i]),
                "is_show_category": spec.is_show_category,
            }
        )
    products = pd.DataFrame(rows)

    # Launch and discontinuation dates
    launched_in_range = rng.random(n) < cfg.reference["launched_in_range_share"]
    launch = [
        start + timedelta(days=int(rng.integers(0, max(1, n_days - 90))))
        if launched_in_range[i]
        else start - timedelta(days=int(rng.integers(30, 1500)))
        for i in range(n)
    ]
    products["launch_date"] = launch
    disc_candidates = np.flatnonzero(~launched_in_range)
    n_disc = round(cfg.reference["discontinued_in_range_share"] * n)
    disc_pos = rng.choice(disc_candidates, n_disc, replace=False)
    products["discontinued_date"] = None
    for p in disc_pos:
        products.at[p, "discontinued_date"] = start + timedelta(
            days=int(rng.integers(60, max(61, n_days - 30)))
        )
    products["discontinued_date"] = products["discontinued_date"].astype(object)

    # Demand weights (truth): Zipf revenue targets assigned to SKUs at random
    s = solve_zipf_exponent(n, cfg.demand["top20_revenue_share"])
    rank = rng.permutation(n) + 1
    revenue_weight = rank.astype(float) ** -s
    products["revenue_weight"] = revenue_weight / revenue_weight.sum()
    products["revenue_rank"] = rank
    products["zipf_exponent"] = round(s, 4)
    # A-class in truth: top SKUs holding 80% of target revenue (used for cycle-count frequency)
    order = np.argsort(-products["revenue_weight"].to_numpy())
    cum = np.cumsum(products["revenue_weight"].to_numpy()[order])
    is_a = np.zeros(n, dtype=bool)
    is_a[order[cum <= 0.80]] = True
    is_a[order[0]] = True
    products["is_a_class_truth"] = is_a
    return products


def build_customers(
    cfg: Config, rng: np.random.Generator, fake: Faker
) -> tuple[pd.DataFrame, dict[int, int]]:
    """Customers plus planted duplicate records (issue 1). Returns (customers, dup_of map)."""
    n = cfg.scale.n_customers
    start, end = cfg.scale.start_date, cfg.scale.end_date
    types = CUSTOMER_TYPE_NAMES
    tw = np.array([cfg.reference["customer_type_weights"][t] for t in types])
    ctype = rng.choice(types, n, p=tw / tw.sum())

    n_existing = round(n * cfg.reference["customers_existing_at_start_share"])
    created = _random_dates(
        rng, start - timedelta(days=2000), start - timedelta(days=30), n_existing
    )
    created += _steady_dates(rng, start, end - timedelta(days=7), n - n_existing)

    state_names = list(STATE_WEIGHTS) + OTHER_STATES
    other_w = (1 - sum(STATE_WEIGHTS.values())) / len(OTHER_STATES)
    state_p = np.array(list(STATE_WEIGHTS.values()) + [other_w] * len(OTHER_STATES))

    rows = []
    used_names: set[str] = set()
    for i in range(n):
        t = str(ctype[i])
        while True:
            prefix = fake.last_name() if rng.random() < 0.6 else fake.city()
            suffix = CUSTOMER_SUFFIXES[t][int(rng.integers(len(CUSTOMER_SUFFIXES[t])))]
            name = f"{prefix} {suffix}"
            if name not in used_names:
                used_names.add(name)
                break
        terms_p = [0.15, 0.45, 0.40] if t == "wholesaler" else [0.25, 0.55, 0.20]
        freq_mult = CUSTOMER_TYPES[t][0]
        rows.append(
            {
                "customer_name": name,
                "customer_type": t,
                "contact_email": f"{_slug(prefix)}{int(rng.integers(1, 99))}@{fake.free_email_domain()}",
                "state": str(rng.choice(state_names, p=state_p / state_p.sum())),
                "credit_terms": str(rng.choice(CREDIT_TERMS, p=terms_p)),
                "sales_rep_id": str(rng.choice(SALES_REPS)),
                "created_date": created[i],
                "order_rate_raw": float(rng.gamma(1.2, 1.0) * freq_mult),
                "churn_date": None,
                "duplicate_of_pos": -1,
            }
        )
    customers = pd.DataFrame(rows)

    # Churn: some customers stop ordering during the range
    eligible = np.flatnonzero(customers["created_date"] < end - timedelta(days=120))
    n_churn = round(cfg.demand["customer_churn_share"] * n)
    for c in rng.choice(eligible, min(n_churn, len(eligible)), replace=False):
        first = max(customers.at[c, "created_date"], start) + timedelta(days=60)
        customers.at[c, "churn_date"] = first + timedelta(
            days=int(rng.integers(0, max(1, (end - first).days)))
        )

    # Planted issue 1: duplicate customer records (same business, name variant, same email)
    n_dup = max(1, round(cfg.planted_issues["duplicate_customers"] * n))
    dup_rows = []
    candidates = np.flatnonzero(customers["created_date"] < end - timedelta(days=120))
    for c in rng.choice(candidates, n_dup, replace=False):
        orig = customers.loc[c]
        lo = max(orig["created_date"], start) + timedelta(days=30)
        hi = (orig["churn_date"] or end) - timedelta(days=30)
        if hi <= lo:
            continue
        dup_date = lo + timedelta(days=int(rng.integers(0, (hi - lo).days)))
        dup_rows.append(
            {
                **orig.to_dict(),
                "customer_name": name_variant(orig["customer_name"], rng),
                "created_date": dup_date,
                "order_rate_raw": 0.0,  # never orders on its own; receives some of the original's orders
                "churn_date": None,
                "duplicate_of_pos": int(c),
            }
        )
    customers = pd.concat([customers, pd.DataFrame(dup_rows)], ignore_index=True)

    # Assign IDs in order of creation so IDs grow over time, like a real ERP
    customers["_orig_pos"] = np.arange(len(customers))
    customers = customers.sort_values(["created_date", "_orig_pos"], kind="stable").reset_index(
        drop=True
    )
    new_pos = {int(o): i for i, o in enumerate(customers["_orig_pos"])}
    customers["duplicate_of_pos"] = [
        new_pos[d] if d >= 0 else -1 for d in customers["duplicate_of_pos"]
    ]
    customers["customer_id"] = [f"CUS-{i + 1:05d}" for i in range(len(customers))]
    customers["first_order_date"] = customers["created_date"]
    customers = customers.drop(columns="_orig_pos")
    dup_of = {
        int(orig): int(dup) for dup, orig in enumerate(customers["duplicate_of_pos"]) if orig >= 0
    }
    return customers, dup_of


def name_variant(name: str, rng: np.random.Generator) -> str:
    """Return a plausible re-keyed variant of a business name ("&" vs "and", LLC, casing)."""
    options = []
    if " & " in name:
        options.append(name.replace(" & ", " and "))
    if " and " in name:
        options.append(name.replace(" and ", " & "))
    options += [f"{name} LLC", f"{name}, Inc.", name.upper(), name.replace(".", ""), f"{name} Co"]
    options = [o for o in options if o != name]
    return options[int(rng.integers(len(options)))]


def build_reference(cfg: Config) -> Reference:
    rng = reference_rng(cfg.seed)
    fake = Faker("en_US")
    fake.seed_instance(cfg.seed)

    warehouses = pd.DataFrame(cfg.warehouses)
    suppliers = build_suppliers(cfg, rng, fake)
    products = build_products(cfg, rng, suppliers)
    customers, _ = build_customers(cfg, rng, fake)
    shows = load_shows(cfg)
    lo, hi = cfg.demand["show_multiplier_range"]
    show_multipliers = rng.uniform(lo, hi, len(shows))

    # ERP "created" timestamp for products: before launch by more than the longest lead time,
    # because the buyer places the first purchase order ahead of launch.
    created = [
        pd.Timestamp(d)
        - pd.Timedelta(days=PRODUCT_SETUP_DAYS_BEFORE_LAUNCH)
        + pd.Timedelta(hours=9)
        for d in products["launch_date"]
    ]
    return Reference(
        warehouses=warehouses,
        suppliers=suppliers,
        products=products,
        customers=customers,
        shows=shows,
        show_multipliers=show_multipliers,
        product_created_ts=np.array(created, dtype="datetime64[s]"),
    )
