import contextlib
import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))
spec = importlib.util.spec_from_file_location("lote", PACKAGE / "lote.py")
lote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lote)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "projeto com espaços"
        self.project.mkdir()
        (self.project / "pyproject.toml").write_text(
            '[project]\nname="fake"\nversion="0.0.1"\n'
        )
        self.config_root = self.root / "scripts"
        self.config_root.mkdir()
        self.pbf = self.project / "dados com espaços.osm.pbf"
        self.pbf.write_bytes(b"not a real OSM file: CLI mock only")
        self.grid = self.project / "grade normalizada.gpkg"
        self.make_grid(self.grid)
        self.csv = self.root / "cidades.csv"
        self.csv.write_text(
            "city,state,state_code,id\nAlfa,São Paulo,SP,1\nFalha,São Paulo,SP,2\nZeta,São Paulo,SP,3\nOutra,Rio de Janeiro,RJ,4\n",
            encoding="utf-8",
        )
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.calls = self.root / "calls.jsonl"
        uv = self.bin / "uv"
        uv.write_text("""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
if args == ['--version']:
    print('uv mocked-for-tests')
    sys.exit(0)
if args[:2] == ['run', '--no-project']:
    os.execv(sys.executable, [sys.executable, *args[5:]])
with open(os.environ['MOCK_CALLS'], 'a', encoding='utf-8') as f:
    f.write(json.dumps({'args': args, 'cwd': os.getcwd()}, ensure_ascii=False) + '\\n')
city = args[args.index('--city') + 1]
print('fake analysis ' + city, flush=True)
sys.exit(7 if city == 'Falha' else 0)
""")
        uv.chmod(0o755)
        self.addCleanup(patch.stopall)
        patch.object(lote, "ROOT", self.config_root).start()
        patch.dict(
            os.environ,
            {
                "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                "MOCK_CALLS": str(self.calls),
            },
        ).start()

    def make_grid(self, path, population=True):
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE gpkg_contents(table_name TEXT, data_type TEXT)")
        con.execute("INSERT INTO gpkg_contents VALUES('grade','features')")
        con.execute(
            "CREATE TABLE grade(ID INTEGER, "
            + ("POPULATION REAL" if population else "ERRADA REAL")
            + ")"
        )
        con.commit()
        con.close()

    def args(self, *extra):
        return [
            "--country",
            "BR",
            "--project-dir",
            str(self.project),
            "--region",
            "SP",
            "--cities-csv",
            str(self.csv),
            "--pbf",
            str(self.pbf),
            "--population-grid",
            str(self.grid),
            *extra,
        ]

    def run_main(self, *extra):
        with contextlib.redirect_stdout(io.StringIO()):
            return lote.main(self.args(*extra))

    def call_data(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def test_continues_after_failure_exact_arguments_and_logging(self):
        self.assertEqual(self.run_main(), 1)
        calls = self.call_data()
        self.assertEqual(
            [c["args"][c["args"].index("--city") + 1] for c in calls],
            ["Alfa", "Falha", "Zeta"],
        )
        for c in calls:
            args = c["args"]
            self.assertEqual(args[args.index("--state") + 1], "São Paulo")
            self.assertEqual(args[args.index("--population-column") + 1], "POPULATION")
            self.assertEqual(args[args.index("--population-id-column") + 1], "ID")
            self.assertEqual(args[args.index("--pbf") + 1], str(self.pbf))
            self.assertEqual(c["cwd"], str(self.project))
        run = next((self.project / "logs/lotes").glob("BR_*"))
        summary = (run / "resumo.csv").read_text(encoding="utf-8-sig")
        self.assertIn("FALHA", summary)
        self.assertEqual(len(list(run.glob("cidade_*.log"))), 3)
        self.assertIn("fake analysis Alfa", (run / "cidade_000001.log").read_text())

    def test_resume_retries_failure_and_invalidates_changed_input(self):
        self.assertEqual(self.run_main(), 1)
        self.assertEqual(self.run_main("--resume"), 1)
        self.assertEqual(len(self.call_data()), 4)
        self.pbf.write_bytes(b"changed input file")
        self.assertEqual(self.run_main("--resume"), 1)
        self.assertEqual(len(self.call_data()), 7)

    def test_no_resume_reexecutes(self):
        self.run_main()
        self.run_main()
        self.assertEqual(len(self.call_data()), 6)

    def test_dry_run_and_list_never_mark_success_or_execute(self):
        self.assertEqual(self.run_main("--dry-run"), 0)
        self.assertEqual(self.run_main("--list-only"), 0)
        self.assertFalse(self.calls.exists())
        self.assertFalse((self.project / "logs/lotes/progresso_BR.jsonl").exists())
        with next(
            (self.project / "logs/lotes").glob("BR_*/metricas_cientificas.csv")
        ).open(encoding="utf-8-sig") as stream:
            rows = list(lote.csv.DictReader(stream))
        self.assertTrue(
            all(row["measurement_status"] == "NOT_EXECUTED" for row in rows)
        )
        self.assertTrue(all(row["rss_peak_sampled_mib"] == "" for row in rows))
        self.assertEqual(self.run_main("--resume", "--limit", "1"), 0)
        self.assertEqual(len(self.call_data()), 1)

    def test_missing_population_fails_before_start(self):
        bad = self.project / "bad.gpkg"
        self.make_grid(bad, population=False)
        with self.assertRaisesRegex(RuntimeError, "POPULATION"):
            self.run_main("--population-grid", str(bad))
        self.assertFalse(self.calls.exists())

    def test_region_choices_accent_alias_and_all(self):
        regions = [
            {"code": "35", "name": "São Paulo", "aliases": ["SP", "35"]},
            {"code": "33", "name": "Rio de Janeiro", "aliases": ["RJ", "33"]},
        ]
        for value in ["SP", "35", "sao paulo", "SÃO PAULO"]:
            self.assertEqual(lote.choose_regions(regions, value, "UF")[0]["code"], "35")
        self.assertEqual(len(lote.choose_regions(regions, "0", "UF")), 2)
        with self.assertRaises(RuntimeError):
            lote.choose_regions(regions, "Atlantida", "UF")

    def test_sources_br_fr_urls_and_population_not_catalog(self):
        def fake(url, cache, refresh):
            if "/estados?" in url:
                return [{"id": 35, "nome": "São Paulo", "sigla": "SP"}]
            if "/municipios?" in url:
                return [{"id": 1, "nome": "Santos"}]
            if url.endswith("/regions"):
                return [{"code": "11", "nom": "Île-de-France"}]
            if "/communes?" in url:
                self.assertIn("codeRegion=11", url)
                return [{"code": "75056", "nom": "Paris", "codeRegion": "11"}]
            self.fail(url)

        with patch.object(lote, "get_json", side_effect=fake):
            for country, name in [("BR", "Santos"), ("FR", "Paris")]:
                regions = lote.get_regions(country, self.root, False)
                cities = lote.get_cities(country, regions, self.root, False)
                self.assertEqual(cities[0]["city"], name)
                self.assertNotIn("population", cities[0])

    def test_geonames_filters_neighborhoods_historical_and_other_regions(self):
        admin = self.root / "admin.txt"
        admin.write_text(
            "CN.23\tShanghai\tShanghai\t1\nCN.22\tBeijing\tBeijing\t2\n",
            encoding="utf-8",
        )
        archive = self.root / "CN.zip"

        def record(identifier, name, feature, region):
            return (
                f"{identifier}\t{name}\t{name}\t\t1\t1\tP\t{feature}\tCN\t\t"
                f"{region}\t\t\t\t0\t\t\tAsia/Shanghai\t2026-01-01"
            )

        with zipfile.ZipFile(archive, "w") as z:
            z.writestr(
                "CN.txt",
                "\n".join(
                    [
                        record("1", "Shanghai", "PPLA", "23"),
                        record("2", "Neighborhood", "PPLX", "23"),
                        record("3", "Old town", "PPLH", "23"),
                        record("4", "Beijing", "PPLC", "22"),
                    ]
                ),
            )

        def fake_download(url, destination, refresh=False, ttl=86400):
            return admin if url.endswith("admin1CodesASCII.txt") else archive

        with (
            patch.object(lote, "download", side_effect=fake_download),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            regions = lote.get_regions("CN", self.root, False)
            chosen = lote.choose_regions(regions, "Shanghai", "província")
            cities = lote.get_cities("CN", chosen, self.root, False)
        self.assertEqual([c["city"] for c in cities], ["Shanghai"])

    def test_keyboard_interrupt_does_not_mark_success(self):
        with patch.object(lote, "run_city", side_effect=KeyboardInterrupt):
            self.assertEqual(self.run_main(), 130)
        self.assertFalse((self.project / "logs/lotes/progresso_BR.jsonl").exists())
        summary = next((self.project / "logs/lotes").glob("BR_*/resumo.csv")).read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("INTERROMPIDA", summary)

    def test_launchers_country_and_forwarding_arguments(self):
        for path in PACKAGE.glob("*.sh"):
            result = subprocess.run(
                ["bash", "-n", str(path)], capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(
            ["bash", str(PACKAGE / "analisar_brasil.sh"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--population-grid", result.stdout)
        self.assertEqual(len(list(PACKAGE.glob("*.sh"))), 9)
        self.assertEqual(len(list(PACKAGE.glob("*.ps1"))), 9)

    def test_scientific_csv_and_environment_for_every_real_city(self):
        self.assertEqual(self.run_main("--sample-interval", "0.1", "--hash-inputs"), 1)
        folder = next((self.project / "logs/lotes").glob("BR_*"))
        environment = json.loads((folder / "ambiente.json").read_text())
        self.assertEqual(environment["software"]["psutil_version"], "7.2.2")
        self.assertEqual(len(environment["inputs"]["pbf"]["sha256"]), 64)
        self.assertNotIn("DATABASE_URL", json.dumps(environment))
        with (folder / "metricas_cientificas.csv").open(encoding="utf-8-sig") as stream:
            rows = list(lote.csv.DictReader(stream))
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            [row["status"] for row in rows], ["SUCESSO", "FALHA", "SUCESSO"]
        )
        for row in rows:
            self.assertGreater(float(row["wall_seconds"]), 0)
            self.assertGreaterEqual(float(row["cpu_total_seconds"]), 0)
            self.assertEqual(row["cpu_time_method"], "rusage_children_delta")
            self.assertTrue(Path(row["series_csv"]).is_file())
            self.assertTrue(Path(row["metrics_json"]).is_file())
        self.run_main("--resume")
        folders = sorted((self.project / "logs/lotes").glob("BR_*"))
        with (folders[-1] / "metricas_cientificas.csv").open(
            encoding="utf-8-sig"
        ) as stream:
            resumed = list(lote.csv.DictReader(stream))
        for row in resumed:
            if row["status"] == "IGNORADA":
                self.assertEqual(row["measurement_status"], "NOT_EXECUTED")
                self.assertEqual(row["cpu_total_seconds"], "")

    def test_live_sampling_includes_child_memory_and_cpu(self):
        child = "import time; b=bytearray(64*1024*1024); end=time.monotonic()+0.6\nwhile time.monotonic()<end: sum(range(20000))"
        parent = (
            'import subprocess,sys; subprocess.run([sys.executable,"-c",'
            + repr(child)
            + "],check=True)"
        )
        metrics = {}
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = lote.run_city(
                [sys.executable, "-c", parent],
                self.project,
                self.root / "live.log",
                sample_interval=0.1,
                metrics=metrics,
            )
        self.assertEqual(exit_code, 0)
        if metrics["samples_with_processes"]:
            self.assertGreater(metrics["rss_peak_sampled_mib"], 60)
            self.assertGreaterEqual(metrics["processes_peak_sampled"], 2)
            self.assertEqual(metrics["measurement_status"], "OK")
        else:
            # Este executor pode não expor os PIDs locais em /proc.
            self.assertIsNone(metrics["rss_peak_sampled_mib"])
            self.assertEqual(metrics["measurement_status"], "PARTIAL")
        self.assertGreater(metrics["cpu_total_seconds"], 0.2)
        self.assertGreater(metrics["samples"], 3)
        self.assertTrue((self.root / "live.metricas.json").is_file())

    def test_sampled_cpu_fallback_and_missing_machine_counters(self):
        import time

        from monitoramento import ResourceMonitor, utc_now

        monitor = ResourceMonitor(
            os.getpid(), self.root / "fallback.csv", 0.1, time.monotonic(), utc_now()
        )
        monitor.start()
        time.sleep(0.12)
        result = monitor.finish(None, None, time.monotonic(), utc_now())
        self.assertEqual(
            result["cpu_time_method"], "sampled_observed_process_counters_lower_bound"
        )
        self.assertIsNone(result["process_block_inputs"])
        if result["samples_with_processes"]:
            self.assertGreaterEqual(result["rss_peak_sampled_mib"], 0)
        else:
            self.assertIsNone(result["rss_peak_sampled_mib"])
            self.assertEqual(result["measurement_status"], "PARTIAL")

    def test_tree_memory_sampling_and_cpu_counter_aggregation_with_backend(self):
        import time
        from types import SimpleNamespace

        from monitoramento import MIB, ResourceMonitor, utc_now

        monitor = ResourceMonitor(
            1, self.root / "tree.csv", 0.1, time.monotonic(), utc_now()
        )

        class FakeProcess:
            def __init__(self, memory, cpu):
                self.memory, self.cpu = memory, cpu

            def is_running(self):
                return True

            def status(self):
                return "running"

            def oneshot(self):
                return contextlib.nullcontext()

            def memory_info(self):
                return SimpleNamespace(rss=self.memory)

            def cpu_times(self):
                return SimpleNamespace(user=self.cpu, system=0.2)

        processes = [
            ((1, 1), FakeProcess(10 * MIB, 0.5)),
            ((2, 1), FakeProcess(64 * MIB, 1.0)),
        ]
        with patch.object(monitor, "processes", return_value=processes):
            monitor.start()
            time.sleep(0.12)
            data = monitor.finish(None, None, time.monotonic(), utc_now())
        self.assertEqual(data["processes_peak_sampled"], 2)
        self.assertEqual(data["rss_peak_sampled_mib"], 74)
        self.assertAlmostEqual(data["rss_mean_sampled_mib"], 74)
        self.assertAlmostEqual(data["cpu_total_seconds"], 1.9)

    def test_invalid_sampling_interval_rejected(self):
        for value in ["0", "-1", "nan", "inf"]:
            with (
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                lote.main(self.args("--sample-interval", value))

    def test_actual_interruption_preserves_measurements_and_reaps_process(self):
        class InterruptOutput(io.StringIO):
            def write(self, value):
                if "READY" in value:
                    raise KeyboardInterrupt
                return super().write(value)

        command = [
            sys.executable,
            "-c",
            "print('READY',flush=True); import time; time.sleep(10)",
        ]
        metrics = {}
        with (
            contextlib.redirect_stdout(InterruptOutput()),
            self.assertRaises(KeyboardInterrupt),
        ):
            lote.run_city(
                command,
                self.project,
                self.root / "interrupted.log",
                sample_interval=0.1,
                metrics=metrics,
            )
        saved = json.loads((self.root / "interrupted.metricas.json").read_text())
        self.assertNotEqual(saved["native_exit_code"], 0)
        self.assertGreater(saved["wall_seconds"], 0)
        self.assertLess(saved["wall_seconds"], 5)
        self.assertTrue((self.root / "interrupted.recursos.csv").is_file())

    def test_example_config_is_preserved_when_saving_local_paths(self):
        example = self.config_root / "arquivos.example.json"
        original = json.dumps(
            {
                "countries": {
                    "BR": {"pbf": str(self.pbf), "population_grid": str(self.grid)}
                }
            }
        )
        example.write_text(original, encoding="utf-8")
        self.assertEqual(self.run_main("--limit", "1"), 0)
        self.assertEqual(example.read_text(encoding="utf-8"), original)
        local = json.loads(
            (self.config_root / "arquivos.json").read_text(encoding="utf-8")
        )
        self.assertEqual(local["countries"]["BR"]["pbf"], str(self.pbf))

    def test_project_root_is_detected_from_scripts_directory(self):
        checkout = self.root / "checkout"
        scripts = checkout / "scripts" / "automacao"
        scripts.mkdir(parents=True)
        (checkout / "pyproject.toml").write_text(
            '[project]\nname="fake"\nversion="0.1"\n'
        )
        region = {"code": "35", "name": "São Paulo", "aliases": ["SP"]}
        cities = [lote.city_record("1", "Santos", region, "BR", "test")]
        with (
            patch.object(lote, "ROOT", scripts),
            patch.object(lote, "get_regions", return_value=[region]),
            patch.object(lote, "get_cities", return_value=cities),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                lote.main(["--country", "BR", "--region", "SP", "--list-only"]), 0
            )
        self.assertEqual(
            len(list((checkout / "logs/lotes").glob("BR_*/cidades.csv"))), 1
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
