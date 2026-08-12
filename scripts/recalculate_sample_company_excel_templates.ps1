param(
    [string]$LibreOfficePath = "C:\Program Files\LibreOffice\program\soffice.com"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$excelRoot = (Resolve-Path (Join-Path $repoRoot "starter_kits\KIT-MFG-NONFERROUS-PROCUREMENT\1.0.0\templates\excel")).Path

if (-not (Test-Path -LiteralPath $LibreOfficePath)) {
    $resolved = Get-Command soffice.com -ErrorAction SilentlyContinue
    if (-not $resolved) {
        throw "LibreOffice soffice.com을 찾을 수 없습니다. -LibreOfficePath로 지정하십시오."
    }
    $LibreOfficePath = $resolved.Source
}

$tempRoot = Join-Path $excelRoot (".recalc_" + $PID)
$profileRoot = Join-Path $tempRoot "profile"
New-Item -ItemType Directory -Force -Path $profileRoot | Out-Null

try {
    $profileUri = $profileRoot.Replace("\", "/")
    $files = Get-ChildItem -LiteralPath $excelRoot -Filter *.xlsx |
        Where-Object { $_.Name -ne "AFS_Starter_Kit_Onboarding_Index.xlsx" }
    if ($files.Count -ne 35) {
        throw "데이터셋 Excel이 35개가 아닙니다: $($files.Count)"
    }

    $arguments = @(
        "-env:UserInstallation=file:///$profileUri",
        "--headless",
        "--convert-to", "xlsx:Calc MS Excel 2007 XML",
        "--outdir", $tempRoot
    ) + @($files.FullName)

    & $LibreOfficePath @arguments | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "LibreOffice 재계산 실패: exit=$LASTEXITCODE"
    }

    $converted = Get-ChildItem -LiteralPath $tempRoot -Filter *.xlsx
    if ($converted.Count -ne 35) {
        throw "재계산 결과가 35개가 아닙니다: $($converted.Count)"
    }
    foreach ($file in $converted) {
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $excelRoot $file.Name) -Force
    }
    [pscustomobject]@{
        status = "recalculated"
        workbooks = $converted.Count
        excel_root = $excelRoot
    } | ConvertTo-Json
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        $resolvedTemp = (Resolve-Path -LiteralPath $tempRoot).Path
        if (-not $resolvedTemp.StartsWith($excelRoot + "\")) {
            throw "안전하지 않은 임시 경로: $resolvedTemp"
        }
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    }
}
