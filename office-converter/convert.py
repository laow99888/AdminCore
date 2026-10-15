"""No network or host credentials. stdout is only a bounded PDF; no server/listener."""
import os
from pathlib import Path
import subprocess
import sys


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {'docx', 'xlsx', 'pptx', 'odt', 'ods', 'odp'}:
        raise ValueError('invalid_format')
    profile = Path('/tmp/profile/user')
    profile.mkdir(parents=True)
    # Very High, no trusted source/location; package validation rejects macro content too.
    (profile / 'registrymodifications.xcu').write_text('''<?xml version="1.0"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop><prop oor:name="SecureURL" oor:op="fuse"><value/></prop></item>
<item oor:path="/org.openoffice.Office.Common/Java"><prop oor:name="Enable" oor:op="fuse"><value>false</value></prop></item>
</oor:items>''', encoding='utf-8')
    output = Path('/tmp/output')
    output.mkdir()
    result = subprocess.run(['/usr/bin/soffice', '-env:UserInstallation=file:///tmp/profile',
        '--headless', '--nologo', '--nodefault', '--norestore', '--nofirststartwizard',
        '--convert-to', 'pdf', '--outdir', str(output), '/input/source.' + sys.argv[1]],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, env={
            'HOME': '/tmp', 'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'SAL_USE_VCLPLUGIN': 'svp'})
    target = output / 'source.pdf'
    if result.returncode or target.is_symlink() or not target.is_file() or not 0 < target.stat().st_size <= 10 * 1024 * 1024:
        raise ValueError('invalid_result')
    sys.stdout.buffer.write(target.read_bytes())


if __name__ == '__main__':
    try:
        main()
    except Exception:
        sys.exit(1)
