"""'Email this to me': one place's prices for one service, to take along
(Cooper, 2026-11-12).

The email has the prices we show (from the same search, so the numbers match
the site), every price the place published for the codes, the billing codes to
ask about, a link to the hospital's own price file so people can check it
themselves, and plain steps for finding the code in that (often enormous) file.

Privacy: the address is used only to send this one email. The outbox clears the
body once sent and deletes the row after 30 days (mailer.py); nothing else is
kept and nobody is added to a list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, text

from .facilities import facility_detail
from .object_store import ObjectStore
from .search import SearchError, search

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")
MAX_PER_ADDRESS_PER_DAY = 5
MAX_ROWS = 40


class PriceEmailError(ValueError):
    """Bad request; nothing was queued."""


@dataclass(frozen=True, slots=True)
class PriceEmail:
    subject: str
    body: str


def money(value: Decimal | None) -> str:
    """Exact as published: two decimals when the value has at most two, all of
    its digits otherwise (never rounded)."""
    if value is None:
        return "-"
    v = value.normalize()
    exponent = v.as_tuple().exponent
    places = max(2, -exponent) if isinstance(exponent, int) else 2
    if places == 2:
        return f"${value:,.2f}"
    return f"${v:,.{places}f}"


_TEXT: dict[str, dict[str, Any]] = {
    "en": {
        "subject": "Prices for {service} at {place}",
        "intro": "Here are the prices you asked ProcedureScout to send you.",
        "phone": "Phone",
        "paying_cash": "Paying: cash (paying for yourself)",
        "paying_plan": "Paying: {plan}",
        "price": "Price",
        "range": "{low} to {high} (the place published several prices)",
        "hospital_part": "This is the hospital's part (facility fee).",
        "doctor_part": "Doctor's part (billed separately): {p}",
        "cash_instead": "No price was published for your insurance here; this is the cash price.",
        "cash_line": "Cash price: {p}",
        "no_price": "No price of this kind was published here.",
        "codes": "Billing code(s) to ask about: {codes}",
        "all": "Every price this place published for these codes:",
        "more": "...and {n} more (see the link below).",
        "check": "Check it yourself in the hospital's own price file:",
        "no_file": "We don't have a link to this place's own price file.",
        "website": "Hospital website: {w}",
        "how_title": "How to find these prices in the hospital's file",
        "how": [
            "Open the link above, on a computer if you can. The file can be very large "
            "(thousands of rows). A .csv file opens in Excel or Google Sheets; a .json file "
            "opens in a web browser. A .zip file needs to be opened first.",
            "Press Ctrl+F (Windows) or Cmd+F (Mac) and type the code: {code}.",
            "Each matching row is one price. Look for columns named like "
            '"discounted_cash" (the cash price), "gross" (the full price) or '
            '"negotiated_dollar" (an insurance rate). For an insurance rate, the insurer is '
            'in the "payer_name" and "plan_name" columns, or in the column heading itself.',
            "Rows for the same code can differ by setting (inpatient or outpatient) and by "
            'billing class ("facility" is the hospital\'s part, "professional" is the '
            "doctor's part). That's why there can be several prices.",
            "When you call or arrive, give the billing office the code and ask what you will "
            "pay. If you're paying for yourself, you can ask for a written Good Faith Estimate.",
        ],
        "on_site": "See this on ProcedureScout: {url}",
        "fine": "These are prices the place published, not a quote or a bill. What you pay can "
        "differ. Always confirm with the provider before your visit.",
        "why_got": "You got this email because someone asked ProcedureScout to send it to this "
        "address. We used your address only to send it and didn't add you to any list.",
        "types": {
            "discounted_cash": "Cash price",
            "gross": "Full price",
            "negotiated": "Insurance rate",
        },
        "parts": {
            "facility": "hospital's part",
            "both": "hospital's part",
            "professional": "doctor's part",
        },
        "settings": {"inpatient": "inpatient", "outpatient": "outpatient"},
        "their": "their wording",
        "pct": "{p}% of charges",
    },
    "es": {
        "subject": "Precios de {service} en {place}",
        "intro": "Estos son los precios que pidió que ProcedureScout le enviara.",
        "phone": "Teléfono",
        "paying_cash": "Pago: en efectivo (pagando usted mismo)",
        "paying_plan": "Pago: {plan}",
        "price": "Precio",
        "range": "{low} a {high} (el lugar publicó varios precios)",
        "hospital_part": "Esta es la parte del hospital (cargo del centro).",
        "doctor_part": "Parte del médico (se cobra aparte): {p}",
        "cash_instead": "Aquí no se publicó un precio para su seguro; "
        "este es el precio en efectivo.",
        "cash_line": "Precio en efectivo: {p}",
        "no_price": "Aquí no se publicó un precio de este tipo.",
        "codes": "Código(s) de facturación para preguntar: {codes}",
        "all": "Todos los precios que este lugar publicó para estos códigos:",
        "more": "...y {n} más (vea el enlace abajo).",
        "check": "Compruébelo usted mismo en el archivo de precios del hospital:",
        "no_file": "No tenemos un enlace al archivo de precios de este lugar.",
        "website": "Sitio web del hospital: {w}",
        "how_title": "Cómo encontrar estos precios en el archivo del hospital",
        "how": [
            "Abra el enlace de arriba, en una computadora si puede. El archivo puede ser muy "
            "grande (miles de filas). Un archivo .csv se abre en Excel o Google Sheets; un "
            "archivo .json se abre en un navegador. Un archivo .zip hay que abrirlo primero.",
            "Presione Ctrl+F (Windows) o Cmd+F (Mac) y escriba el código: {code}.",
            "Cada fila que coincide es un precio. Busque columnas con nombres como "
            '"discounted_cash" (precio en efectivo), "gross" (precio completo) o '
            '"negotiated_dollar" (tarifa de seguro). Para una tarifa de seguro, la aseguradora '
            'aparece en las columnas "payer_name" y "plan_name", o en el encabezado de la columna.',
            "Las filas del mismo código pueden variar por lugar de atención (hospitalización o "
            'ambulatorio) y por tipo de cargo ("facility" es la parte del hospital, '
            '"professional" es la parte del médico). Por eso puede haber varios precios.',
            "Cuando llame o llegue, dé el código a la oficina de facturación y pregunte cuánto "
            "pagará. Si paga usted mismo, puede pedir un Estimado de Buena Fe por escrito.",
        ],
        "on_site": "Véalo en ProcedureScout: {url}",
        "fine": "Estos son precios que el lugar publicó, no una cotización ni una factura. Lo "
        "que pague puede ser distinto. Confirme siempre con el proveedor antes de su visita.",
        "why_got": "Recibió este correo porque alguien pidió a ProcedureScout que lo enviara a "
        "esta dirección. Usamos su dirección solo para enviarlo y no lo agregamos a ninguna lista.",
        "types": {
            "discounted_cash": "Precio en efectivo",
            "gross": "Precio completo",
            "negotiated": "Tarifa de seguro",
        },
        "parts": {
            "facility": "parte del hospital",
            "both": "parte del hospital",
            "professional": "parte del médico",
        },
        "settings": {"inpatient": "hospitalización", "outpatient": "ambulatorio"},
        "their": "su descripción",
        "pct": "{p}% de los cargos",
    },
}


def price_files(conn: Connection, facility_id: str) -> list[str]:
    """Links to the place's own machine-readable price files (newest first)."""
    rows = conn.execute(
        text(
            "SELECT url FROM src.transparency_source WHERE facility_id = CAST(:f AS uuid) "
            "AND active ORDER BY last_checked_at DESC NULLS LAST, created_at DESC LIMIT 3"
        ),
        {"f": facility_id},
    ).all()
    return [str(r[0]) for r in rows]


def compose(
    conn: Connection,
    store: ObjectStore,
    *,
    facility_id: str,
    service_slug: str | None = None,
    code_system: str | None = None,
    code: str | None = None,
    mode: str = "cash",
    plan_id: str | None = None,
    payer_id: str | None = None,
    payer_raw: str | None = None,
    plan_label: str | None = None,
    lang: str = "en",
    site_url: str = "",
) -> PriceEmail:
    tx = _TEXT["es" if lang == "es" else "en"]
    try:
        d = facility_detail(conn, facility_id)
    except SearchError as exc:
        raise PriceEmailError(str(exc)) from exc
    if d.lat is None or d.lng is None:
        raise PriceEmailError("this place has no map location")
    try:
        res = search(
            conn,
            store,
            latitude=Decimal(d.lat),
            longitude=Decimal(d.lng),
            radius_miles=Decimal(1),
            service_slug=service_slug,
            code_system=code_system,
            code=code,
            mode=mode,
            plan_id=plan_id,
            payer_id=payer_id,
            payer_raw=payer_raw,
        )
    except SearchError as exc:
        raise PriceEmailError(str(exc)) from exc
    f = next((x for x in res.facilities if x.facility_id == d.facility_id), None)
    if f is None or not f.prices:
        raise PriceEmailError("this place hasn't published prices for this")
    service = res.service_name or (f"{code_system} {code}" if code else "")
    out: list[str] = [tx["intro"], "", service.upper() if service else "", ""]
    out.append(d.name)
    addr = ", ".join(x for x in (d.address, d.city, f"{d.state_code} {d.zip5 or ''}".strip()) if x)
    if addr:
        out.append(addr)
    if d.phone:
        out.append(f"{tx['phone']}: {d.phone}")
    out.append("")
    out.append(
        tx["paying_plan"].format(plan=plan_label or res.insurer_unsure or "")
        if mode == "plan"
        else tx["paying_cash"]
    )
    h = f.headline
    if h is None:
        out.append(f"{tx['price']}: {tx['no_price']}")
    else:
        shown = (
            money(h.amount)
            if h.amount == h.highest
            else tx["range"].format(low=money(h.amount), high=money(h.highest))
        )
        out.append(f"{tx['price']}: {shown}")
        if f.no_plan_rate:
            out.append(tx["cash_instead"])
        if f.doctor_fee is not None:
            out.append(tx["hospital_part"])
            doc = (
                money(f.doctor_fee.amount)
                if f.doctor_fee.amount == f.doctor_fee.highest
                else f"{money(f.doctor_fee.amount)}-{money(f.doctor_fee.highest)}"
            )
            out.append(tx["doctor_part"].format(p=doc))
    codes = list(res.codes)
    if codes:
        out += ["", tx["codes"].format(codes=", ".join(codes))]
    out += ["", tx["all"]]
    seen: set[tuple[object, ...]] = set()
    lines: list[str] = []
    for p in f.prices:
        key = (p.price_type, p.payer_name_raw, p.plan_name_raw, p.amount, p.percentage,
               p.setting, p.billing_class, p.description_raw)  # fmt: skip
        if key in seen:
            continue
        seen.add(key)
        bits = [tx["types"].get(p.price_type, p.price_type)]
        if p.payer_name_raw:
            bits.append(" · ".join(x for x in (p.payer_name_raw, p.plan_name_raw) if x))
        if p.billing_class in tx["parts"]:
            bits.append(tx["parts"][p.billing_class])
        if p.setting in tx["settings"]:
            bits.append(tx["settings"][p.setting])
        amount = (
            money(p.amount)
            if p.amount is not None
            else tx["pct"].format(p=format(p.percentage.normalize(), "f"))
            if p.percentage is not None
            else (p.algorithm or "-")
        )
        bits.append(amount)
        if p.description_raw:
            bits.append(f'{tx["their"]}: "{p.description_raw}"')
        lines.append(f"- {p.code_system} {p.code} · " + " · ".join(bits))
    out += lines[:MAX_ROWS]
    if len(lines) > MAX_ROWS:
        out.append(tx["more"].format(n=len(lines) - MAX_ROWS))
    files = price_files(conn, d.facility_id)
    out += ["", tx["check"] if files else tx["no_file"]]
    out += files
    if d.website:
        out.append(tx["website"].format(w=d.website))
    first_code = codes[0].split(" ", 1)[-1] if codes else (code or "")
    out += ["", tx["how_title"].upper()]
    out += [f"{i}. {step.format(code=first_code)}" for i, step in enumerate(tx["how"], 1)]
    if site_url:
        page = f"{site_url.rstrip('/')}/facility/{d.facility_id}"
        if service_slug:
            page += f"?service={service_slug}"
        out += ["", tx["on_site"].format(url=page)]
    out += ["", tx["fine"], "", tx["why_got"]]
    subject = tx["subject"].format(service=service, place=d.name)[:200]
    return PriceEmail(subject, "\n".join(out))


def queue(conn: Connection, to: str, email: PriceEmail) -> None:
    """Put the email in the outbox (portal connection). At most a few a day to
    one address, so the button can't be used to flood someone's inbox."""
    to = to.strip()
    if not EMAIL.match(to) or len(to) > 254:
        raise PriceEmailError("Please enter a valid email address.")
    sent_today = conn.execute(
        text(
            "SELECT count(*) FROM prov.outbox WHERE lower(to_email) = lower(:e) "
            "AND purpose = 'notice' AND created_at > now() - interval '1 day'"
        ),
        {"e": to},
    ).scalar_one()
    if int(sent_today) >= MAX_PER_ADDRESS_PER_DAY:
        raise PriceEmailError("We've already sent several emails to this address today.")
    conn.execute(
        text(
            "INSERT INTO prov.outbox (to_email, purpose, subject, body) "
            "VALUES (:e, 'notice', :s, :b)"
        ),
        {"e": to, "s": email.subject, "b": email.body},
    )
