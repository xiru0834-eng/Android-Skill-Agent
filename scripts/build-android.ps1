param(
    [string]$SdkPath = $(if ($env:ANDROID_SDK_ROOT) { $env:ANDROID_SDK_ROOT } else { $env:ANDROID_HOME }),
    [string]$DebugKeystore = (Join-Path $env:USERPROFILE '.android/debug.keystore')
)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($SdkPath)) {
    throw 'Supply -SdkPath or configure ANDROID_SDK_ROOT / ANDROID_HOME.'
}
$sdk = (Resolve-Path -LiteralPath $SdkPath).Path
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$tools = Join-Path $sdk 'build-tools/34.0.0'
$androidJar = Join-Path $sdk 'platforms/android-34/android.jar'
foreach ($tool in @('aapt2.exe','aapt.exe','d8.bat','zipalign.exe','apksigner.bat')) {
    if (-not (Test-Path -LiteralPath (Join-Path $tools $tool) -PathType Leaf)) {
        throw ('Missing Android Build Tools 34.0.0: ' + $tool)
    }
}
if (-not (Test-Path -LiteralPath $androidJar -PathType Leaf)) { throw 'Missing Android platform 34.' }
foreach ($tool in @('java','javac','jar','keytool')) { Get-Command $tool -ErrorAction Stop | Out-Null }
$jdkVersion = (& javac -version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $jdkVersion -notmatch '^javac 17\.') { throw 'Use JDK 17 for this frozen snapshot.' }
if (-not (Test-Path -LiteralPath $DebugKeystore -PathType Leaf)) {
    $keyPath = [IO.Path]::GetFullPath($DebugKeystore)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $keyPath) | Out-Null
    & keytool -genkeypair -keystore $keyPath -alias androiddebugkey -storepass android -keypass android -dname 'CN=Android Debug,O=Android,C=US' -keyalg RSA -keysize 2048 -validity 10000
    if ($LASTEXITCODE -ne 0) { throw 'Debug key generation failed.' }
}
$key = (Resolve-Path -LiteralPath $DebugKeystore).Path
foreach ($app in @('agent','parameter-room')) {
    $project = Join-Path $repo ('android/' + $app)
    # An isolated ASCII temporary path also avoids Windows SDK argument issues.
    $staging = Join-Path ([IO.Path]::GetTempPath()) ('android-skill-build-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $staging | Out-Null
    Copy-Item -LiteralPath (Join-Path $project 'app/src/main') -Destination (Join-Path $staging 'main') -Recurse
    $out = Join-Path $staging 'build'
    New-Item -ItemType Directory -Force -Path $out,(Join-Path $out 'classes'),(Join-Path $out 'dex') | Out-Null
    & (Join-Path $tools 'aapt2.exe') compile --dir (Join-Path $staging 'main/res') -o (Join-Path $out 'resources.zip')
    if ($LASTEXITCODE -ne 0) { throw "$app resources compile failed" }
    & (Join-Path $tools 'aapt2.exe') link -o (Join-Path $out 'resources.apk') -I $androidJar --manifest (Join-Path $staging 'main/AndroidManifest.xml') -R (Join-Path $out 'resources.zip') --auto-add-overlay
    if ($LASTEXITCODE -ne 0) { throw "$app resources link failed" }
    $sources = @(Get-ChildItem -LiteralPath (Join-Path $staging 'main/java') -Recurse -Filter '*.java' | ForEach-Object FullName)
    & javac -encoding UTF-8 -source 17 -target 17 -cp $androidJar -d (Join-Path $out 'classes') $sources
    if ($LASTEXITCODE -ne 0) { throw "$app Java compilation failed" }
    $archive = Join-Path $out 'classes.jar'
    & jar --create --file $archive -C (Join-Path $out 'classes') .
    if ($LASTEXITCODE -ne 0) { throw "$app class archive failed" }
    & (Join-Path $tools 'd8.bat') --min-api 30 --lib $androidJar --output (Join-Path $out 'dex') $archive
    if ($LASTEXITCODE -ne 0) { throw "$app dex compilation failed" }
    Copy-Item -LiteralPath (Join-Path $out 'resources.apk') -Destination (Join-Path $out 'unsigned.apk')
    Push-Location (Join-Path $out 'dex')
    try {
        & (Join-Path $tools 'aapt.exe') add (Join-Path $out 'unsigned.apk') 'classes.dex'
        if ($LASTEXITCODE -ne 0) { throw "$app dex packaging failed" }
    } finally { Pop-Location }
    & (Join-Path $tools 'zipalign.exe') -f 4 (Join-Path $out 'unsigned.apk') (Join-Path $out 'aligned.apk')
    if ($LASTEXITCODE -ne 0) { throw "$app alignment failed" }
    $destination = Join-Path $project ('build/manual/' + $app + '-debug.apk')
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    & (Join-Path $tools 'apksigner.bat') sign --ks $key --ks-key-alias androiddebugkey --ks-pass 'pass:android' --key-pass 'pass:android' --out $destination (Join-Path $out 'aligned.apk')
    if ($LASTEXITCODE -ne 0) { throw "$app signing failed" }
    & (Join-Path $tools 'apksigner.bat') verify --verbose $destination
    if ($LASTEXITCODE -ne 0) { throw "$app signature verification failed" }
    Write-Output ('APK_BUILT=' + $destination)
    Write-Output ('BUILD_TEMP=' + $staging)
}
