"""Descarga las carteleras y las deja en data/<id>.json (lo ejecuta GitHub Actions).

La web no puede pedirlas desde el navegador porque Sensacine no permite CORS.
"""
import html
import json
import pathlib
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DIAS = 7
RAIZ = pathlib.Path(__file__).parent
VERSIONES = {"ORIGINAL": "VOSE", "DUBBED": "Doblada"}


def leer(url, accept):
    pet = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Linux; Android 13) Cinorro/1.0", "Accept": accept})
    with urllib.request.urlopen(pet, timeout=20) as r:
        return r.read().decode("utf-8")


def sensacine(cine_id, dia):
    pelis, pagina, total = [], 1, 1
    while pagina <= total:
        ruta = f"https://www.sensacine.com/_/showtimes/theater-{cine_id}/d-{dia}/"
        if pagina > 1:
            ruta += f"p-{pagina}/"
        datos = json.loads(leer(ruta, "application/json"))
        if datos.get("error"):
            return pelis
        total = (datos.get("pagination") or {}).get("totalPages") or 1
        for r in datos.get("results") or []:
            peli = r.get("movie") or {}
            titulo = (peli.get("title") or "").strip()
            sesiones, vistos = [], set()
            for lista in (r.get("showtimes") or {}).values() if titulo else []:
                for s in lista or []:
                    inicio = (s.get("startsAt") or "")[:16]
                    if not inicio or s.get("internalId") in vistos:
                        continue
                    vistos.add(s.get("internalId"))
                    sesiones.append({"inicio": inicio, "version": VERSIONES.get(s.get("diffusionVersion"), "Español")})
            if sesiones:
                pelis.append({"titulo": titulo, "duracion": peli.get("runtime") or "",
                              "sesiones": sorted(sesiones, key=lambda s: s["inicio"])})
        pagina += 1
    return pelis


def taquilla(base, dia):
    """Respaldo para los cines sin datos en Sensacine."""
    pagina = leer(f"{base}?t10city=Madrid&t10d={dia}", "text/html")
    pelis = []
    for bloque in pagina.split('<div class="list-films__result">')[1:]:
        m = re.search(r'<h3 class="film-title"><a[^>]*>(.*?)</a>', bloque, re.S)
        if not m:
            continue
        titulo = re.sub(r"<span>.*?</span>|<[^>]+>", "", m.group(1), flags=re.S)
        titulo = html.unescape(titulo).strip()
        horas = re.findall(r'data-vars-ga-label="[^"#]*#(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})#link"', bloque)
        horas = sorted({h for d, h in horas if d == dia})
        if titulo and horas:
            pelis.append({"titulo": titulo, "duracion": "",
                          "sesiones": [{"inicio": f"{dia}T{h}", "version": "Sesiones"} for h in horas]})
    return pelis


def main():
    ahora = datetime.now(ZoneInfo("Europe/Madrid"))
    salida = RAIZ / "data"
    salida.mkdir(exist_ok=True)
    con_datos = 0
    for cine in json.loads((RAIZ / "cines.json").read_text(encoding="utf-8")):
        dias = {}
        for n in range(DIAS):
            dia = (ahora + timedelta(days=n)).date().isoformat()
            res = {"fuente": "Sensacine", "pelis": []}
            try:
                res["pelis"] = sensacine(cine["id"], dia)
            except Exception as e:
                res["error"] = str(e)
            if not res["pelis"] and cine.get("taquilla"):
                try:
                    otras = taquilla(cine["taquilla"], dia)
                    if otras:
                        res = {"fuente": "Taquilla.com", "pelis": otras}
                except Exception as e:
                    res["error"] = str(e)
            dias[dia] = res
        total = sum(len(d["pelis"]) for d in dias.values())
        errores = [d["error"] for d in dias.values() if "error" in d]
        print(f"{cine['nombre']}: {total} películas/día, {len(errores)} errores {errores[:1]}")
        con_datos += total > 0
        (salida / f"{cine['id']}.json").write_text(
            json.dumps({"actualizado": ahora.isoformat(timespec="minutes"), "dias": dias}, ensure_ascii=False),
            encoding="utf-8")
    if not con_datos:  # no publicar una web vacia encima de la anterior
        sys.exit("Ningún cine ha devuelto datos")


if __name__ == "__main__":
    main()
