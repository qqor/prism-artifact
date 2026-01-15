#!/usr/bin/env python3

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import toml

sys.path.append(str(Path(__file__).parent))
from models import (
    AIxCCChallengeBlobInfo,
    AIxCCChallengeDeltaMode,
    AIxCCChallengeFullMode,
    AIxCCChallengeProjectDetection,
    CommitHexString,
    TarballMetadata,
    TaskMetadata,
)


def sudo_rm(target: Path):
    if not target.exists():
        return

    target = target.resolve()
    cwd = target.parent
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "-v",
            f"{cwd}:{cwd}",
            "--workdir",
            f"{cwd}",
            "ghcr.io/aixcc-finals/base-builder:v1.3.0",
            "rm",
            "-rf",
            target,
        ],
        check=True,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="AFC Detection Maker")
    parser.add_argument(
        "afc_tarballs_directory", help="Target directory containing task files"
    )
    parser.add_argument(
        "--save-directory",
        default=".afc/tasks",
        help="Cache directory for trajectory data (default: .afc/tasks)",
    )
    parser.add_argument(
        "--target",
        required=False,
        help="Target directory containing task files",
        type=str,
        default=None,
    )
    return parser.parse_args()


def extract_tarball(tarball_path: Path, extract_to: Path):
    """Extract a tarball to the specified directory."""
    if tarball_path.exists():
        print(f"Extracting {tarball_path} to {extract_to}")
        with tarfile.open(tarball_path, "r:gz") as tar:
            tar.extractall(path=extract_to)
        return True
    else:
        print(f"Warning: {tarball_path} does not exist")
        return False


def get_head_commit(repo_dir: Path):
    """Get the HEAD commit hash of the git repository in the specified directory."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_dir, "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        head_commit = result.stdout.strip()
        print(f"HEAD commit in {repo_dir} is {head_commit}")
        return head_commit
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error getting HEAD commit: {e}")


def setup_git_repo(repo_dir: Path) -> CommitHexString:
    """Initialize git repository in the specified directory. Then, return the initial commit hash."""
    try:
        subprocess.run(["git", "-C", repo_dir, "init"], check=True)
        subprocess.run(
            ["git", "-C", repo_dir, "config", "user.name", "Your Name"], check=True
        )
        subprocess.run(
            ["git", "-C", repo_dir, "config", "user.email", "you@example.com"],
            check=True,
        )
        # initial commit
        subprocess.run(["git", "-C", repo_dir, "add", "."], check=True)
        subprocess.run(
            ["git", "-C", repo_dir, "commit", "-m", "Initial commit"], check=True
        )
        print(f"Initialized git repository in {repo_dir}")
        # Get the initial commit hash
        return get_head_commit(repo_dir)
    except subprocess.CalledProcessError as e:
        print(f"Error initializing git repository: {e}")
        raise


def apply_diff_and_commit(repo_dir: Path, diff_path: Path) -> CommitHexString:
    """Apply a diff file to the repository and commit changes."""
    try:
        subprocess.run(
            ["git", "-C", repo_dir, "apply", "--reject", diff_path.absolute()],
        )
        subprocess.run(["git", "-C", repo_dir, "add", "--all", "-f"], check=True)
        subprocess.run(
            ["git", "-C", repo_dir, "commit", "-m", "Applied diff patch"], check=True
        )
        print(f"Applied and committed diff from {diff_path}")
        # Get the new commit hash
        return get_head_commit(repo_dir)
    except subprocess.CalledProcessError as e:
        print(f"Error applying diff or committing: {e}")
        raise


def get_tarball_metadata(target_directory: Path) -> TarballMetadata:
    metadata_path = target_directory / "metadata.json"
    if not metadata_path.exists():
        raise ValueError(f"Error: metadata.json not found in {target_directory}")

    with open(metadata_path, "r") as f:
        metadata = json.load(f)
        try:
            return TarballMetadata.model_validate(metadata)
        except Exception as e:
            print(f"Error validating metadata: {metadata_path}")
            print(f"Error: {e}")
            raise ValueError(f"Error validating metadata: {metadata_path}")


def prepare_task(target_directory: Path, save_directory: Path) -> Path:
    if not target_directory.exists():
        print(f"Error: Target directory {target_directory} does not exist")
        raise ValueError(f"Error: Target directory {target_directory} does not exist")
    if not save_directory.exists():
        save_directory.mkdir(parents=True, exist_ok=True)
        print(f"Created save directory: {save_directory}")

    if not (target_directory / "metadata.json").exists():
        raise ValueError(f"Error: metadata.json not found in {target_directory}")

    metadata = get_tarball_metadata(target_directory)
    task_id = metadata.task_id
    project_name = metadata.project_name
    focus = metadata.focus
    povs = {str(pov["pov"]): pov for pov in metadata.pov}
    print(f"povs: {povs}")
    print(f"focus: {focus}")
    print(f"task_id: {task_id}")
    print(f"project_name: {project_name}")

    print(f"Processing task: {task_id}, project: {project_name}")

    # Step 1: Create trajectory directory
    task_directory = save_directory / task_id
    if task_directory.exists():
        shutil.rmtree(task_directory)
    os.makedirs(task_directory)
    print(f"Cache directory: {task_directory}")

    # Step 2: Extract oss-fuzz.tar.gz
    oss_fuzz_directory = task_directory / "fuzz-tooling"
    oss_fuzz_tarball = target_directory / "task_tarballs" / "oss-fuzz.tar.gz"
    if not extract_tarball(oss_fuzz_tarball, task_directory):
        raise ValueError("oss-fuzz.tar.gz extraction failed")
    if not (oss_fuzz_directory).exists():
        assert False, "oss-fuzz directory not found"

    # HELPER file....
    shutil.copy(
        Path(__file__).parent.parent.parent
        / "packages"
        / "python_oss_fuzz"
        / ".oss_fuzz"
        / "infra"
        / "helper.py",
        oss_fuzz_directory / "infra" / "helper.py",
    )

    # Step 3: Extract repo.tar.gz and initialize git
    source_directory = task_directory / focus
    repo_tarball = target_directory / "task_tarballs" / "repo.tar.gz"
    if not extract_tarball(repo_tarball, task_directory):
        assert False, "repo.tar.gz extraction failed"
    if not (source_directory).exists():
        assert False, "Repo directory not found"

    base_commit = setup_git_repo(source_directory)

    # Step 4: Extract diff.tar.gz if it exists and apply the diff
    diff_commit = None
    diff_tarball = target_directory / "task_tarballs" / "diff.tar.gz"
    if diff_tarball.exists():
        if not extract_tarball(diff_tarball, task_directory):
            assert False, "diff.tar.gz extraction failed"
        diff_file = task_directory / "diff" / "ref.diff"
        if diff_file.exists():
            diff_commit = apply_diff_and_commit(source_directory, diff_file)
        else:
            print(f"Warning: diff file {diff_file} not found")

    if diff_commit:
        mode = AIxCCChallengeDeltaMode(delta_ref=diff_commit, base_ref=base_commit)
    else:
        mode = AIxCCChallengeFullMode(base_ref=base_commit)

    detections: list[AIxCCChallengeProjectDetection] = []
    # Step 5: Make detection files for each pov in the bundle
    (task_directory / "detection").mkdir()
    for pov_id in povs:
        harness_name = povs[pov_id]["harness_name"]
        sanitizer = povs[pov_id]["sanitizer"]
        blob = (target_directory / "pov" / pov_id).read_bytes()
        blob_info = AIxCCChallengeBlobInfo(
            harness_name=harness_name,
            sanitizer_name=sanitizer,
            blob=base64.b64encode(blob).decode(errors="replace"),
        )

        detections.append(
            AIxCCChallengeProjectDetection(
                mode=mode,
                vulnerability_identifier=pov_id,
                project_name=project_name,
                blobs=[blob_info],
                sarif_report=None,
            )
        )

    detection_files: list[str] = []
    for detection in detections:
        save_detection(
            task_directory / "detection" / f"{detection.vulnerability_identifier}.toml",
            detection,
        )
        detection_files.append(str(f"{detection.vulnerability_identifier}.toml"))

    task_metadata = TaskMetadata(
        task_id=task_id,
        project_name=project_name,
        focus=focus,
        detections=detection_files,
        mode=mode.type,
        base_commit=base_commit,
        diff_commit=diff_commit,
        source_directory=str(source_directory.relative_to(task_directory)),
        oss_fuzz_directory=str(oss_fuzz_directory.relative_to(task_directory)),
    )
    (task_directory / "metadata.json").write_text(task_metadata.model_dump_json())
    zzz = TaskMetadata.model_validate_json(
        (task_directory / "metadata.json").read_text()
    )
    print(f"Task directory: {zzz.project_name}")
    return task_directory


def save_detection(detection_path: Path, detection: AIxCCChallengeProjectDetection):
    detection_content = toml.dumps(detection.model_dump())
    detection_content = (
        "# DO NOT EDIT THIS FILE.\n"
        "# This file is automatically generated by `scripts/eval/afc_detection_maker.py`\n\n"
        + detection_content
    )
    detection_path.write_text(detection_content)
    print(f"Stored {detection_path}")


def clean_task_directory(task_directory: Path):
    with open(task_directory / "metadata.json", "r") as f:
        metadata = json.load(f)

    subprocess.run(
        [
            "git",
            "-C",
            str(task_directory / metadata["focus"]),
            "restore",
            "--source=HEAD",
            ":/",
        ]
    )
    subprocess.run(
        ["git", "-C", str(task_directory / metadata["focus"]), "clean", "-fd"]
    )

    build_directory = task_directory / "fuzz-tooling" / "build"
    if build_directory.exists():
        sudo_rm(build_directory)


if __name__ == "__main__":
    args = parse_args()
    save_directory = Path(args.save_directory)

    if args.target:
        tarball_directories = [Path(args.afc_tarballs_directory) / args.target]
    else:
        tarball_directories = Path(args.afc_tarballs_directory).glob("*/")

    for target_directory in tarball_directories:
        print(f"Processing {target_directory}")
        try:
            if not (target_directory / "metadata.json").exists():
                continue
            task_directory = prepare_task(target_directory, save_directory)
            print(f"OSS-Fuzz project directory: {task_directory}")
        except Exception as e:
            print(f"Error processing {target_directory}: {e}")
            # log to file
            with open(f"logs/{target_directory.name}.log", "a") as f:
                f.write(f"{e}\n")
