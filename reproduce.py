import argparse
import os
from pathlib import Path
import subprocess

from check import check_outputs


ROOT = Path(__file__).resolve().parent
REVISION = "642f1a0f7c857ffa4fc9fa3f9d1433aab895dd29"
PROJECT = Path("src/internal/SetBuildNumber/SomeVerInit.verproj")
OUTPUTS = (
    "global.json",
    "Directory.Packages.props",
    "build/SomeVerInfo.cs",
    "build/SomeVerInfo.rc",
    "build/SomeVerInfo.props",
)


def run(command, cwd, log, env):
    with log.open("w") as output:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=output,
                                stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"Command failed; see {log.relative_to(ROOT)}")


def report_check(work, version):
    try:
        check_outputs(work, version)
    except (AssertionError, ValueError) as error:
        print(f"  Output check failed: {error}")
        return False
    print(f"  All five outputs are correct for {version}.")
    return True


def clone_wix(work, log, env):
    run(["git", "clone", "--depth", "1", "--branch", "v7.0.1",
         "https://github.com/wixtoolset/wix.git", str(work)], ROOT, log, env)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=work,
                                       text=True).strip()
    assert revision == REVISION, "The upstream WiX tag points to an unexpected revision"


def upgrade(work):
    project = work / PROJECT
    content = project.read_bytes()
    assert content.count(b"SomeVer/0.1.1") == 1
    project.write_bytes(content.replace(b"SomeVer/0.1.1", b"SomeVer/0.1.2"))


def main():
    parser = argparse.ArgumentParser(description="Reproduce SomeVer failures in upstream WiX.")
    parser.add_argument("--work-dir", type=Path, default=Path("build/wix"))
    parser.add_argument("--fix", action="store_true",
                        help="Also demonstrate the one-line fix in an isolated NuGet cache.")
    args = parser.parse_args()
    work = ROOT / args.work_dir
    if work.exists():
        parser.error("Work directory exists; choose a fresh --work-dir.")

    logs = ROOT / "build/agent/logs"
    logs.mkdir(parents=True, exist_ok=True)
    work.parent.mkdir(parents=True, exist_ok=True)
    packages = work.parent / (work.name + "-packages")
    env = os.environ.copy()
    env["NUGET_PACKAGES"] = str(packages)
    env["DOTNET_PROCESSOR_COUNT"] = "2"

    clone_wix(work, logs / "clone.log", env)

    # Invoke from this repository to select .NET 10 despite WiX's .NET 9 SDK pin.
    build = ["dotnet", "build", str(work / PROJECT), "--disable-build-servers"]
    print("1. Upstream WiX v7.0.1, unchanged SomeVer 0.1.1:")
    run(build, ROOT, logs / "baseline.log", env)
    check_outputs(work, "7.0.1")
    print("  All five outputs are correct for 7.0.1.")

    print("2. Add v7.0.2 without changing any templates; rebuild with 0.1.1:")
    run(["git", "tag", "v7.0.2"], work, logs / "tag.log", env)
    run(build, ROOT, logs / "stale.log", env)
    report_check(work, "7.0.2")

    upgrade(work)
    print("3. Upgrade only the SomeVer SDK pin to stock 0.1.2:")
    run(build, ROOT, logs / "upgrade.log", env)
    for path in OUTPUTS:
        print(f"  {path}: {(work / path).read_text().splitlines()[0]}")
    correct = report_check(work, "7.0.2")
    with (logs / "next-dotnet.log").open("w") as output:
        result = subprocess.run(["dotnet", "--version"], cwd=work, env=env,
                                stdout=output, stderr=subprocess.STDOUT)
    print(f"  Next dotnet command exits {result.returncode}; see build/agent/logs/next-dotnet.log.")

    if args.fix:
        print("4. Add Outputs batching to the isolated SomeVer 0.1.2 target:")
        target = packages / "somever/0.1.2/build/SomeVer.targets"
        content = target.read_bytes()
        declaration = b'<Target Name="SomeVerApplyVersionTemplates"'
        assert content.count(declaration) == 1
        newline = b"\r\n" if b"\r\n" in content else b"\n"
        replacement = declaration + newline + b'          Outputs="%(VersionTemplate.OutputPath)"'
        target.write_bytes(content.replace(declaration, replacement))

        # The broken global.json blocks SDK resolution; preserve it and use a fresh checkout.
        corrected = work.with_name(work.name + "-corrected")
        clone_wix(corrected, logs / "fixed-clone.log", env)
        fixed_build = ["dotnet", "build", str(corrected / PROJECT), "--disable-build-servers"]
        run(fixed_build, ROOT, logs / "fixed-baseline.log", env)
        check_outputs(corrected, "7.0.1")
        run(["git", "tag", "v7.0.2"], corrected, logs / "fixed-tag.log", env)
        upgrade(corrected)
        run(fixed_build, ROOT, logs / "fixed.log", env)
        correct = report_check(corrected, "7.0.2")

    return 0 if correct else 1


if __name__ == "__main__":
    raise SystemExit(main())
