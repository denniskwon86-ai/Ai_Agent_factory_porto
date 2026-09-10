$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$taskOutput = Join-Path $PSScriptRoot 'audio'
New-Item -ItemType Directory -Force -Path $taskOutput | Out-Null
$taskNarrator = New-Object System.Speech.Synthesis.SpeechSynthesizer
$taskNarrator.SelectVoice('Microsoft Heami Desktop')
$taskNarrator.Rate = 0
$taskNarrator.Volume = 100
$taskLines = @(
    '흩어진 업무와 데이터.',
    '현업의 생각을 업무 앱으로.',
    '부서의 데이터를 회사의 지식으로.',
    '경영 판단에서, 실행과 학습까지.',
    '현업과 경영을 잇는, 랙스 엠.'
)
for ($taskIndex = 0; $taskIndex -lt $taskLines.Count; $taskIndex++) {
    $taskNarrator.Rate = if ($taskIndex -eq 4) { 2 } else { 0 }
    $taskNarrator.SetOutputToWaveFile((Join-Path $taskOutput ('voice_{0}.wav' -f $taskIndex)))
    $taskNarrator.Speak($taskLines[$taskIndex])
    $taskNarrator.SetOutputToNull()
}
$taskNarrator.Dispose()
Write-Output '한국어 내레이션 5개 구간 생성 완료'
