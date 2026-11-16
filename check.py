import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def check_outputs(root, version):
    config = json.loads((root / "global.json").read_text())
    actual = config["msbuild-sdks"]["WixToolset.Sdk"]
    assert actual == version, f"global.json has version {actual}, expected {version}"

    packages = ET.parse(root / "Directory.Packages.props")
    core = packages.find(".//PackageVersion[@Include='WixToolset.Core']")
    assert core is not None, "Directory.Packages.props is missing WixToolset.Core"
    assert core.get("Version") == version, "WixToolset.Core version is stale"

    props = ET.parse(root / "build/SomeVerInfo.props")
    assert props.findtext(".//SomeVerInfoVersion") == version, "Version props are stale"

    source = (root / "build/SomeVerInfo.cs").read_text()
    assert f'InformationalVersion = @"{version}";' in source, "C# version is incorrect"

    resource = (root / "build/SomeVerInfo.rc").read_text()
    assert f'VALUE "ProductVersion", CVS({version})' in resource, "RC version is incorrect"


def main():
    parser = argparse.ArgumentParser(description="Check WiX's five generated version files.")
    parser.add_argument("directory", type=Path)
    parser.add_argument("version")
    args = parser.parse_args()
    try:
        check_outputs(args.directory, args.version)
    except (AssertionError, ValueError, ET.ParseError, OSError) as error:
        print(f"Output check failed: {error}")
        return 1
    print("All five outputs have the intended format and version.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
