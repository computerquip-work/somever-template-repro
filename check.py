from pathlib import Path
import xml.etree.ElementTree as ET

version = Path("generated/version.txt").read_text().strip()
assert version == "Version=1.2.3", f"generated/version.txt contains {version!r}"
config = ET.parse("generated/config.xml")
assert config.findtext("Version") == "1.2.3"
print("Both outputs contain their own template's content.")
