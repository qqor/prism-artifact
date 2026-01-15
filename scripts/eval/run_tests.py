import json
import os
import pty
import signal
import subprocess
import tempfile
import time
from pathlib import Path

import click
import psutil

from scripts.eval.task_manager import sudo_rm

REPOSITORIES_DIRECTORY = Path("/repositories")


def kill_process_tree(pid: int):
    try:
        psutil_process = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

    children = psutil_process.children(recursive=True)
    for child in children[::-1]:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass

    try:
        psutil_process.kill()
    except psutil.NoSuchProcess:
        pass


def run_command(
    command: str,
    cwd: Path | None = None,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
    input: bytes | None = None,
) -> tuple[str, str]:
    main, sub = pty.openpty()
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdin=sub,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        env=env,
    )
    os.close(sub)

    try:
        if input:
            os.write(main, input + b"\n")
        stdout, stderr = process.communicate(timeout=timeout)

        return_code = process.returncode

        match return_code:
            case 0:
                return (stdout.decode(errors="ignore"), stderr.decode(errors="ignore"))
            case _:
                raise Exception(stdout, stderr)

    except subprocess.TimeoutExpired as error:
        os.kill(process.pid, signal.SIGINT)
        time.sleep(5)
        kill_process_tree(process.pid)
        stdout, stderr = process.communicate()

        raise Exception(stdout, stderr) from error


def apply_patch_diff(repo_directory: Path, patch_diff: Path):
    subprocess.run(
        ["git", "-C", repo_directory, "apply", str(patch_diff.absolute())], check=True
    )


def git_checkout(repository_directory: Path, ref: str | None = None):
    repo = str(repository_directory)

    subprocess.run(["git", "-C", repo, "restore", "--source=HEAD", ":/"], check=True)

    subprocess.run(["git", "-C", repo, "clean", "-fdx"], check=True)

    if ref is not None:
        subprocess.run(["git", "-C", repo, "checkout", "-f", ref], check=True)


def run_tests2(
    oss_fuzz_directory: Path,
    project_name: str,
    source_directory: Path,
    test_script: Path,
):
    helper_script = oss_fuzz_directory / "infra" / "helper.py"
    command = (f"{helper_script} build_image --no-pull --cache {project_name}",)
    print(command)
    try:
        subprocess.check_call(
            command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        raise e

    run_tests_script = Path(__file__).parent.parent.parent / Path(
        "third_party/crs-architecture/example-challenge-evaluation/action-run-tests/run_tests.sh"
    )
    command = (
        f'{run_tests_script} -p {project_name} -r {source_directory.absolute()} -t "{str(test_script.absolute())}"',
    )
    print(command)
    try:
        subprocess.check_call(
            command,
            shell=True,
        )
    except Exception as e:
        raise e


def run_tests(
    oss_fuzz_directory: Path, project_name: str, repos_directory: Path, test_sh: str
):
    test_sh_path = oss_fuzz_directory / "build" / "work" / project_name / "test.sh"
    test_sh_path.parent.mkdir(parents=True, exist_ok=True)
    with open(test_sh_path, "w") as f:
        f.write(test_sh)

    test_sh_path.chmod(0o755)
    command = f"{oss_fuzz_directory / 'infra' / 'helper.py'} shell {project_name} {repos_directory}"
    try:
        run_command(
            command=command,
            input="/work/test.sh; exit $?".encode(),
            cwd=oss_fuzz_directory,
            timeout=1800,
        )
    except Exception as e:
        print(command)
        raise e


@click.command()
@click.argument("patch_diff", type=Path)
@click.option(
    "--detection-name",
    required=True,
    help="Task ID(e.g., apache-poi_poi-delta-01)",
)
@click.option("--repository-directory", type=Path, default=REPOSITORIES_DIRECTORY)
def main(patch_diff: Path, detection_name: str, repository_directory: Path):
    """Run tests for a given patch diff file."""

    if not patch_diff.exists():
        click.echo(f"Error: Patch file {patch_diff} does not exist", err=True)
        return

    with open(repository_directory / "detections.json", "r") as f:
        detections_info = json.load(f)

    detection_info = detections_info[detection_name]
    cp_name = detection_info["cp_name"]
    project_name = detection_info["project_name"]
    source_directory = repository_directory / detection_info["focus"]
    oss_fuzz_directory = repository_directory / "oss-fuzz-aixcc"

    sudo_rm(oss_fuzz_directory / "build")
    git_checkout(source_directory, f"challenges/{cp_name}")
    git_checkout(oss_fuzz_directory, f"challenge-state/{cp_name}")

    test_script = source_directory / ".aixcc" / "test.sh"
    # Create temp directory and apply patch

    temporary_directory = Path(tempfile.mkdtemp())
    try:
        # shutil.copytree(source_directory, temporary_directory, dirs_exist_ok=True)
        os.system(f"cp -rf {source_directory}/* {temporary_directory}/")
        apply_patch_diff(temporary_directory, patch_diff)

        # Run tests
        run_tests2(
            oss_fuzz_directory,
            project_name,
            temporary_directory,
            test_script,
        )
        click.echo("Tests passed successfully!")
    except Exception as e:
        click.echo(e, err=True)
        click.echo("Tests failed!", err=True)
        raise click.Abort()
    finally:
        try:
            sudo_rm(temporary_directory)
            sudo_rm(oss_fuzz_directory / "build")
        except Exception:
            click.echo("Failed to clean up!", err=True)


if __name__ == "__main__":
    main()
