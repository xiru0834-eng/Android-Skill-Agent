$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$project = Join-Path $repo 'android/agent'
$out = Join-Path $project 'build/service-audit-test'
New-Item -ItemType Directory -Force -Path $out | Out-Null
& javac -encoding UTF-8 -d $out (Join-Path $project 'app/src/main/java/edu/sydney/probe/PortableServiceAudit.java') (Join-Path $project 'tests/edu/sydney/probe/PortableServiceAuditTest.java')
if ($LASTEXITCODE -ne 0) { throw 'Service audit test compilation failed.' }
& java -cp $out edu.sydney.probe.PortableServiceAuditTest
if ($LASTEXITCODE -ne 0) { throw 'Service audit test failed.' }
Write-Output 'This is a pure JVM test, not an Android service or device E2E run.'
