import logging
import os
import subprocess
from pathlib import Path
from typing import Literal, Optional

from crete.framework.environment.contexts import EnvironmentContext
from crete.framework.environment_pool.services.oss_fuzz import OssFuzzEnvironmentPool
from joblib import Memory
from python_aixcc_challenge.detection.models import (
    AIxCCChallengeDeltaMode,
    AIxCCChallengeFullMode,
    AIxCCChallengeMode,
    AIxCCChallengeProjectDetection,
)
from python_aixcc_challenge.project.models import AIxCCChallengeProjectYaml


def get_environment_context(
    logger: logging.Logger, sanitizer_name: str, cache_directory: Path
) -> EnvironmentContext:
    return {
        "logger": logger,
        "logging_prefix": "patch-manager",
        "memory": Memory(),
        "sanitizer_name": sanitizer_name,
    }


def init_environment_pool(
    environment_context: EnvironmentContext,
    project_name: str,
    challenge_mode: AIxCCChallengeMode,
    challenge_project_directory: Path,
    crete_cache_directory: Optional[Path] = None,
) -> OssFuzzEnvironmentPool:
    challenge_project_detection = AIxCCChallengeProjectDetection(
        vulnerability_identifier="",
        project_name=project_name,
        mode=challenge_mode,
    )
    challenge_project_yaml = AIxCCChallengeProjectYaml.from_project_name(project_name)
    environment_pool = OssFuzzEnvironmentPool(
        challenge_project_directory=challenge_project_directory,
        challenge_project_detection=challenge_project_detection,
        challenge_project_yaml=challenge_project_yaml,
        cache_directory=(crete_cache_directory / "environments")
        if crete_cache_directory
        else None,
        max_timeout=30 * 60,
    )

    print(environment_pool._create_environment_by_type(environment_context, "CLEAN"))  # pyright: ignore[reportPrivateUsage]
    print(environment_pool._create_environment_by_type(environment_context, "DEBUG"))  # pyright: ignore[reportPrivateUsage]
    print(
        environment_pool._create_environment_by_type(environment_context, "CALL_TRACE")  # pyright: ignore[reportPrivateUsage]
    )

    return environment_pool


def construct_challenge_mode(
    challenge_project_directory: Path, mode: Literal["full", "delta"]
) -> AIxCCChallengeMode:
    def run_git_command(cmd: str) -> str:
        try:
            return subprocess.check_output(
                cmd,
                cwd=challenge_project_directory,
                shell=True,
                text=True,
                stderr=subprocess.STDOUT,
            ).strip()
        except subprocess.CalledProcessError as e:
            print(f"Error running command: {cmd}")
            print(f"Return code: {e.returncode}")
            print(f"Output:\n{e.output}")
            raise

    match mode:
        case "full":
            base_ref = run_git_command("git rev-parse HEAD")
            challenge_mode = AIxCCChallengeFullMode.model_validate(
                {
                    "type": "full",
                    "base_ref": base_ref,
                }
            )
        case "delta":
            base_ref = run_git_command("git rev-parse HEAD~")
            delta_ref = run_git_command("git rev-parse HEAD")
            challenge_mode = AIxCCChallengeDeltaMode.model_validate(
                {
                    "type": "delta",
                    "base_ref": base_ref,
                    "delta_ref": delta_ref,
                }
            )
    return challenge_mode


def run_command(command: str, env: dict[str, str] = {}):
    try:
        subprocess.run(
            command,
            check=True,
            shell=True,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                **env,
            },
        )
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {command}")
        print(f"Return code: {e.returncode}")
        print(f"stderr:\n{e.stderr}")
        raise


def build_oss_fuzz_image(
    project_name: str,
    oss_fuzz_directory: Path,
):
    try:
        run_command(f"docker inspect aixcc-afc/{project_name}")
        return
    except Exception:
        pass

    run_command(
        f"python {oss_fuzz_directory}/infra/helper.py build_image --no-pull {project_name}"
    )


def make_crete_environments_cache(
    project_name: str,
    challenge_project_directory: Path,
    cache_directory: Path,
):
    logger = logging.getLogger(__name__)
    print(cache_directory)
    environment_context = get_environment_context(logger, "address", cache_directory)
    init_environment_pool(
        environment_context,
        project_name,
        construct_challenge_mode(challenge_project_directory, "full"),
        challenge_project_directory,
        crete_cache_directory=cache_directory,
    )
