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
