#!/usr/bin/env python3
"""Monitor prezzi PS5: legge le pagine prodotto dei negozi, tiene lo storico
e genera index.html con il prezzo migliore per ogni versione.

Uso:  python3 ps5_monitor.py
Solo libreria standard di Python 3.8+, nessuna installazione necessaria.
"""
import datetime
import html
import json
import os
import pathlib
import re
import time
import urllib.request

# ---- CONFIGURAZIONE ------------------------------------------------------
# Incolla l'indirizzo esatto della pagina prodotto di ogni negozio.
# Le voci lasciate vuote vengono saltate.
PRODOTTI = {
    "PS5 Digital Edition": {
        "listino": 599.99,
        "pagine": {
            "Amazon": "",
            "MediaWorld": "https://www.mediaworld.it/it/product/_sony-ps5-dig-e-chassis-825gb-white-528663.html",
            "Unieuro": "https://www.unieuro.it/online/Console-Playstation-5/PlayStation-5-Digital-Edition-pidSON1000049749",
            "Euronics": "",
        },
    },
    "PS5 Slim con lettore": {
        "listino": 649.99,
        "pagine": {
            "Amazon": "",
            "MediaWorld": "https://www.mediaworld.it/it/product/_sony-ps5-disc-e-chassis-white-528652.html",
            "Unieuro": "",
            "Euronics": "",
        },
    },
    "PS5 Pro": {
        "listino": 899.99,
        "pagine": {
            "Amazon": "",
            "MediaWorld": "https://www.mediaworld.it/it/product/_sony-playstation-5-pro-2tb-white-548489.html",
            "Unieuro": "https://www.unieuro.it/online/Console-Playstation-5/PlayStation-5-Pro-pidSON1000050720",
            "Euronics": "",
        },
    },
}
CARTELLA = pathlib.Path(__file__).resolve().parent
STORICO = CARTELLA / "prices.json"
PAGINA = CARTELLA / "index.html"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")  # opzionale: notifica sul telefono con ntfy.sh
PAUSA_SECONDI = 5  # pausa tra una richiesta e l'altra, per non sovraccaricare i negozi
VALIDITA_ORE = 72  # un prezzo piu' vecchio di cosi' non viene considerato
# --------------------------------------------------------------------------

UA = "Mozilla/5.0 (compatible; ps5-monitor personale)"
# --- fine parte 1 ---
def scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "it-IT,it;q=0.9"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="replace")


def numero(valore):
    s = str(valore).strip().replace("\u20ac", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    return float(s)


def cerca_offerte(nodo, trovate):
    """Scorre il JSON-LD e raccoglie (prezzo, disponibile) dagli 'offers' schema.org."""
    if isinstance(nodo, list):
        for x in nodo:
            cerca_offerte(x, trovate)
    elif isinstance(nodo, dict):
        if "offers" in nodo:
            for o in nodo["offers"] if isinstance(nodo["offers"], list) else [nodo["offers"]]:
                if isinstance(o, dict):
                    p = o.get("price", o.get("lowPrice"))
                    if p not in (None, ""):
                        disp = "OutOfStock" not in str(o.get("availability", ""))
                        trovate.append((numero(p), disp))
        for v in nodo.values():
            if isinstance(v, (dict, list)):
                cerca_offerte(v, trovate)


def estrai_prezzo(testo):
    """Ritorna (prezzo, disponibile) oppure None."""
    trovate = []
    for blocco in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', testo, re.S | re.I):
        try:
            cerca_offerte(json.loads(blocco), trovate)
        except (ValueError, TypeError):
            continue
    if trovate:
        return trovate[0]
    m = re.search(r'(?:itemprop="price"|property="product:price:amount")[^>]*content="([\d.,]+)"', testo)
    return (numero(m.group(1)), True) if m else None


def carica_storico():
    return json.loads(STORICO.read_text()) if STORICO.exists() else {}


def registra(storico, modello, negozio, prezzo, ora):
    serie = storico.setdefault(modello, {}).setdefault(negozio, [])
    if not serie or serie[-1][1] != prezzo or ora - datetime.datetime.fromisoformat(serie[-1][0]) > datetime.timedelta(hours=24):
        serie.append([ora.isoformat(timespec="minutes"), prezzo])
        del serie[:-2000]


def ultimi_prezzi(storico, modello, ora):
    out = {}
    for negozio, serie in storico.get(modello, {}).items():
        if serie and serie[-1][1] is not None:
            quando = datetime.datetime.fromisoformat(serie[-1][0])
            if ora - quando <= datetime.timedelta(hours=VALIDITA_ORE):
                out[negozio] = serie[-1][1]
    return out


def minimo_storico(storico, modello):
    tutti = [p for s in storico.get(modello, {}).values() for _, p in s if p is not None]
    return min(tutti) if tutti else None
# --- fine parte 2 ---
def notifica(testo):
    print(testo)
    if NTFY_TOPIC:
        req = urllib.request.Request("https://ntfy.sh/" + NTFY_TOPIC, data=testo.encode("utf-8"))
        try:
            urllib.request.urlopen(req, timeout=15)
        except OSError as e:
            print("Notifica non inviata:", e)


def genera_pagina(storico, ora):
    righe = []
    for modello, conf in PRODOTTI.items():
        prezzi = ultimi_prezzi(storico, modello, ora)
        righe.append("<h2>%s</h2><p>Listino: %.2f &euro;</p>" % (html.escape(modello), conf["listino"]))
        if not prezzi:
            righe.append("<p>Nessun prezzo recente.</p>")
            continue
        migliore = min(prezzi, key=prezzi.get)
        righe.append("<table>")
        for negozio, p in sorted(prezzi.items(), key=lambda x: x[1]):
            classe = ' class="best"' if negozio == migliore and len(prezzi) > 1 else ""
            righe.append("<tr%s><td>%s</td><td>%.2f &euro;</td></tr>" % (classe, html.escape(negozio), p))
        righe.append("</table>")
        mn = minimo_storico(storico, modello)
        if mn is not None:
            righe.append("<p>Minimo registrato: %.2f &euro;</p>" % mn)
    PAGINA.write_text(
        '<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Prezzi PS5</title><style>body{font:16px/1.5 system-ui,sans-serif;max-width:560px;margin:auto;padding:16px}"
        "table{width:100%%;border-collapse:collapse}td{padding:8px;border-bottom:1px solid #8884}"
        "td:last-child{text-align:right}.best{background:#0a7d4f22;font-weight:700}</style></head><body>"
        "<h1>PlayStation 5: prezzi</h1><p>Aggiornato: %s</p>%s</body></html>"
        % (ora.strftime("%d/%m/%Y %H:%M"), "".join(righe)),
        encoding="utf-8",
    )


def main():
    ora = datetime.datetime.now()
    storico = carica_storico()
    for modello, conf in PRODOTTI.items():
        minimo_prima = minimo_storico(storico, modello)
        for negozio, url in conf["pagine"].items():
            if not url:
                continue
            try:
                risultato = estrai_prezzo(scarica(url))
            except Exception as e:  # rete, pagina cambiata, blocco del negozio
                print("%s / %s: errore (%s)" % (modello, negozio, e))
                risultato = None
            time.sleep(PAUSA_SECONDI)
            if not risultato:
                print("%s / %s: prezzo non trovato" % (modello, negozio))
                continue
            prezzo, disponibile = risultato
            if not disponibile:
                print("%s / %s: non disponibile" % (modello, negozio))
                continue
            registra(storico, modello, negozio, prezzo, ora)
            print("%s / %s: %.2f EUR" % (modello, negozio, prezzo))
            if minimo_prima is not None and prezzo < minimo_prima:
                notifica("Nuovo minimo per %s: %.2f EUR su %s" % (modello, prezzo, negozio))
                minimo_prima = prezzo
    STORICO.write_text(json.dumps(storico, ensure_ascii=False, indent=1))
    genera_pagina(storico, ora)


if __name__ == "__main__":
    main()
