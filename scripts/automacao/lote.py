#!/usr/bin/env python3
"""Lotes sequenciais da CLI existente, com monitoramento científico por execução."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
import unicodedata
import zipfile
import zlib
from contextlib import suppress
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from monitoramento import (
    METRIC_FIELDS,
    MONITOR_ERRORS,
    ResourceMonitor,
    environment_metadata,
    require_psutil,
    usage_snapshot,
    utc_now,
)

ROOT = Path(__file__).resolve().parent
COUNTRIES = {
    "BR": ("Brasil", "Brazil", "brazil", "UF"),
    "FR": ("França", "France", "france", "região"),
    "ES": ("Espanha", "Spain", "spain", "comunidade autônoma"),
    "IT": ("Itália", "Italy", "italy", "região"),
    "AU": ("Austrália", "Australia", "australia", "estado/território"),
    "CN": ("China", "China", "china", "divisão provincial"),
    "NL": ("Países Baixos", "Netherlands", "netherlands", "província"),
    "BE": ("Bélgica", "Belgium", "belgium", "região"),
    "US": ("Estados Unidos", "United States", "united-states", "estado"),
}
PPL_CODES = {"PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLA5", "PPLC", "PPLG", "PPLL"}
BR_API = "https://servicodados.ibge.gov.br/api/v1/localidades"
FR_API = "https://geo.api.gouv.fr"
GN_BASE = "https://download.geonames.org/export/dump"


def norm(value):
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", value.strip()).casefold()
        if not unicodedata.combining(c)
    )


def load_json(path, default=None):
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def download(url, destination, refresh=False, ttl=86400):
    if (
        not refresh
        and destination.is_file()
        and time.time() - destination.stat().st_mtime < ttl
    ):
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    error = None
    for attempt in range(3):
        try:
            print(f"Consultando: {url}", flush=True)
            request = Request(url, headers={"User-Agent": "TCC-Cidade15-Batch/1.0"})
            with (
                urlopen(request, timeout=90) as response,
                temporary.open("wb") as output,
            ):
                shutil.copyfileobj(response, output)
            temporary.replace(destination)
            return destination
        except (OSError, URLError) as exc:
            error = exc
            temporary.unlink(missing_ok=True)
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Falha ao consultar {url}: {error}")


def parse_catalogue(payload):
    # json.loads(bytes) reconhece os marcadores BOM de UTF-8/16/32.
    if payload.startswith(b"\x1f\x8b"):
        payload = gzip.decompress(payload)
    data = json.loads(payload)
    if not isinstance(data, list):
        raise TypeError("O catálogo deve retornar uma lista JSON.")
    return data


def get_json(url, cache, refresh):
    name = hashlib.sha256(url.encode()).hexdigest()
    path = cache / (name + ".json")
    diagnostic = cache / (name + ".response-error.json")
    if not refresh and path.is_file() and time.time() - path.stat().st_mtime < 86400:
        try:
            return parse_catalogue(path.read_bytes())
        except (ValueError, TypeError, OSError, EOFError, zlib.error):
            print(
                f"Cache de catálogo inválido; consultando novamente: {url}", flush=True
            )
            path.unlink(missing_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    error = None
    for attempt in range(3):
        body = b""
        status = content_type = content_encoding = None
        try:
            print(f"Consultando: {url} (tentativa {attempt + 1}/3)", flush=True)
            request = Request(
                url,
                headers={
                    "User-Agent": "TCC-Cidade15-Batch/1.0",
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                },
            )
            with urlopen(request, timeout=90) as response:
                status = response.status
                content_type = response.headers.get("Content-Type")
                content_encoding = response.headers.get("Content-Encoding")
                body = response.read()
            data = parse_catalogue(body)
            # Só publica respostas válidas no cache, com codificação normalizada.
            write_json(path, data)
            diagnostic.unlink(missing_ok=True)
            return data
        except (OSError, URLError, ValueError, TypeError, EOFError, zlib.error) as exc:
            error = exc
            if isinstance(exc, HTTPError):
                status = exc.code
                content_type = exc.headers.get("Content-Type") if exc.headers else None
                body = exc.read(512)
                exc.close()
            write_json(
                diagnostic,
                {
                    "url": url,
                    "attempt": attempt + 1,
                    "http_status": status,
                    "content_type": content_type,
                    "content_encoding": content_encoding,
                    "error": str(exc),
                    "response_prefix": body[:512].decode("utf-8", errors="replace"),
                    "response_prefix_hex": body[:32].hex(),
                },
            )
            print(
                f"Catálogo indisponível ou inválido: HTTP {status}, "
                f"Content-Type={content_type}; {exc}",
                flush=True,
            )
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(
        f"Não foi possível obter uma lista JSON válida de {url} após 3 tentativas. "
        f"Diagnóstico: {diagnostic}. Último erro: {error}"
    ) from error


def get_regions(code, cache, refresh):
    if code == "BR":
        data = get_json(BR_API + "/estados?orderBy=nome", cache, refresh)
        return [
            {
                "code": str(r["id"]),
                "name": r["nome"],
                "aliases": [r["sigla"], str(r["id"])],
            }
            for r in data
        ]
    if code == "FR":
        data = get_json(FR_API + "/regions", cache, refresh)
        return [
            {"code": r["code"], "name": r["nom"], "aliases": [r["code"]]} for r in data
        ]
    path = download(
        GN_BASE + "/admin1CodesASCII.txt", cache / "admin1CodesASCII.txt", refresh
    )
    regions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) >= 4 and fields[0].startswith(code + "."):
            region_code = fields[0].split(".", 1)[1]
            regions.append(
                {
                    "code": region_code,
                    "name": fields[1],
                    "aliases": [region_code, fields[0], fields[2]],
                }
            )
    return regions


def choose_regions(regions, answer, label):
    regions = sorted(regions, key=lambda r: norm(r["name"]))
    if not regions:
        raise RuntimeError("A fonte não retornou divisões administrativas.")
    if answer is None:
        print(f"\nSelecione {label} pelo código ou nome:")
        for region in regions:
            aliases = "/".join(dict.fromkeys([region["code"], *region["aliases"][:1]]))
            print(f"  [{aliases}] {region['name']}")
        print("  [0] País inteiro")
        answer = ask("Seleção: ")
    if norm(answer) in {"0", "all", "todos", "todas", "pais inteiro"}:
        return regions
    matches = [
        r
        for r in regions
        if norm(answer)
        in {norm(r["name"]), norm(r["code"]), *(norm(a) for a in r["aliases"])}
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Seleção inválida ou ambígua: {answer!r}. Use o código ou nome completo."
        )
    return matches


def ask(prompt):
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Entrada interativa indisponível. Informe --region e os caminhos pelos parâmetros."
        )
    return input(prompt).strip()


def city_record(identifier, name, region, code, source):
    return {
        "id": str(identifier),
        "city": name,
        "state": region["name"],
        "state_code": region["code"],
        "country": COUNTRIES[code][1],
        "source": source,
    }


def get_cities(code, selected, cache, refresh):
    cities = []
    if code in {"BR", "FR"}:
        for region in selected:
            if code == "BR":
                data = get_json(
                    f"{BR_API}/estados/{region['code']}/municipios?orderBy=nome",
                    cache,
                    refresh,
                )
                cities.extend(
                    city_record(c["id"], c["nome"], region, code, "IBGE") for c in data
                )
            else:
                query = urlencode(
                    {
                        "codeRegion": region["code"],
                        "fields": "nom,code,codeRegion",
                        "format": "json",
                    }
                )
                data = get_json(FR_API + "/communes?" + query, cache, refresh)
                cities.extend(
                    city_record(c["code"], c["nom"], region, code, "geo.api.gouv.fr")
                    for c in data
                )
        return cities
    print(
        "\nFonte: GeoNames. A lista contém localidades habitadas, não um cadastro oficial de municípios."
    )
    print(
        "A população do GeoNames NÃO é usada nas métricas; a análise usa exclusivamente seu GPKG."
    )
    archive = download(
        f"{GN_BASE}/{code}.zip", cache / f"{code}.zip", refresh, ttl=7 * 86400
    )
    region_map = {r["code"]: r for r in selected}
    without_region = 0
    with zipfile.ZipFile(archive) as zipped, zipped.open(f"{code}.txt") as raw:
        for fields in csv.reader(
            io.TextIOWrapper(raw, encoding="utf-8"), delimiter="\t"
        ):
            if (
                len(fields) < 19
                or fields[8] != code
                or fields[6] != "P"
                or fields[7] not in PPL_CODES
            ):
                continue
            region = region_map.get(fields[10])
            if region:
                cities.append(
                    city_record(fields[0], fields[1], region, code, "GeoNames")
                )
            elif not fields[10] or fields[10] == "00":
                without_region += 1
    if without_region:
        print(f"Localidades sem divisão provincial válida ignoradas: {without_region}.")
    return cities


def csv_cities(path, code):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"city", "state"}.issubset(reader.fieldnames or []):
            raise RuntimeError(
                "O CSV deve ter cabeçalho city,state; state_code e id são opcionais."
            )
        records = []
        regions = {}
        for index, row in enumerate(reader, 2):
            name = (row.get("city") or "").strip()
            state = (row.get("state") or "").strip()
            if not name or not state:
                raise RuntimeError(f"CSV: city ou state vazio na linha {index}.")
            declared_country = (row.get("country") or "").strip()
            if declared_country and norm(declared_country) != norm(COUNTRIES[code][1]):
                raise RuntimeError(
                    f"CSV: país incompatível na linha {index}: {declared_country}."
                )
            region_code = (row.get("state_code") or state).strip()
            region = {"code": region_code, "name": state, "aliases": [region_code]}
            previous = regions.get(region_code)
            if previous and previous["name"] != state:
                raise RuntimeError(
                    f"CSV: state_code {region_code!r} corresponde a nomes diferentes."
                )
            regions[region_code] = region
            records.append(
                city_record(row.get("id") or index, name, region, code, "CSV local")
            )
    return records, list(regions.values())


def export_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def resolve_input(value, folder, suffix, prompt, project, execute):
    if value:
        path = Path(value).expanduser()
        path = path if path.is_absolute() else project / path
        if not execute or path.is_file():
            return path.resolve()
        print(f"Arquivo configurado não encontrado: {path}")
    candidates = (
        sorted(p for p in folder.glob("*" + suffix) if p.is_file())
        if folder.is_dir()
        else []
    )
    if len(candidates) == 1:
        print(f"Arquivo encontrado: {candidates[0]}")
        return candidates[0].resolve()
    if candidates:
        print("Há vários arquivos; informe qual deseja usar:")
        for path in candidates:
            print(f"  {path}")
    answer = ask(prompt).strip('"').strip("'")
    path = Path(answer).expanduser()
    path = path if path.is_absolute() else project / path
    if not answer or not path.is_file():
        raise RuntimeError(f"Arquivo inexistente: {path}")
    return path.resolve()


def check_grid(path):
    if path.suffix.lower() != ".gpkg":
        raise RuntimeError("Informe a grade já normalizada em .gpkg.")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        layers = connection.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features'"
        ).fetchall()
        if len(layers) != 1:
            raise RuntimeError("Use um GPKG normalizado com uma única camada vetorial.")
        table = layers[0][0].replace('"', '""')
        columns = {
            row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')
        }
        missing = {"POPULATION", "ID"} - columns
        if missing:
            raise RuntimeError(
                f"Faltam colunas na grade: {', '.join(sorted(missing))}. Encontradas: {sorted(columns)}"
            )
    finally:
        connection.close()


def build_command(city, pbf, grid, cache):
    return [
        "uv",
        "run",
        "fifteen-minute-city",
        "--city",
        city["city"],
        "--state",
        city["state"],
        "--country",
        city["country"],
        "--pbf",
        str(pbf),
        "--population-grid",
        str(grid),
        "--population-column",
        "POPULATION",
        "--population-id-column",
        "ID",
        "--cache-dir",
        str(cache),
        "--enable-db",
        "--output-mode",
        "simple",
        "--verbose",
    ]


def command_text(command):
    return subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)


def signature(command, project):
    inputs = []
    for option in ("--pbf", "--population-grid"):
        path = Path(command[command.index(option) + 1])
        stat = path.stat()
        inputs.append((str(path.resolve()), stat.st_size, stat.st_mtime_ns))
    payload = [str(project), command, inputs]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def run_city(command, project, log_path, sample_interval=1.0, metrics=None):
    metrics = metrics if metrics is not None else {}
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    # O ambiente isolado do monitor não é o ambiente virtual da CLI do projeto.
    environment.pop("VIRTUAL_ENV", None)
    with log_path.open("w", encoding="utf-8") as log:
        log.write(command_text(command) + "\n\n")
        log.flush()
        before = usage_snapshot()
        started, started_utc = time.monotonic(), utc_now()
        process = subprocess.Popen(
            command,
            cwd=project,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        monitor = None

        def terminate_tree():
            if monitor is not None:
                for _, child in monitor.processes():
                    with suppress(*MONITOR_ERRORS):
                        child.terminate()
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        try:
            try:
                monitor = ResourceMonitor(
                    process.pid,
                    log_path.with_suffix(".recursos.csv"),
                    sample_interval,
                    started,
                    started_utc,
                )
                monitor.start()
            except MONITOR_ERRORS as exc:
                metrics.update(measurement_status="ERROR", monitoring_error=str(exc))
                print(f"AVISO: monitoramento parcial/indisponível: {exc}", flush=True)
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
            return process.wait()
        except KeyboardInterrupt:
            # Encerra também os descendentes conhecidos, inclusive no Windows.
            terminate_tree()
            raise
        finally:
            if process.poll() is None:
                terminate_tree()
            finished, finished_utc = time.monotonic(), utc_now()
            after = usage_snapshot()
            if process.stdout is not None:
                process.stdout.close()
            metrics.update(
                started_at_utc=started_utc,
                finished_at_utc=finished_utc,
                wall_seconds=finished - started,
            )
            if monitor is not None and monitor.stream is not None:
                try:
                    metrics.update(
                        monitor.finish(before, after, finished, finished_utc)
                    )
                except MONITOR_ERRORS as exc:
                    metrics.update(
                        measurement_status="ERROR", monitoring_error=str(exc)
                    )
                    print(f"AVISO: falha ao finalizar métricas: {exc}", flush=True)
            metrics_path = log_path.with_suffix(".metricas.json")
            metrics["metrics_json"] = str(metrics_path)
            write_json(
                metrics_path,
                {
                    "command": command,
                    "project_dir": str(project),
                    "native_exit_code": process.returncode,
                    **metrics,
                },
            )


def execute_batch(cities, args, project, pbf, grid, run_dir):
    progress = project / "logs" / "lotes" / f"progresso_{args.country}.jsonl"
    done = set()
    if args.resume and progress.exists():
        for line in progress.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
                if item.get("status") == "SUCESSO":
                    done.add(item["signature"])
            except (ValueError, KeyError):
                pass
    summary_fields = [
        "city",
        "state",
        "country",
        "status",
        "seconds",
        "exit_code",
        "log",
    ]
    counts = {"SUCESSO": 0, "FALHA": 0, "IGNORADA": 0, "SIMULADA": 0, "INTERROMPIDA": 0}
    started = time.monotonic()
    with (
        (run_dir / "resumo.csv").open("w", encoding="utf-8-sig", newline="") as stream,
        (run_dir / "metricas_cientificas.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as science_stream,
    ):
        writer = csv.DictWriter(
            stream, fieldnames=summary_fields, extrasaction="ignore"
        )
        writer.writeheader()
        science_writer = csv.DictWriter(
            science_stream,
            fieldnames=summary_fields + METRIC_FIELDS,
            extrasaction="ignore",
        )
        science_writer.writeheader()
        for index, city in enumerate(cities, 1):
            command = build_command(city, pbf, grid, project / "data" / "cache")
            log_path = run_dir / f"cidade_{index:06d}.log"
            record = {**city, "seconds": 0, "exit_code": "", "log": str(log_path)}
            print(
                f"\n[{index}/{len(cities)}] {city['city']} — {city['state']} — {city['country']}",
                flush=True,
            )
            item_started = time.monotonic()
            key = None
            metrics = {"measurement_status": "NOT_EXECUTED"}
            try:
                if args.dry_run:
                    print(command_text(command))
                    record.update(status="SIMULADA", log="")
                else:
                    key = signature(command, project)
                    if args.resume and key in done:
                        record.update(status="IGNORADA", log="")
                    else:
                        metrics = {"measurement_status": "ERROR"}
                        code = run_city(
                            command,
                            project,
                            log_path,
                            sample_interval=args.sample_interval,
                            metrics=metrics,
                        )
                        record.update(
                            status="SUCESSO" if code == 0 else "FALHA", exit_code=code
                        )
                        with progress.open("a", encoding="utf-8") as journal:
                            journal.write(
                                json.dumps(
                                    {
                                        "signature": key,
                                        "status": record["status"],
                                        "city": city["city"],
                                        "log": str(log_path),
                                    },
                                    ensure_ascii=False,
                                )
                                + "\n"
                            )
            except KeyboardInterrupt:
                record.update(status="INTERROMPIDA", exit_code=130)
            except OSError as exc:
                record.update(status="FALHA", exit_code=-1)
                print(f"ERRO: {exc}", flush=True)
            record["seconds"] = round(time.monotonic() - item_started, 2)
            counts[record["status"]] += 1
            writer.writerow(record)
            stream.flush()
            science_writer.writerow({**record, **metrics})
            science_stream.flush()
            label = {
                "SUCESSO": "CONCLUÍDA",
                "IGNORADA": "JÁ CONCLUÍDA EM LOTE ANTERIOR",
            }.get(record["status"], record["status"])
            print(
                f"[{label}] {city['city']} | {record['seconds']}s | {index}/{len(cities)}",
                flush=True,
            )
            if metrics.get("rss_peak_sampled_mib") is not None:
                print(
                    f"  RAM RSS máxima observada: {metrics['rss_peak_sampled_mib']:.1f} MiB",
                    flush=True,
                )
            if metrics.get("cpu_total_seconds") is not None:
                print(
                    f"  Tempo de CPU: {metrics['cpu_total_seconds']:.3f}s", flush=True
                )
            if record["status"] == "INTERROMPIDA":
                print(f"Interrompido. Logs preservados em {run_dir}")
                return 130
    print(f"\nLote finalizado em {time.monotonic() - started:.1f}s: {counts}")
    print(f"Resumo e logs: {run_dir}")
    return 1 if counts["FALHA"] else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Análises sequenciais de cidades por país e região."
    )
    parser.add_argument("--country", choices=COUNTRIES, required=True)
    parser.add_argument(
        "--region",
        help="UF/código/nome; 0 = país inteiro. Ausente: pergunta no terminal.",
    )
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--pbf", help="Arquivo .osm.pbf, não uma pasta.")
    parser.add_argument(
        "--population-grid", help="GPKG normalizado com ID e POPULATION."
    )
    parser.add_argument(
        "--cities-csv", type=Path, help="Lista própria, substitui a consulta online."
    )
    parser.add_argument(
        "--list-only", action="store_true", help="Exporta a lista, sem executar a CLI."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Imprime comandos, sem executar nem marcar sucesso.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Ignora sucessos anteriores com mesmos caminhos/tamanhos/mtimes de entrada.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limita o número de cidades para uma execução de teste.",
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Atualiza os catálogos consultados."
    )
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=1.0,
        help="Intervalo de amostragem de CPU/RAM em segundos (padrão 1.0; mínimo 0.1).",
    )
    parser.add_argument(
        "--hash-inputs",
        action="store_true",
        help="Calcula SHA256 completo do PBF/GPKG antes do lote; pode demorar em arquivos grandes.",
    )
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit deve ser maior que zero")
    if not math.isfinite(args.sample_interval) or args.sample_interval < 0.1:
        parser.error("--sample-interval deve ser um número finito maior ou igual a 0.1")
    settings = load_json(ROOT / "arquivos.example.json")
    local_settings = load_json(ROOT / "arquivos.json")
    countries = {**settings.get("countries", {}), **local_settings.get("countries", {})}
    settings.update(local_settings)
    settings["countries"] = countries
    detected_project = next(
        (p for p in ROOT.parents if (p / "pyproject.toml").is_file()),
        Path("/opt/15minute-city"),
    )
    project = (
        (args.project_dir or Path(settings.get("project_dir") or detected_project))
        .expanduser()
        .resolve()
    )
    if not project.is_dir():
        raise RuntimeError(
            f"Diretório do projeto não encontrado: {project}. Informe --project-dir."
        )
    catalog_cache = project / "data" / "cache" / "catalogos_lotes"
    if args.cities_csv:
        cities, regions = csv_cities(args.cities_csv, args.country)
        selected = choose_regions(regions, args.region, COUNTRIES[args.country][3])
        selected_codes = {r["code"] for r in selected}
        cities = [c for c in cities if c["state_code"] in selected_codes]
    else:
        regions = get_regions(args.country, catalog_cache, args.refresh)
        selected = choose_regions(regions, args.region, COUNTRIES[args.country][3])
        cities = get_cities(args.country, selected, catalog_cache, args.refresh)
    # A CLI recebe apenas cidade + estado + país: consultas idênticas rodam uma vez.
    unique = {}
    for city in cities:
        unique.setdefault(
            (city["city"].casefold(), city["state"].casefold(), city["country"]), city
        )
    duplicates = len(cities) - len(unique)
    cities = sorted(unique.values(), key=lambda c: (norm(c["state"]), norm(c["city"])))
    if args.limit:
        cities = cities[: args.limit]
    if not cities:
        raise RuntimeError("Nenhuma cidade/localidade encontrada para a seleção.")
    if duplicates:
        print(
            f"Consultas idênticas por cidade/estado/país consolidadas: {duplicates}. Homônimos podem exigir CSV revisado."
        )
    run_dir = (
        project
        / "logs"
        / "lotes"
        / f"{args.country}_{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns() % 1000000:06d}"
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    export_csv(
        run_dir / "cidades.csv",
        cities,
        ["id", "city", "state", "state_code", "country", "source"],
    )
    print(
        f"\nSelecionadas: {len(cities)} cidades/localidades. Lista: {run_dir / 'cidades.csv'}"
    )
    if args.list_only:
        print("Somente listagem: nenhuma análise foi executada.")
        return 0
    paths = settings.get("countries", {}).get(args.country, {})
    folder = project / "data" / "input" / COUNTRIES[args.country][2]
    pbf = resolve_input(
        args.pbf or paths.get("pbf"),
        folder,
        ".pbf",
        "Caminho completo do PBF: ",
        project,
        not args.dry_run,
    )
    grid = resolve_input(
        args.population_grid or paths.get("population_grid"),
        folder,
        ".gpkg",
        "Caminho completo do GPKG normalizado: ",
        project,
        not args.dry_run,
    )
    if not args.dry_run:
        if not (project / "pyproject.toml").is_file():
            raise RuntimeError(f"pyproject.toml não encontrado em {project}.")
        if not shutil.which("uv"):
            raise RuntimeError("uv não encontrado no PATH.")
        if not pbf.name.lower().endswith(".pbf"):
            raise RuntimeError("--pbf deve apontar para um arquivo .pbf.")
        check_grid(grid)
        require_psutil()
        print(
            "Registrando ambiente e arquivos de entrada antes de iniciar as medições...",
            flush=True,
        )
        write_json(
            run_dir / "ambiente.json",
            environment_metadata(
                project, pbf, grid, args.sample_interval, args.hash_inputs
            ),
        )
        # Lembra os arquivos para as próximas execuções; não guarda credenciais.
        settings["project_dir"] = str(project)
        settings.setdefault("countries", {})[args.country] = {
            "pbf": str(pbf),
            "population_grid": str(grid),
        }
        write_json(ROOT / "arquivos.json", settings)
    print(
        f"PBF: {pbf}\nGrade: {grid}\nColunas fixas: POPULATION (população) e ID (identificador)."
    )
    print("Uma cidade por vez. SUCESSO significa código de saída zero da CLI.")
    return execute_batch(cities, args, project, pbf, grid, run_dir)


if __name__ == "__main__":
    for output in (sys.stdout, sys.stderr):
        if hasattr(output, "reconfigure"):
            output.reconfigure(errors="replace")
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.", file=sys.stderr)
        raise SystemExit(130)
    except (
        RuntimeError,
        OSError,
        ValueError,
        KeyError,
        sqlite3.Error,
        zipfile.BadZipFile,
    ) as error:
        print(f"ERRO: {error}", file=sys.stderr)
        raise SystemExit(1)
