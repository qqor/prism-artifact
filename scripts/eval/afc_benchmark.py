import importlib
import json
import os
import shutil
import subprocess
import time
import traceback
from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import Iterator, List, Optional

import click
import litellm
from crete.atoms.report import CreteResult, DiffResult, ErrorResult, NoPatchResult
from crete.commons.logging.hooks import use_logger
from pygit2 import Repository
from tqdm import tqdm

from scripts.benchmark.models import BenchmarkReport, BenchmarkResult
from scripts.benchmark.verifiers import (
    verify_patch_with_crete,
    verify_patch_with_patch_checker,
)
from scripts.eval.models import TaskMetadata
from scripts.eval.task_manager import clean_task_directory, sudo_rm

litellm.suppress_debug_info = True

_logger = use_logger()


@dataclass(frozen=True)
class BenchmarkArguments:
    timeout: int
    llm_cost_limit: float


@click.command()
@click.argument(
    "detection-files",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    nargs=-1,
)
@click.option(
    "--module",
    "-m",
    help="""App to run ([module]:[object])""",
    required=False,
    default=None,
    multiple=True,
    type=str,
)
@click.option(
    "--cache-directory",
    help="Cache directory",
    type=click.Path(exists=False, file_okay=False, dir_okay=True, path_type=Path),
    default=Path(__file__).parent.parent.parent / ".cache/afc",
    required=False,
)
@click.option(
    "--reports-directory",
    help="Reports directory",
    type=click.Path(exists=False, file_okay=False, dir_okay=True, path_type=Path),
    default=Path(__file__).parent.parent.parent / "reports",
)
@click.option(
    "--timeout-for-app",
    help="Timeout for each app in seconds (default: None)",
    type=Optional[int],
    default=None,
)
@click.option(
    "--timeout",
    help="Timeout for each app and detection in seconds (default: 5 minutes)",
    type=int,
    default=60 * 60,  # 1 hour
)
@click.option(
    "--llm-cost-limit",
    help="LLM cost limit for each app and detection in dollars (default: 5.0)",
    type=float,
    default=5.0,  # 5 dollars
)
@click.option(
    "--keep-best-result",
    help="Instead of deleting the contents of the report directory, replace the existing contents only if the execution results are better than or equal to the previous execution; otherwise, retain the existing contents (default: False)",
    is_flag=True,
    default=False,
)
@click.option(
    "--early-exit-on-sound",
    help="Execution will not be performed if the existing patch is sound (valid only when the --keep-best-result option is enabled, default: False)",
    is_flag=True,
    default=False,
)
@click.option(
    "--no-cache",
    help="Use cache",
    is_flag=True,
    default=False,
)
def run(
    detection_files: tuple[Path],
    module: list[str],
    cache_directory: Path,
    reports_directory: Path,
    timeout_for_app: Optional[int],
    timeout: int,
    llm_cost_limit: float,
    keep_best_result: bool,
    early_exit_on_sound: bool,
    no_cache: bool,
):
    """\b
    Run benchmarks for Crete, targeting apps/*.py directory. 
    If --module is not provided, all apps/*.py will be run.


    \b
    Example:
    $ uv run benchmark \\
            --module apps.aider_only \\
            --cache-directory /tmp/.cache \\
            --reports-directory reports \\
            detection-files/*.toml
    """

    # _assert_valid_reports_directory(reports_directory)

    assert timeout_for_app is None or timeout_for_app > timeout, (
        "Timeout for each application should be greater than the timeout for each instance"
    )

    modules = (
        list(_all_modules())
        if len(module) == 0
        else [_verified_module(m) for m in module]
    )

    benchmark_arguments = BenchmarkArguments(
        timeout=timeout,
        llm_cost_limit=llm_cost_limit,
    )

    # for task_directory in set(
    #     detection_file.parent.parent for detection_file in detection_files
    # ):
    #     metadata = TaskMetadata.model_validate_json(
    #         (task_directory / "metadata.json").read_text()
    #     )

    #     source_directory = task_directory / metadata.source_directory
    #     oss_fuzz_directory = task_directory / metadata.oss_fuzz_directory
    #     build_oss_fuzz_image(metadata.project_name, oss_fuzz_directory)
    #     run_command(
    #         f"python scripts/eval/environment_builder.py {metadata.project_name} {source_directory} {cache_directory / metadata.task_id}",
    #         env={
    #             "OSS_FUZZ_DIRECTORY": str(oss_fuzz_directory.resolve()),
    #         },
    #     )

    for app_module in tqdm(modules, desc="Apps", dynamic_ncols=True, colour="blue"):
        app_name = app_module.removeprefix("apps.")
        benchmark_results: List[BenchmarkResult] = []
        for detection_file in tqdm(
            detection_files,
            desc="Running",
            unit="detection",
            dynamic_ncols=True,
            leave=False,
            colour="green",
        ):
            task_directory = detection_file.parent.parent
            metadata = TaskMetadata.model_validate_json(
                (task_directory / "metadata.json").read_text()
            )
            output_directory = reports_directory / app_name / detection_file.stem
            print(f"\nApp name: {app_name}")
            print(f"Project name: {metadata.project_name}")
            print(f"Task directory: {task_directory}")

            clean_task_directory(task_directory)

            source_directory = task_directory / metadata.source_directory
            oss_fuzz_directory = task_directory / metadata.oss_fuzz_directory
            task_cache_directory = cache_directory / metadata.task_id
            if no_cache:
                sudo_rm(task_cache_directory)
            task_cache_directory.mkdir(parents=True, exist_ok=True)
            prev_result = None

            if keep_best_result:
                try:
                    prev_result = BenchmarkResult.load(output_directory / "result.json")
                except Exception:
                    pass

                if prev_result is not None:
                    if early_exit_on_sound and prev_result.variant == "sound":
                        continue
                    output_directory = (
                        reports_directory / app_name / (detection_file.stem + "_tmp")
                    )

            if output_directory.exists():
                shutil.rmtree(output_directory)
            output_directory.mkdir(parents=True, exist_ok=True)

            result = _run_single_benchmark(
                app_module,
                source_directory,
                output_directory,
                detection_file,
                benchmark_arguments,
                oss_fuzz_directory,
                task_cache_directory,
            )
            (output_directory / "result.json").write_text(result.model_dump_json())
            if no_cache:
                sudo_rm(task_cache_directory)
            clean_task_directory(task_directory)

            if keep_best_result and prev_result is not None:
                if not result.is_worse_than(prev_result):
                    shutil.rmtree(reports_directory / app_name / detection_file.stem)
                    shutil.copytree(
                        output_directory,
                        reports_directory / app_name / detection_file.stem,
                    )
                else:
                    result = prev_result
                shutil.rmtree(output_directory)

            benchmark_results.append(result)

        report_path = reports_directory / f"{app_name}.json"
        if report_path.exists():
            BenchmarkReport.from_benchmark_results(app_name, benchmark_results).append(
                report_path
            )
        else:
            BenchmarkReport.from_benchmark_results(app_name, benchmark_results).save(
                report_path
            )


def _run_crete_app(
    app_module: str,
    challenge_project_directory: Path,
    output_directory: Path,
    detection_file: Path,
    benchmark_arguments: BenchmarkArguments,
    oss_fuzz_directory: Path,
    cache_directory: Path,
) -> CreteResult:
    try:
        # Prepare command arguments
        cmd = [
            "python",
            "-m",
            app_module,
            "--challenge-project-directory",
            str(challenge_project_directory),
            "--detection-toml-file",
            str(detection_file),
            "--output-directory",
            str(output_directory),
            "--timeout",
            str(benchmark_arguments.timeout),
            "--llm-cost-limit",
            str(benchmark_arguments.llm_cost_limit),
        ]

        stdout_path = output_directory / "stdout.txt"
        stderr_path = output_directory / "stderr.txt"
        with (
            open(stdout_path, "w") as stdout_file,
            open(stderr_path, "w") as stderr_file,
        ):
            subprocess.run(
                cmd,
                env={
                    **os.environ,
                    "OSS_FUZZ_DIRECTORY": str(oss_fuzz_directory.resolve()),
                    "CACHE_DIRECTORY": str(cache_directory.resolve()),
                },
                check=True,
                stdout=stdout_file,
                stderr=stderr_file,
                timeout=benchmark_arguments.timeout,  # 1 hour timeout
            )

        # Parse the output to get the CreteResult
        # The module should output the result as JSON in stdout
        result_file = output_directory / "_crete_return.json"
        result_json = json.loads(result_file.read_text())

        # Determine the type of result based on the variant field
        variant = result_json.get("variant")
        if variant in (
            "sound",
            "vulnerable",
            "compilable",
            "uncompilable",
            "wrong",
            "internal_tests_failure",
        ):
            return DiffResult.model_validate(result_json)
        elif variant == "unknown_error":
            return ErrorResult.model_validate(result_json)
        elif variant == "no_patch":
            return NoPatchResult.model_validate(result_json)
        else:
            raise ValueError(f"Unknown variant: {variant}")
    except Exception:
        traceback.print_exc()
        raise


def _get_patch_result_from_crete_result(crete_result: CreteResult) -> str:
    match crete_result:
        case NoPatchResult(variant=variant):
            return f"No patch found ({variant})"
        case DiffResult(variant=variant, diff=_):
            return f"Patch found ({variant})"
        case ErrorResult(variant=variant, error=_):
            return f"Error ({variant})"


def _run_single_benchmark(
    app_module: str,
    challenge_project_directory: Path,
    output_directory: Path,
    detection_file: Path,
    benchmark_arguments: BenchmarkArguments,
    oss_fuzz_directory: Path,
    cache_directory: Path,
) -> BenchmarkResult:
    start_time = time.time()
    llm_cost = 0.0
    try:
        crete_result = _run_crete_app(
            app_module,
            challenge_project_directory,
            output_directory,
            detection_file,
            benchmark_arguments,
            oss_fuzz_directory,
            cache_directory,
        )
        elapsed_time = int(time.time() - start_time)
        llm_cost = crete_result.llm_usage.total_cost
        # Sarif detection does not contain the blob file. Instead, we use full-mode detection file to verify the patch.
        if detection_file.stem.endswith("-sarif") and crete_result.variant == "sound":
            if validation_detection_file := _detection_from_sarif_detection_file(
                detection_file
            ):
                crete_result = verify_patch_with_crete(
                    validation_detection_file,
                    challenge_project_directory,
                    output_directory / f"final-{crete_result.variant}.diff",
                )

        # Verify with PatchChecker, which is used by CRS-Patch.
        if crete_result.variant == "sound":
            old_crete_result = crete_result
            crete_result = verify_patch_with_patch_checker(
                detection_file,
                challenge_project_directory,
                output_directory / f"final-{crete_result.variant}.diff",
            )
            if crete_result.variant != old_crete_result.variant:
                _logger.warning(
                    f"PatchChecker result ({crete_result.variant}) is different from Crete result ({old_crete_result.variant})"
                )
            else:
                _logger.info("PatchChecker result: SOUND")

        _logger.info(
            f"{detection_file.stem} result:\n"
            f"  Patch: {_get_patch_result_from_crete_result(crete_result)}\n"
            f"  Elapsed time: {elapsed_time} seconds\n"
        )

        return BenchmarkResult.from_crete_result(
            crete_result,
            detection_file.stem,
            elapsed_time,
            llm_cost,
        )
    except Exception as e:
        return BenchmarkResult.model_validate(
            {
                "cpv_name": detection_file.stem,
                "variant": "unknown_error",
                "message": str(e),
                "elapsed_time": int(time.time() - start_time),
                "llm_cost": llm_cost,
            }
        )


def _all_modules() -> Iterator[str]:
    for path in glob("apps/**/*.py", recursive=True):
        module_name = Path(path).stem
        if module_name.startswith("_") or module_name.startswith("."):
            continue
        module = path.removesuffix(".py").replace("/", ".")
        assert module.startswith("apps.")
        yield _verified_module(module)


def _verified_module(module: str) -> str:
    try:
        importlib.import_module(module)
    except ImportError:
        raise ValueError(f"Could not import module {module}")

    return module


# Function removed since we're now using python -m to run the app module


def _assert_valid_reports_directory(reports_directory: Path):
    repository = Repository(".")  # FIXME: This is a hardcoded path
    head_commit = repository[repository.head.target].peel(1)
    commit_hash = str(head_commit.id)
    commit_timestamp = head_commit.commit_time

    for report_file in reports_directory.glob("*.json"):
        report = BenchmarkReport.load(report_file)
        assert (
            report.commit_hash == commit_hash
            and report.commit_timestamp == commit_timestamp
        ), (
            f'Report directory "{reports_directory}" is from a different commit. Please remove it.'
        )


def _detection_from_sarif_detection_file(detection_file: Path) -> Path | None:
    parent_dir = detection_file.parent.parent
    file_stem = detection_file.stem.replace("-sarif", "")
    detection_file = parent_dir / "full" / f"{file_stem}-full.toml"
    _logger.info(f"Sarif file detected. Using full detection file: {detection_file}")
    if not detection_file.exists():
        _logger.warning(f"Full detection file not found: {detection_file}")
        return None
    return detection_file


if __name__ == "__main__":
    run()
